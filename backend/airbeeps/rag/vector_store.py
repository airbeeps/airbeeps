import logging
from pathlib import Path
from typing import Any

from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document as VectorDocument
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStoreRetriever

from airbeeps.config import settings

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """Encapsulate Chroma vector store operations"""

    def __init__(self) -> None:
        self.host = settings.CHROMA_SERVER_HOST
        self.port = settings.CHROMA_SERVER_PORT
        if settings.CHROMA_PERSIST_DIR:
            Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        # Keep a consistent Chroma client configuration to avoid "different settings" errors
        self.client_settings = ChromaSettings(
            anonymized_telemetry=False,
            persist_directory=settings.CHROMA_PERSIST_DIR or None,
            allow_reset=True,
        )

    def _get_collection(
        self,
        collection_name: str,
        embedding_function: Embeddings | None = None,
    ) -> Chroma:
        kwargs: dict[str, Any] = {
            "collection_name": collection_name,
        }

        # Use embedded mode if no host is set or if persist_dir is set
        use_embedded = (
            not self.host
            or self.host in ["", "chromadb"]
            or settings.CHROMA_PERSIST_DIR
        )

        if use_embedded:
            # Embedded mode: use local persistence
            kwargs["persist_directory"] = settings.CHROMA_PERSIST_DIR
        else:
            # Server mode: connect to remote Chroma server
            kwargs["host"] = self.host
            kwargs["port"] = self.port

        # Enforce consistent client settings (telemetry off, single persistence config)
        kwargs["client_settings"] = self.client_settings

        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function

        return Chroma(**kwargs)

    async def get_retriever(
        self, collection_name: str, embedding_function: Embeddings, **kwargs: Any
    ) -> VectorStoreRetriever:
        logger.debug(f"Getting retriever for collection: {collection_name}")
        collection = self._get_collection(
            collection_name,
            embedding_function=embedding_function,
        )
        retriever = collection.as_retriever(**kwargs)
        logger.debug(
            f"Created retriever for collection {collection_name} with kwargs: {kwargs}"
        )
        return retriever

    async def add_documents(
        self,
        collection_name: str,
        documents: list[VectorDocument],
        embedding_function: Embeddings | None = None,
    ) -> None:
        if not documents:
            logger.debug(f"No documents to add to collection {collection_name}")
            return

        logger.info(
            f"Adding {len(documents)} documents to vector store collection: {collection_name}"
        )

        collection = self._get_collection(
            collection_name,
            embedding_function=embedding_function,
        )

        # Ensure each document has valid string content
        for i, doc in enumerate(documents):
            if not isinstance(doc.page_content, str):
                logger.error(
                    f"Document {i} content type invalid: {type(doc.page_content)}"
                )
                raise ValueError(
                    f"Document content must be a string, got {type(doc.page_content)}"
                )
            if not doc.page_content.strip():
                logger.error(f"Document {i} has empty content")
                raise ValueError("Document content cannot be empty")

        # Extract document IDs
        ids = [doc.id for doc in documents]

        try:
            await collection.aadd_documents(documents=documents, ids=ids)
            logger.info(
                f"Successfully added {len(documents)} documents to collection {collection_name}"
            )
        except Exception as exc:
            logger.error(
                f"Failed to add documents to Chroma collection {collection_name}: {exc}",
                exc_info=True,
            )
            raise

    async def search_documents(
        self,
        *,
        collection_name: str,
        embedding_function: Embeddings,
        query: str,
        k: int,
        fetch_k: int | None = None,
        score_threshold: float | None = None,
        where_filter: dict[str, Any] | None = None,
        search_type: str = "similarity",
        mmr_lambda: float = 0.5,
    ) -> list[tuple[VectorDocument, float | None]]:
        """
        Retrieve documents with optional score/threshold support.

        Returns list of (document, score) sorted by score desc when available.
        """
        collection = self._get_collection(
            collection_name, embedding_function=embedding_function
        )
        # Ensure fetch_k is at least k when provided
        effective_fetch_k = max(fetch_k or k, k)

        if search_type == "mmr":
            docs = await collection.a_max_marginal_relevance_search(
                query,
                k=k,
                fetch_k=effective_fetch_k,
                lambda_mult=mmr_lambda,
                filter=where_filter,
            )
            # MMR path does not return scores
            return [(doc, None) for doc in docs]

        # Similarity with scores; prefer LC helper, fall back to manual query
        try:
            results = await collection.asimilarity_search_with_relevance_scores(
                query=query,
                k=effective_fetch_k,
                filter=where_filter,
                fetch_k=effective_fetch_k,
                score_threshold=score_threshold,
            )
        except TypeError:
            # Older langchain-chroma may not accept fetch_k/score_threshold
            results = await collection.asimilarity_search_with_relevance_scores(
                query=query,
                k=effective_fetch_k,
                filter=where_filter,
            )

        # results: List[Tuple[VectorDocument, float]]
        filtered: list[tuple[VectorDocument, float | None]] = []
        for doc, score in results:
            if (
                score_threshold is not None
                and score is not None
                and score < score_threshold
            ):
                continue
            filtered.append((doc, score))

        filtered.sort(
            key=lambda pair: pair[1] if pair[1] is not None else -1, reverse=True
        )
        if len(filtered) > k:
            filtered = filtered[:k]
        logger.debug(
            "Chroma search complete (type=%s, k=%s, fetch_k=%s, threshold=%s, returned=%s)",
            search_type,
            k,
            effective_fetch_k,
            score_threshold,
            len(filtered),
        )
        return filtered

    async def delete_documents(
        self,
        collection_name: str,
        ids: list[str],
    ) -> None:
        if not ids:
            logger.debug(f"No documents to delete from collection {collection_name}")  # noqa: S608
            return

        logger.info(
            f"Deleting {len(ids)} documents from vector store collection: {collection_name}"
        )

        collection = self._get_collection(collection_name)

        try:
            await collection.adelete(ids=ids)
            logger.info(
                f"Successfully deleted {len(ids)} documents from collection {collection_name}"
            )
        except Exception as exc:
            logger.error(
                f"Failed to delete documents from Chroma collection {collection_name}: {exc}",
                exc_info=True,
            )
            raise

    async def delete_collection(self, collection_name: str) -> None:
        """
        Drop an entire collection from Chroma to remove all vectors for a KB.
        """
        logger.info("Deleting Chroma collection: %s", collection_name)
        try:
            collection = self._get_collection(collection_name)

            # langchain-chroma exposes the underlying client on _client
            client = getattr(collection, "_client", None)
            if client and hasattr(client, "delete_collection"):
                client.delete_collection(collection_name)
                logger.info("Deleted Chroma collection via client: %s", collection_name)
                return

            # Fallback: attempt collection-level delete if available
            if hasattr(collection, "delete_collection"):
                collection.delete_collection()
                logger.info(
                    "Deleted Chroma collection via collection handle: %s",
                    collection_name,
                )
                return

            logger.warning(
                "Could not delete collection %s (no client delete handler available)",
                collection_name,
            )
        except Exception as exc:
            logger.error(
                "Failed to delete Chroma collection %s: %s",
                collection_name,
                exc,
                exc_info=True,
            )
            raise

    async def get_collection_info(self, collection_name: str) -> dict[str, Any]:
        """
        Get basic metadata about a Chroma collection.

        Returns at least: {name, count}. On error includes {error}.
        """
        try:
            collection = self._get_collection(collection_name)

            # langchain_chroma.Chroma wraps a chromadb Collection as _collection
            internal = getattr(collection, "_collection", None)
            if internal is not None and hasattr(internal, "count"):
                count = int(internal.count())
            else:
                # Fallback: try len() if implemented
                count = len(collection)  # type: ignore[arg-type]

            return {
                "name": collection_name,
                "count": count,
            }
        except Exception as exc:
            logger.warning(
                "Failed to get collection info for %s: %s",
                collection_name,
                exc,
                exc_info=True,
            )
            return {
                "name": collection_name,
                "count": 0,
                "error": str(exc),
            }
