"""Milvus vector store — RAG retrieval for KnowledgeAgent.

Milvus is an open-source vector database optimized for similarity search
at scale. This module provides connection management, document indexing,
and semantic search against the enterprise IT knowledge base.

Two collections are managed:
  - ``it_knowledge``: enterprise IT manuals & policy documents (text + metadata)
  - ``qa_pairs``: IT support Q&A pairs imported from external datasets
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

from app.core.config import settings

# Milvus uses a connection alias; we manage a singleton connection
_CONNECTION_ALIAS = "cyberbuddy_milvus"
_collection: Optional[Collection] = None
_qa_collection: Optional[Collection] = None
_violations_collection: Optional[Collection] = None

# ── QA pair collection constants ────────────────────────────────────
QA_COLLECTION_NAME = "qa_pairs"
VIOLATIONS_COLLECTION_NAME = "security_violations"
MAX_VARCHAR = 65535
# Fields stored in the QA collection (beyond id + embedding)
QA_SCALAR_FIELDS = [
    "qa_text",       # combined "Q: ...\nA: ..." (embedded)
    "question",       # original question
    "answer",         # original answer
    "source",         # IBM_TechQA | IEEE_IT_Support | StackExchange
    "tags",           # JSON array string: '["windows","wsl"]'
    "date",           # YYYY-MM-DD
    "site",           # stackexchange site slug or empty
    "score",          # vote / quality score
    "is_accepted",    # whether answer was accepted (StackExchange)
    "url",            # original URL or empty
]


def _connect() -> None:
    """Establish connection to Milvus if not already connected."""
    if not connections.has_connection(_CONNECTION_ALIAS):
        connections.connect(
            alias=_CONNECTION_ALIAS,
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
        )


def _get_collection() -> Collection:
    """Get or create the IT knowledge base collection (document chunks)."""
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
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=MAX_VARCHAR),
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


def _get_qa_collection() -> Collection:
    """Get or create the QA-pair collection for IT support Q&A datasets.

    Schema includes explicit scalar fields for question, answer, source,
    tags, date, site, score, is_accepted, and url so that searches can
    filter on these dimensions (e.g. "only stackexchange", "2024+").

    The ``qa_text`` field holds the concatenated question+answer text and
    is what gets embedded — the same text the user sees in results.
    """
    global _qa_collection
    _connect()

    if _qa_collection is not None:
        return _qa_collection

    if utility.has_collection(QA_COLLECTION_NAME, using=_CONNECTION_ALIAS):
        _qa_collection = Collection(QA_COLLECTION_NAME, using=_CONNECTION_ALIAS)
        _qa_collection.load()
        return _qa_collection

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.MILVUS_DIMENSION),
        FieldSchema(name="qa_text", dtype=DataType.VARCHAR, max_length=MAX_VARCHAR),
        FieldSchema(name="question", dtype=DataType.VARCHAR, max_length=MAX_VARCHAR),
        FieldSchema(name="answer", dtype=DataType.VARCHAR, max_length=MAX_VARCHAR),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="tags", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="date", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="site", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="score", dtype=DataType.FLOAT),
        FieldSchema(name="is_accepted", dtype=DataType.BOOL),
        FieldSchema(name="url", dtype=DataType.VARCHAR, max_length=2048),
    ]
    schema = CollectionSchema(fields, description="IT支持问答对 (TechQA + IEEE + StackExchange)")
    _qa_collection = Collection(QA_COLLECTION_NAME, schema=schema, using=_CONNECTION_ALIAS)

    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    _qa_collection.create_index(field_name="embedding", index_params=index_params)
    _qa_collection.load()

    return _qa_collection


async def search_knowledge_base(
    query_embedding: list[float],
    top_k: int = 5,
    min_score: float = 0.5,
) -> list[dict]:
    """Search the IT knowledge base by vector similarity.

    Args:
        query_embedding: The embedding vector of the user query.
        top_k: Number of top results to return.
        min_score: Minimum COSINE similarity score (0.0–1.0).

    Returns:
        List of dicts with keys: text, score, metadata.
    """
    collection = _get_collection()

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
    results = collection.search(
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
        if hit.score >= min_score
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

    # Column order: embedding, text, metadata (id is auto_id)
    entities = [
        embeddings,
        documents,
        metadatas,
    ]

    collection.insert(entities)
    collection.flush()

    return len(documents)


# ── QA Pair operations ────────────────────────────────────────────────

async def search_qa_pairs(
    query_embedding: list[float],
    top_k: int = 5,
    min_score: float = 0.5,
    source_filter: str | None = None,
    site_filter: str | None = None,
) -> list[dict]:
    """Search the IT support Q&A knowledge base by vector similarity.

    Args:
        query_embedding: The embedding vector of the user query.
        top_k: Number of top results to return.
        min_score: Minimum COSINE similarity score (0.0–1.0). Results below
            this threshold are discarded.  Default 0.5 — tuned for BGE
            embeddings where < 0.4 is usually noise.
        source_filter: Optional filter by source (e.g. ``"StackExchange"``).
        site_filter: Optional filter by site (e.g. ``"superuser"``).

    Returns:
        List of dicts with keys matching all QA scalar fields plus ``score``.
    """
    collection = _get_qa_collection()

    # Build optional scalar filter expression
    conditions = []
    if source_filter:
        conditions.append(f'source == "{source_filter}"')
    if site_filter:
        conditions.append(f'site == "{site_filter}"')
    expr = " && ".join(conditions) if conditions else None

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        expr=expr,
        output_fields=QA_SCALAR_FIELDS,
    )

    if not results:
        return []

    return [
        {
            **{field: hit.entity.get(field, "") for field in QA_SCALAR_FIELDS},
            "score": hit.score,
        }
        for hit in results[0]
        if hit.score >= min_score
    ]


async def index_qa_pairs(
    embeddings: list[list[float]],
    qa_texts: list[str],
    questions: list[str],
    answers: list[str],
    sources: list[str],
    tags_list: list[str],
    dates: list[str],
    sites: list[str],
    scores: list[float],
    is_accepteds: list[bool],
    urls: list[str],
) -> int:
    """Index IT support Q&A pairs into the QA collection.

    Each argument is a list of the same length representing one scalar
    column.  ``qa_texts`` is the concatenated ``question + answer`` and
    is what gets embedded for similarity search.
    """
    n = len(qa_texts)
    if n == 0:
        return 0

    collection = _get_qa_collection()

    # Column order must match schema: id(auto), embedding, qa_text,
    # question, answer, source, tags, date, site, score, is_accepted, url
    entities = [
        embeddings,
        qa_texts,
        questions,
        answers,
        sources,
        tags_list,
        dates,
        sites,
        scores,
        is_accepteds,
        urls,
    ]

    collection.insert(entities)
    collection.flush()

    return n


def get_qa_collection_stats() -> dict:
    """Return row count and load state for the QA collection."""
    try:
        _connect()
        if utility.has_collection(QA_COLLECTION_NAME, using=_CONNECTION_ALIAS):
            col = Collection(QA_COLLECTION_NAME, using=_CONNECTION_ALIAS)
            col.load()
            return {
                "name": QA_COLLECTION_NAME,
                "num_entities": col.num_entities,
                "loaded": True,
            }
        return {"name": QA_COLLECTION_NAME, "num_entities": 0, "loaded": False}
    except Exception as e:
        return {"name": QA_COLLECTION_NAME, "num_entities": 0, "loaded": False, "error": str(e)}


# ── Security violations operations ────────────────────────────────────

def _get_violations_collection() -> Collection:
    """Get or create the security-violations catalogue collection.

    Each row is one employee example phrase (``phrase``) mapped to the
    canonical violation name (``violation``) and severity (``severity``) it
    represents.  SecurityGuardian searches this to ground its severity
    judgement in policy when a user's report matches a known phrase.
    """
    global _violations_collection
    _connect()

    if _violations_collection is not None:
        return _violations_collection

    if utility.has_collection(VIOLATIONS_COLLECTION_NAME, using=_CONNECTION_ALIAS):
        _violations_collection = Collection(VIOLATIONS_COLLECTION_NAME, using=_CONNECTION_ALIAS)
        _violations_collection.load()
        return _violations_collection

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.MILVUS_DIMENSION),
        FieldSchema(name="phrase", dtype=DataType.VARCHAR, max_length=MAX_VARCHAR),
        FieldSchema(name="violation", dtype=DataType.VARCHAR, max_length=MAX_VARCHAR),
        FieldSchema(name="severity", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=32),
    ]
    schema = CollectionSchema(fields, description="安全违规条目库 (示例提问 → 违规名称 + 风险等级)")
    _violations_collection = Collection(VIOLATIONS_COLLECTION_NAME, schema=schema, using=_CONNECTION_ALIAS)

    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    _violations_collection.create_index(field_name="embedding", index_params=index_params)
    _violations_collection.load()

    return _violations_collection


async def search_violations(
    query_embedding: list[float],
    top_k: int = 3,
    min_score: float = 0.5,
) -> list[dict]:
    """Search the violation catalogue by similarity to an employee phrase.

    Returns matches carrying the canonical ``violation`` name and ``severity``
    so the caller can ground a risk judgement in policy.

    Note: an empty result is **not** evidence of no risk — callers must fall
    back to general knowledge rather than treating a miss as "no issue".
    """
    collection = _get_violations_collection()

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        output_fields=["phrase", "violation", "severity", "category"],
    )

    if not results:
        return []

    return [
        {
            "phrase": hit.entity.get("phrase", ""),
            "violation": hit.entity.get("violation", ""),
            "severity": hit.entity.get("severity", ""),
            "category": hit.entity.get("category", ""),
            "score": hit.score,
        }
        for hit in results[0]
        if hit.score >= min_score
    ]
