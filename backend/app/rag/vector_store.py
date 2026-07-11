"""Milvus vector store — RAG retrieval for KnowledgeAgent.

Milvus is an open-source vector database optimized for similarity search
at scale. This module provides connection management, document indexing,
and semantic search against the enterprise IT knowledge base.
"""

from typing import Optional

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)
from pymilvus.client.types import SearchResult

from app.core.config import settings

# Milvus uses a connection alias; we manage a singleton connection
_CONNECTION_ALIAS = "cyberbuddy_milvus"
_collection: Optional[Collection] = None


def _connect() -> None:
    """Establish connection to Milvus if not already connected."""
    if not connections.has_connection(_CONNECTION_ALIAS):
        connections.connect(
            alias=_CONNECTION_ALIAS,
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
        )


def _get_collection() -> Collection:
    """Get or create the IT knowledge base collection."""
    global _collection
    _connect()

    if _collection is not None:
        return _collection

    collection_name = settings.MILVUS_COLLECTION_NAME

    if utility.has_collection(collection_name, using=_CONNECTION_ALIAS):
        _collection = Collection(collection_name, using=_CONNECTION_ALIAS)
        _collection.load()
        return _collection

    # Define schema: id (PK), embedding (vector), text (scalar), metadata (JSON)
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.MILVUS_DIMENSION),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="metadata", dtype=DataType.JSON),
    ]
    schema = CollectionSchema(fields, description="企业IT手册与安全合规制度")
    _collection = Collection(collection_name, schema=schema, using=_CONNECTION_ALIAS)

    # Create IVF_FLAT index for fast approximate search
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    _collection.create_index(field_name="embedding", index_params=index_params)
    _collection.load()

    return _collection


async def search_knowledge_base(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    """Search the IT knowledge base by vector similarity.

    Args:
        query_embedding: The embedding vector of the user query.
        top_k: Number of top results to return.

    Returns:
        List of dicts with keys: text, score, metadata.
    """
    collection = _get_collection()

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
    results: list[SearchResult] = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        output_fields=["text", "metadata"],
    )

    if not results:
        return []

    return [
        {
            "text": hit.entity.get("text", ""),
            "score": hit.score,
            "metadata": hit.entity.get("metadata", {}),
        }
        for hit in results[0]
    ]


async def index_documents(
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict] | None = None,
) -> int:
    """Index new documents into the knowledge base.

    Args:
        embeddings: Pre-computed embedding vectors, one per document.
        documents: Document text strings.
        metadatas: Optional metadata dict for each document.

    Returns:
        Number of documents indexed.
    """
    if not documents:
        return 0

    collection = _get_collection()
    metadatas = metadatas or [{}] * len(documents)

    entities = [
        documents,
        embeddings,
        metadatas,
    ]

    collection.insert(entities)
    collection.flush()

    return len(documents)
