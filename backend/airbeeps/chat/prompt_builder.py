"""Prompt builder utilities for LangchainChatService."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import tiktoken
from sqlalchemy import select

from airbeeps.assistants.models import (
    AssistantModeEnum,
    Message,
    MessageTypeEnum,
)
from airbeeps.files.storage import storage_service
from airbeeps.rag.service import RAGService

from .effective_config import resolve_rag_config
from .models import ChatMessage, MessageRole
from .token_utils import get_default_token_counter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from airbeeps.assistants.models import (
        Assistant,
        Conversation,
    )

    from .token_utils import TokenCounter

logger = logging.getLogger(__name__)

_DATA_URL_MARKDOWN_PATTERN = re.compile(
    r"!\[[^\]]*\]\(data:image/[^)]+\)", re.IGNORECASE
)
_DATA_URL_INLINE_PATTERN = re.compile(
    r"data:image/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE
)

_DEFAULT_SKIP_PATTERNS = {
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "ok",
    "okay",
}
_MIN_SMALLTALK_CHARS = 8
_MIN_SMALLTALK_TOKENS = 2

RAG_INSTRUCTIONS = (
    "Here are reference materials from the knowledge base related to the user's question.\n"
    "CITATION FORMAT: You MUST cite sources using ONLY the format [n] where n is the reference number.\n"
    "- Example: 'According to the survey, 1 in 3 users... [2]'\n"
    "- Do NOT use any other citation format like【】, †, L1-L4, or footnotes.\n"
    "- Base your answer only on the provided references.\n"
    "- Do not add details that are not present in the references; if something is missing, say so.\n"
    "- Keep it concise and mirror what the reference states.\n"
    "\nReference Materials:\n{context_text}"
)

RAG_NO_CONTEXT_INSTRUCTIONS = (
    "IMPORTANT: You are operating in RAG (Retrieval-Augmented Generation) mode with a knowledge base.\n"
    "However, no relevant information was found in the knowledge base for the user's question.\n"
    "- You MUST NOT make up or hallucinate information.\n"
    "- You MUST NOT use your training data to answer as if it came from the knowledge base.\n"
    "- Instead, politely inform the user that you could not find relevant information in the knowledge base.\n"
    "- If appropriate, suggest they rephrase their question or check if the relevant documents are in the knowledge base."
)

RAG_SMALLTALK_INSTRUCTIONS = (
    "The user sent a greeting or casual message (like 'hi', 'hello', 'thanks', etc.).\n"
    "You are a knowledge base assistant designed to help users find information from the connected knowledge base.\n"
    "- Respond warmly and briefly to the greeting.\n"
    "- Let the user know you are here to help them with questions related to the knowledge base.\n"
    "- Encourage them to ask a question about the topics covered in the knowledge base.\n"
    "- Keep your response short, friendly, and professional.\n"
    "- Do NOT attempt to retrieve information from the knowledge base for greetings."
)


class PromptBuilder:
    """Builds prompt messages with history, RAG context, and safety limits."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def get_system_prompt(
        self, assistant: Assistant, language: str | None = None
    ) -> str:
        """Get translated system prompt based on language."""
        # Determine language context
        user_lang = language or "en"

        # Normalize language code (e.g., en-US -> en)
        lang_code = user_lang.split("-")[0].lower() if user_lang else "en"

        # Get translated system prompt if available
        system_prompt = assistant.system_prompt or "You are a helpful AI agent."

        if assistant.translations:
            translations = assistant.translations

            # Try exact match first, then language code match
            if user_lang in translations and "system_prompt" in translations[user_lang]:
                system_prompt = translations[user_lang]["system_prompt"]
            elif (
                lang_code in translations and "system_prompt" in translations[lang_code]
            ):
                system_prompt = translations[lang_code]["system_prompt"]

        return system_prompt

    async def build_prompt_messages(
        self,
        conversation: Conversation,
        user_input: str,
        *,
        exclude_message_ids: list[uuid.UUID] | None = None,
        current_images: list[dict[str, Any]] | None = None,
        language: str | None = None,
        include_agent_rag: bool = False,
    ) -> tuple[list[ChatMessage], list[dict[str, Any]]]:
        token_counter = get_default_token_counter()
        model = conversation.assistant.model
        max_context_tokens = model.max_context_tokens or 4096
        max_output_tokens = model.max_output_tokens or 1024

        available_input_tokens = max_context_tokens - max_output_tokens
        safety_ratio = 0.9
        safe_input_tokens = int(available_input_tokens * safety_ratio)

        logger.info(
            "Token budget for conversation %s: max_context=%s, max_output=%s, available_input=%s, safe_input=%s",
            conversation.id,
            max_context_tokens,
            max_output_tokens,
            available_input_tokens,
            safe_input_tokens,
        )

        fixed_messages: list[ChatMessage] = []
        system_parts: list[str] = []

        # Determine language context
        user_lang = language or "en"
        if not language and conversation.user and conversation.user.language:
            user_lang = conversation.user.language

        # Normalize language code (e.g., en-US -> en)
        lang_code = user_lang.split("-")[0].lower() if user_lang else "en"

        logger.info(
            "Building prompt for conversation %s. User lang: %s, Normalized: %s",
            conversation.id,
            user_lang,
            lang_code,
        )

        # Get translated system prompt if available
        system_prompt = conversation.assistant.system_prompt
        if conversation.assistant.translations:
            translations = conversation.assistant.translations
            logger.debug(
                "Assistant translations available: %s", list(translations.keys())
            )

            # Try exact match first, then language code match
            if user_lang in translations and "system_prompt" in translations[user_lang]:
                system_prompt = translations[user_lang]["system_prompt"]
                logger.info(
                    "Using exact match translation for system prompt (%s)", user_lang
                )
            elif (
                lang_code in translations and "system_prompt" in translations[lang_code]
            ):
                system_prompt = translations[lang_code]["system_prompt"]
                logger.info(
                    "Using language code match translation for system prompt (%s)",
                    lang_code,
                )
            else:
                logger.info(
                    "No matching translation found for system prompt, using default"
                )
        if system_prompt:
            system_parts.append(system_prompt)

        rag_citations: list[dict[str, Any]] = []
        should_apply_rag = (
            not conversation.assistant.enable_agent
        ) or include_agent_rag
        if should_apply_rag:
            # Check if assistant is in explicit RAG mode with knowledge bases
            mode = getattr(conversation.assistant, "mode", None)
            knowledge_base_ids = (
                getattr(conversation.assistant, "knowledge_base_ids", None) or []
            )
            is_rag_mode = mode == AssistantModeEnum.RAG and knowledge_base_ids

            # Check for small-talk first (only in RAG mode)
            if is_rag_mode:
                effective_rag = await resolve_rag_config(
                    self.session, conversation.assistant
                )
                smalltalk_guard = {
                    "skip_smalltalk": effective_rag.skip_smalltalk,
                    "skip_patterns": effective_rag.skip_patterns,
                }
                if self._should_skip_smalltalk(user_input, smalltalk_guard):
                    logger.info(
                        "Small-talk detected for conversation %s - adding greeting instruction",
                        conversation.id,
                    )
                    system_parts.append(RAG_SMALLTALK_INSTRUCTIONS)
                else:
                    # Not small-talk, proceed with RAG retrieval
                    rag_context = await self._get_rag_context_content(
                        conversation.assistant, user_input, language=lang_code
                    )
                    if rag_context:
                        context_text, rag_citations = rag_context
                        system_parts.append(context_text)
                    else:
                        logger.info(
                            "RAG mode active but no relevant context found for conversation %s - adding no-context instruction",
                            conversation.id,
                        )
                        system_parts.append(RAG_NO_CONTEXT_INSTRUCTIONS)
            else:
                # Not in RAG mode, try regular RAG context
                rag_context = await self._get_rag_context_content(
                    conversation.assistant, user_input, language=lang_code
                )
                if rag_context:
                    context_text, rag_citations = rag_context
                    system_parts.append(context_text)
        else:
            logger.info(
                "Agent mode enabled - skipping automatic RAG context injection for conversation %s",
                conversation.id,
            )

        if system_parts:
            combined_system_content = "\n\n".join(system_parts)
            fixed_messages.append(
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=combined_system_content,
                )
            )

        if current_images:
            inline_only = self._requires_inline_images(conversation.assistant)
            content_parts: list[dict[str, Any]] = []
            if user_input:
                content_parts.append({"type": "text", "text": user_input})

            for img in current_images:
                image_part = await self._build_image_part(img, inline_only=inline_only)
                if image_part:
                    content_parts.append(image_part)

            if content_parts:
                current_user_message = ChatMessage(
                    role=MessageRole.USER, content=content_parts
                )
                logger.info(
                    "Created multimodal user message with %s images for conversation %s",
                    len(current_images),
                    conversation.id,
                )
            else:
                current_user_message = ChatMessage(
                    role=MessageRole.USER, content=user_input
                )
        else:
            current_user_message = ChatMessage(
                role=MessageRole.USER, content=user_input
            )
        fixed_messages.append(current_user_message)

        fixed_tokens = token_counter.count_messages_tokens(fixed_messages)
        if fixed_tokens > safe_input_tokens:
            raise ValueError(
                f"Input too long: fixed messages use {fixed_tokens} tokens, which exceeds the safe limit of {safe_input_tokens} tokens. "
                "Please reduce the length of your message or system prompt."
            )

        available_history_tokens = safe_input_tokens - fixed_tokens
        logger.info(
            "Fixed messages use %s tokens, available for history: %s tokens",
            fixed_tokens,
            available_history_tokens,
        )

        history_messages = await self._get_conversation_history_with_token_limit(
            conversation,
            available_history_tokens,
            token_counter,
            exclude_message_ids,
        )

        final_messages: list[ChatMessage] = []
        if system_parts:
            final_messages.append(fixed_messages[0])
        final_messages.extend(history_messages)
        final_messages.append(current_user_message)

        total_tokens = 0
        for msg in final_messages:
            if isinstance(msg.content, str):
                total_tokens += token_counter.count_message_tokens(msg)
            else:
                text_parts: list[str] = []
                if isinstance(msg.content, list):
                    for part in msg.content:
                        if isinstance(part, dict) and part.get("text"):
                            text_parts.append(part["text"])
                temp_msg = ChatMessage(
                    role=msg.role, content=" ".join(text_parts) if text_parts else ""
                )
                total_tokens += token_counter.count_message_tokens(temp_msg)

        logger.info(
            "Final prompt for conversation %s: %s messages, %s total tokens (%s/%s budget used)",
            conversation.id,
            len(final_messages),
            total_tokens,
            total_tokens,
            safe_input_tokens,
        )

        logger.debug("Final message sequence for conversation %s:", conversation.id)
        for idx, msg in enumerate(final_messages):
            if isinstance(msg.content, str):
                preview = msg.content[:100] + ("..." if len(msg.content) > 100 else "")
            else:
                preview = f"<multi-modal content with {len(msg.content)} parts>"
            logger.debug("  %s: %s - %s", idx, msg.role.value, preview)

        return final_messages, rag_citations

    async def _get_conversation_history_with_token_limit(
        self,
        conversation: Conversation,
        token_limit: int,
        token_counter: TokenCounter,
        exclude_message_ids: list[uuid.UUID] | None = None,
    ) -> list[ChatMessage]:
        if token_limit <= 0:
            logger.info(
                "No tokens available for history messages (limit: %s)", token_limit
            )
            return []

        max_message_count = conversation.assistant.max_history_messages
        if max_message_count is not None and max_message_count <= 0:
            logger.info(
                "Assistant configured to include no history messages (max_history_messages: %s)",
                max_message_count,
            )
            return []

        query = (
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
        )
        if exclude_message_ids:
            query = query.where(~Message.id.in_(exclude_message_ids))

        result = await self.session.execute(query)
        all_messages = result.scalars().all()

        logger.debug("📚 Fetched %s total messages from database", len(all_messages))

        valid_messages = [
            msg for msg in all_messages if msg.content and msg.content.strip()
        ]
        logger.debug("📝 After filtering empty: %s valid messages", len(valid_messages))

        corrected_messages: list[Message] = []
        i = 0
        while i < len(valid_messages):
            current_msg = valid_messages[i]
            if (
                i + 1 < len(valid_messages)
                and valid_messages[i + 1].created_at == current_msg.created_at
            ):
                next_msg = valid_messages[i + 1]
                if (
                    current_msg.message_type == MessageTypeEnum.ASSISTANT
                    and next_msg.message_type == MessageTypeEnum.USER
                ):
                    corrected_messages.append(next_msg)
                    corrected_messages.append(current_msg)
                    i += 2
                    continue
            corrected_messages.append(current_msg)
            i += 1

        if max_message_count is not None and max_message_count > 0:
            if len(corrected_messages) > max_message_count:
                corrected_messages = corrected_messages[-max_message_count:]

        selected_messages: list[ChatMessage] = []
        current_tokens = 0
        for msg in reversed(corrected_messages):
            role = (
                MessageRole.USER
                if msg.message_type == MessageTypeEnum.USER
                else MessageRole.ASSISTANT
            )

            should_use_multimodal = False
            parts: list[Any] = []
            if role == MessageRole.USER and msg.extra_data:
                images_payload = msg.extra_data.get("images")
                if images_payload:
                    inline_only = self._requires_inline_images(conversation.assistant)
                    for image in images_payload:
                        image_part = await self._build_image_part(
                            image, inline_only=inline_only
                        )
                        if image_part:
                            if not should_use_multimodal:
                                parts = []
                                should_use_multimodal = True
                            parts.append(image_part)

            if should_use_multimodal:
                content_parts: list[Any] = []
                if role == MessageRole.USER and msg.content and msg.content.strip():
                    content_parts.append({"type": "text", "text": msg.content.strip()})
                content_parts.extend(parts)
                chat_message = ChatMessage(role=role, content=content_parts)
                logger.debug(
                    "Restored multimodal message with %s parts (role=%s)",
                    len(content_parts),
                    role,
                )
                text_for_counting = (
                    msg.content.strip()
                    if msg.content and msg.content.strip()
                    else "[image]"
                )
                sanitized = self._sanitize_content_for_prompt(text_for_counting)
                temp_message = ChatMessage(role=role, content=sanitized)
                message_tokens = token_counter.count_message_tokens(temp_message)
            else:
                if not msg.content or not msg.content.strip():
                    continue
                sanitized = self._sanitize_content_for_prompt(msg.content.strip())
                chat_message = ChatMessage(role=role, content=sanitized)
                message_tokens = token_counter.count_message_tokens(chat_message)

            if current_tokens + message_tokens > token_limit:
                logger.info(
                    "Token limit reached. Stopping at %s messages (current: %s, would be: %s, limit: %s)",
                    len(selected_messages),
                    current_tokens,
                    current_tokens + message_tokens,
                    token_limit,
                )
                break

            selected_messages.append(chat_message)
            current_tokens += message_tokens
            logger.debug(
                "Added message %s: %s tokens (total: %s/%s)",
                len(selected_messages),
                message_tokens,
                current_tokens,
                token_limit,
            )

        final_messages = list(reversed(selected_messages))
        logger.info(
            "Selected %s history messages using %s/%s tokens",
            len(final_messages),
            current_tokens,
            token_limit,
        )
        return final_messages

    def _requires_inline_images(self, assistant: Assistant) -> bool:
        """Determine if downstream provider expects inline image payloads.

        LiteLLM handles image format conversion for all providers,
        so we default to URL-based images which are more efficient.
        """
        return False

    async def _build_image_part(
        self,
        image: dict[str, Any],
        *,
        inline_only: bool,
    ) -> dict[str, Any] | None:
        if not isinstance(image, dict):
            return None

        mime_value = (
            image.get("mime_type")
            or image.get("mimeType")
            or image.get("content_type")
            or image.get("contentType")
        )
        alt_text = image.get("alt")

        if inline_only:
            inline_url = await self._ensure_inline_data_url(
                image, fallback_mime=mime_value
            )
            if not inline_url:
                logger.warning(
                    "Unable to generate inline data for image, skipping this attachment"
                )
                return None
            entry: dict[str, Any] = {
                "type": "image_url",
                "image_url": {"url": inline_url},
            }
        else:
            source_url = image.get("url")
            if not source_url:
                file_key = self._resolve_file_key(image)
                if file_key:
                    try:
                        source_url = await storage_service.get_public_url(file_key)
                    except Exception as exc:
                        logger.warning(
                            "Failed to get image URL (%s): %s", file_key, exc
                        )
                        source_url = None
            if not source_url:
                inline_url = image.get("data_url") or image.get("dataUrl")
                if inline_url:
                    source_url = inline_url
            if not source_url:
                logger.warning("Image missing available URL, skipping this attachment")
                return None
            entry = {"type": "image_url", "image_url": {"url": source_url}}

        if inline_only:
            if mime_value:
                entry["mime_type"] = mime_value
            if alt_text:
                entry["alt"] = alt_text
        return entry

    async def _ensure_inline_data_url(
        self,
        image: dict[str, Any],
        *,
        fallback_mime: str | None = None,
    ) -> str | None:
        existing = image.get("data_url") or image.get("dataUrl")
        if existing and existing.startswith("data:"):
            return existing

        source_url = image.get("url")
        if source_url and source_url.startswith("data:"):
            return source_url

        file_key = self._resolve_file_key(image)
        if not file_key:
            logger.warning("Unable to locate image file, cannot convert to base64")
            return None

        try:
            file_obj, content_type = await storage_service.download_file(file_key)
        except Exception as exc:
            logger.warning("Failed to download image (%s): %s", file_key, exc)
            return None

        data = file_obj.getvalue()
        mime_type = fallback_mime or content_type or "application/octet-stream"
        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    def _resolve_file_key(self, image: dict[str, Any]) -> str | None:
        direct_key = (
            image.get("file_key")
            or image.get("fileKey")
            or image.get("file_path")
            or image.get("filePath")
        )
        if direct_key:
            return direct_key

        url = image.get("url")
        if not url:
            return None

        candidates = [
            storage_service.external_endpoint_url,
            storage_service.endpoint_url,
        ]
        for base in candidates:
            if not base:
                continue
            normalized = base.rstrip("/") + "/"
            if url.startswith(normalized):
                return url[len(normalized) :]

        parsed = urlparse(url)
        return parsed.path.lstrip("/") or None

    async def _get_rag_context_content(
        self,
        assistant: Assistant,
        user_query: str,
        language: str = "en",
    ) -> tuple[str, list[dict[str, Any]]] | None:
        # RAG is only applied in explicit RAG mode.
        # (If mode is missing, fall back to legacy behavior: allow RAG when KBs are attached.)
        mode = getattr(assistant, "mode", None)
        if mode is not None and mode != AssistantModeEnum.RAG:
            return None

        knowledge_base_ids = getattr(assistant, "knowledge_base_ids", None) or []
        if not knowledge_base_ids:
            return None

        effective_rag = await resolve_rag_config(self.session, assistant)
        smalltalk_guard = {
            "skip_smalltalk": effective_rag.skip_smalltalk,
            "skip_patterns": effective_rag.skip_patterns,
        }
        if self._should_skip_smalltalk(user_query, smalltalk_guard):
            logger.info(
                "Skipping RAG for small-talk query on assistant %s", assistant.id
            )
            return None
        retrieval_count = effective_rag.retrieval_count
        fetch_k = effective_rag.fetch_k or max(retrieval_count * 3, retrieval_count)
        score_threshold = effective_rag.similarity_threshold
        search_type = effective_rag.search_type or "similarity"
        mmr_lambda = effective_rag.mmr_lambda or 0.5
        context_max_tokens = effective_rag.context_max_tokens or 1200

        rag_service = RAGService(self.session)
        token_counter = get_default_token_counter()
        candidates: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []

        for raw_kb_id in knowledge_base_ids:
            try:
                kb_uuid = (
                    raw_kb_id
                    if isinstance(raw_kb_id, uuid.UUID)
                    else uuid.UUID(str(raw_kb_id))
                )
            except Exception:
                logger.warning(
                    "Invalid knowledge base ID '%s' configured on assistant %s",
                    raw_kb_id,
                    assistant.id,
                )
                continue

            try:
                relevance_docs = await rag_service.relevance_search(
                    query=user_query,
                    knowledge_base_id=kb_uuid,
                    k=retrieval_count,
                    fetch_k=fetch_k,
                    score_threshold=score_threshold,
                    search_type=search_type,
                    mmr_lambda=mmr_lambda,
                    multi_query=effective_rag.multi_query,
                    multi_query_count=effective_rag.multi_query_count,
                    rerank_top_k=effective_rag.rerank_top_k,
                    rerank_model_id=effective_rag.rerank_model_id,
                    hybrid_enabled=effective_rag.hybrid_enabled,
                    hybrid_corpus_limit=effective_rag.hybrid_corpus_limit,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to retrieve RAG context for assistant %s (KB %s): %s",
                    assistant.id,
                    kb_uuid,
                    exc,
                )
                continue

            for doc in relevance_docs:
                metadata = doc.metadata or {}
                title = metadata.get("title", "Untitled Document")
                content = doc.page_content or ""
                norm = content.strip()
                if not norm:
                    continue
                token_count = token_counter.count_text_tokens(norm)
                score = metadata.get("score") or metadata.get("similarity")
                chunk_id = metadata.get("chunk_id") or metadata.get("id")
                # sha1 is used for deduplication only, not cryptographic purposes
                hash_key = hashlib.sha1(norm.lower().encode("utf-8")).hexdigest()  # noqa: S324
                candidates.append(
                    {
                        "content": norm,
                        "title": title,
                        "metadata": metadata,
                        "score": score,
                        "token_count": token_count,
                        "chunk_id": chunk_id,
                        "hash": hash_key,
                    }
                )

        if not candidates:
            return None

        # Deduplicate by chunk_id then by content hash
        seen_chunks = set()
        seen_hashes = set()
        deduped: list[dict[str, Any]] = []
        for c in candidates:
            if c["chunk_id"] and c["chunk_id"] in seen_chunks:
                continue
            if c["hash"] in seen_hashes:
                continue
            if c["chunk_id"]:
                seen_chunks.add(c["chunk_id"])
            seen_hashes.add(c["hash"])
            deduped.append(c)

        # Sort by score desc (None last), then by shorter token_count
        deduped.sort(
            key=lambda item: (
                item["score"] is None,
                -(item["score"] or 0),
                item["token_count"],
            )
        )

        # Enforce context token budget
        remaining_tokens = context_max_tokens
        selected_entries: list[dict[str, Any]] = []
        entry_index = 1
        for item in deduped:
            if remaining_tokens <= 0:
                break
            content = item["content"]
            tok_count = item["token_count"]
            if tok_count > remaining_tokens:
                content = self._truncate_to_tokens(content, remaining_tokens)
                tok_count = token_counter.count_text_tokens(content)
                if tok_count == 0:
                    continue
            selected_entries.append(
                {
                    "index": entry_index,
                    "content": content,
                    "title": item["title"],
                    "metadata": item["metadata"],
                    "score": item["score"],
                    "snippet": content[:400] + ("..." if len(content) > 400 else ""),
                }
            )
            entry_index += 1
            remaining_tokens -= tok_count

        if not selected_entries:
            return None

        context_entries: list[str] = []
        citations: list[dict[str, Any]] = []
        for entry in selected_entries:
            context_entries.append(
                f"[{entry['index']}] {entry['title']}\n{entry['content']}"
            )
            citations.append(
                {
                    "index": entry["index"],
                    "title": entry["title"],
                    "display_name": entry["metadata"].get("display_name")
                    or entry["title"],
                    "snippet": entry["snippet"],
                    "document_id": entry["metadata"].get("document_id"),
                    "file_path": entry["metadata"].get("file_path"),
                    "file_type": entry["metadata"].get("file_type"),
                    "source_url": entry["metadata"].get("source_url"),
                    "sheet": entry["metadata"].get("sheet"),
                    "row_number": entry["metadata"].get("row_number"),
                    "score": entry["score"],
                    "metadata": entry["metadata"],
                }
            )

        context_text = "\n\n".join(context_entries)

        instructions = RAG_INSTRUCTIONS.format(context_text=context_text)
        return instructions, citations

    def _should_skip_smalltalk(
        self, user_query: str, rag_config: dict[str, Any]
    ) -> bool:
        """Heuristic guard to bypass RAG for greetings/acks."""
        if not rag_config.get("skip_smalltalk"):
            return False

        norm = (user_query or "").strip().lower()
        if not norm:
            return True

        patterns = rag_config.get("skip_patterns") or _DEFAULT_SKIP_PATTERNS
        normalized_patterns = {p.strip().lower() for p in patterns if p and p.strip()}

        # Direct match or startswith match (e.g., "hi there")
        if norm in normalized_patterns:
            return True
        if any(norm.startswith(f"{pat} ") for pat in normalized_patterns):
            return True

        # Very short inputs with few tokens are treated as small-talk
        return bool(
            len(norm) < _MIN_SMALLTALK_CHARS
            or len(norm.split()) <= _MIN_SMALLTALK_TOKENS
        )

    @staticmethod
    def _sanitize_content_for_prompt(content: str | None) -> str:
        if not content:
            return ""
        if not isinstance(content, str):
            logger.debug(
                "_sanitize_content_for_prompt received non-string content of type %s",
                type(content),
            )
            try:
                content = str(content)
            except Exception:
                return ""

        try:
            sanitized = _DATA_URL_MARKDOWN_PATTERN.sub(
                "[Image content omitted]", content
            )
            sanitized = _DATA_URL_INLINE_PATTERN.sub("[Image data omitted]", sanitized)
        except TypeError as exc:
            logger.warning(
                "Unable to sanitize message content (type=%s): %s", type(content), exc
            )
            return content

        return sanitized

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text or "")
        if len(tokens) <= max_tokens:
            return text
        return encoding.decode(tokens[:max_tokens])
