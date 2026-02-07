"""
Catalog of recommended HuggingFace embedding models for local use.

These are curated models that work well with sentence-transformers
and are suitable for RAG/embedding tasks.
"""

# Recommended embedding models for local use
# Sorted by size (smallest first)
RECOMMENDED_HF_EMBEDDINGS = [
    {
        "id": "sentence-transformers/all-MiniLM-L6-v2",
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "display_name": "All-MiniLM-L6-v2",
        "size_mb": 90,
        "dimensions": 384,
        "description": "Very fast and compact - great for testing",
        "recommended_for": "Quick prototyping, low-resource environments",
    },
    {
        "id": "BAAI/bge-small-en-v1.5",
        "name": "BAAI/bge-small-en-v1.5",
        "display_name": "BGE Small EN v1.5",
        "size_mb": 130,
        "dimensions": 384,
        "description": "Lightweight with good quality - excellent balance",
        "recommended_for": "Production use, good speed/quality tradeoff",
    },
    {
        "id": "sentence-transformers/all-mpnet-base-v2",
        "name": "sentence-transformers/all-mpnet-base-v2",
        "display_name": "All-MPNet-Base-v2",
        "size_mb": 420,
        "dimensions": 768,
        "description": "High quality general-purpose embeddings",
        "recommended_for": "Best quality for general text",
    },
    {
        "id": "BAAI/bge-base-en-v1.5",
        "name": "BAAI/bge-base-en-v1.5",
        "display_name": "BGE Base EN v1.5",
        "size_mb": 440,
        "dimensions": 768,
        "description": "Balanced speed and quality",
        "recommended_for": "Production use, good overall performance",
    },
    {
        "id": "BAAI/bge-large-en-v1.5",
        "name": "BAAI/bge-large-en-v1.5",
        "display_name": "BGE Large EN v1.5",
        "size_mb": 1340,
        "dimensions": 1024,
        "description": "Best quality, slower inference",
        "recommended_for": "Maximum quality, when speed is less critical",
    },
    {
        "id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "display_name": "Paraphrase Multilingual MiniLM",
        "size_mb": 470,
        "dimensions": 384,
        "description": "Supports 50+ languages",
        "recommended_for": "Multilingual applications",
    },
    {
        "id": "intfloat/e5-small-v2",
        "name": "intfloat/e5-small-v2",
        "display_name": "E5 Small v2",
        "size_mb": 130,
        "dimensions": 384,
        "description": "Text embeddings by instruct, small size",
        "recommended_for": "Efficient embeddings with good performance",
    },
    {
        "id": "intfloat/e5-base-v2",
        "name": "intfloat/e5-base-v2",
        "display_name": "E5 Base v2",
        "size_mb": 440,
        "dimensions": 768,
        "description": "Text embeddings by instruct, base size",
        "recommended_for": "Strong general-purpose embeddings",
    },
    {
        "id": "intfloat/e5-large-v2",
        "name": "intfloat/e5-large-v2",
        "display_name": "E5 Large v2",
        "size_mb": 1340,
        "dimensions": 1024,
        "description": "Text embeddings by instruct, large size",
        "recommended_for": "Best E5 quality",
    },
]


def get_recommended_embeddings() -> list[dict]:
    """Get list of recommended embedding models."""
    return RECOMMENDED_HF_EMBEDDINGS.copy()


def get_embedding_by_id(model_id: str) -> dict | None:
    """Get embedding model info by ID."""
    for model in RECOMMENDED_HF_EMBEDDINGS:
        if model["id"] == model_id:
            return model.copy()
    return None


def is_recommended_embedding(model_id: str) -> bool:
    """Check if a model ID is in the recommended list."""
    return any(m["id"] == model_id for m in RECOMMENDED_HF_EMBEDDINGS)
