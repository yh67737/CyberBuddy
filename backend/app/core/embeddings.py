"""Embedding service — local BGE model for RAG retrieval.

Uses BAAI/bge-large-zh-v1.5 via HuggingFace sentence-transformers for Chinese
IT knowledge base retrieval. The model is downloaded and cached locally on
first use (~1.3 GB). No external API key required.

Used by KnowledgeAgent to embed user queries and by the document ingestion
pipeline to index knowledge articles into Milvus.
"""

from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import settings


class EmbeddingService:
    """Local embedding service using BGE-large-zh-v1.5.

    Model is auto-downloaded from HuggingFace Hub on first instantiation and
    cached under ~/.cache/huggingface/hub/ for subsequent use.

    BGE model specifics:
      - Dimension: 1024
      - Max sequence length: 512 tokens
      - Recommended: normalize embeddings, prefix queries for retrieval
    """

    def __init__(
        self,
        model_name: str | None = None,
    ) -> None:
        model = model_name or settings.EMBEDDING_MODEL
        self._model_name = model

        # HuggingFaceEmbeddings wraps sentence-transformers.
        # model_kwargs: 'device' defaults to CPU; set to 'cuda' for GPU.
        # encode_kwargs: 'normalize_embeddings' — BGE models recommend normalization.
        self._embeddings = HuggingFaceEmbeddings(
            model_name=model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string.

        BGE models perform best when queries are prefixed with
        '为这个句子生成表示以用于检索相关文章：' for Chinese retrieval tasks.
        """
        return await self._run_sync(self._embeddings.embed_query, text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks for indexing into Milvus.

        BGE documents should NOT be prefixed — the model treats raw passages
        as documents and prefixed queries as queries differently.
        """
        return await self._run_sync(self._embeddings.embed_documents, texts)

    async def _run_sync(self, func, *args):
        """Run a synchronous call in a thread to avoid blocking the event loop."""
        import asyncio

        return await asyncio.to_thread(func, *args)

    @property
    def dimension(self) -> int:
        """Return the actual embedding vector dimension from the loaded model.

        For BAAI/bge-large-zh-v1.5 this is 1024.
        """
        # Get the underlying sentence-transformers model's embedding dimension
        return self._embeddings._client.get_embedding_dimension()


# Module-level singleton — created on first access
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Return the singleton EmbeddingService, downloading the model on first call."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
