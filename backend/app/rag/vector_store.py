"""ChromaDB vector store — RAG retrieval for KnowledgeAgent."""

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings


# Global ChromaDB client (initialized on first use)
_client: chromadb.PersistentClient | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Get or create the persistent ChromaDB client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_knowledge_collection() -> chromadb.Collection:
    """Get or create the IT knowledge base collection."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"description": "企业IT手册与安全合规制度"}
    )


async def search_knowledge_base(query: str, top_k: int = 5) -> list[str]:
    """Search the IT knowledge base for relevant documents.

    Args:
        query: The user's search query.
        top_k: Number of top results to return.

    Returns:
        List of document text strings ranked by relevance.
    """
    collection = get_knowledge_collection()
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    documents = results.get("documents", [[]])[0]
    return [doc for doc in documents if doc]


async def index_documents(documents: list[str], metadatas: list[dict] | None = None) -> int:
    """Index new documents into the knowledge base.

    Args:
        documents: List of document text strings.
        metadatas: Optional metadata for each document.

    Returns:
        Number of documents indexed.
    """
    if not documents:
        return 0

    collection = get_knowledge_collection()
    ids = [f"doc_{i}" for i in range(collection.count(), collection.count() + len(documents))]

    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )
    return len(documents)
