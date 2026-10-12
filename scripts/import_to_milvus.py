#!/usr/bin/env python3
"""
Import IT support Q&A pairs into Milvus for RAG retrieval.

Reads all data files (TechQA, IEEE, StackExchange), generates embeddings
for question+answer text using BAAI/bge-large-zh-v1.5, and indexes into
the Milvus ``qa_pairs`` collection.

Embedding strategy:
  - Concatenate ``question + "\\n\\n" + answer`` → one text per row
  - Embed the concatenated text → 1024-dim FLOAT_VECTOR
  - Store all original fields as scalar columns for retrieval

Usage:
    python scripts/import_to_milvus.py
    python scripts/import_to_milvus.py --batch-size 200 --limit 1000
    python scripts/import_to_milvus.py --dry-run        # validate data only
    python scripts/import_to_milvus.py --stats           # show collection stats

Environment:
    MILVUS_HOST  — Milvus server host (default: localhost)
    MILVUS_PORT  — Milvus gRPC port  (default: 19530)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# ── Constants ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = PROJECT_ROOT / "data"
COLLECTION_NAME = "qa_pairs"
DIMENSION = 1024
MAX_VARCHAR = 65535
CONNECTION_ALIAS = "cyberbuddy_import"

# Data files to import (each with format: list of QA dicts)
DATA_FILES = [
    "techqa_answerable.json",
    "ieee_it_support.json",
    "stackexchange_it_qa.json",  # merged file (7,664 pairs)
]

# Milvus scalar fields (beyond id + embedding)
QA_SCALAR_FIELDS = [
    "qa_text",
    "question",
    "answer",
    "source",
    "tags",
    "date",
    "site",
    "score",
    "is_accepted",
    "url",
]


# ── Schema helpers ────────────────────────────────────────────────────
def connect_milvus(host: str, port: int) -> None:
    """Connect to Milvus and ensure QA collection exists."""
    from pymilvus import (
        Collection,
        CollectionSchema,
        connections,
        DataType,
        FieldSchema,
        utility,
    )

    if connections.has_connection(CONNECTION_ALIAS):
        return

    connections.connect(alias=CONNECTION_ALIAS, host=host, port=port)
    print(f"🔗 Connected to Milvus at {host}:{port}")

    if utility.has_collection(COLLECTION_NAME, using=CONNECTION_ALIAS):
        col = Collection(COLLECTION_NAME, using=CONNECTION_ALIAS)
        col.load()
        print(f"📦 Collection '{COLLECTION_NAME}' exists: {col.num_entities:,} entities")
        # Ask user if they want to drop
        if col.num_entities > 0:
            resp = input(f"\n⚠️  Collection already has {col.num_entities:,} rows. Drop & recreate? [y/N]: ")
            if resp.lower() == "y":
                utility.drop_collection(COLLECTION_NAME, using=CONNECTION_ALIAS)
                print("🗑️  Dropped. Will recreate on next insert.")
            else:
                print("⏩ Keeping existing data (new rows will be appended).")
        return

    # Create collection
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIMENSION),
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
    schema = CollectionSchema(fields, description="IT支持问答对 RAG 知识库")
    col = Collection(COLLECTION_NAME, schema=schema, using=CONNECTION_ALIAS)

    # IVF_FLAT index with COSINE
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    col.create_index(field_name="embedding", index_params=index_params)
    col.load()
    print(f"📦 Created collection '{COLLECTION_NAME}' with IVF_FLAT/COSINE index")


# ── Data loading ──────────────────────────────────────────────────────
def _truncate(text: str, max_len: int = MAX_VARCHAR) -> str:
    """Truncate text to fit Milvus VARCHAR field."""
    if len(text) <= max_len:
        return text
    print(f"  ⚠️  Truncating text from {len(text):,} to {max_len:,} chars")
    return text[:max_len]


def load_all_qa_pairs(limit: Optional[int] = None) -> list[dict]:
    """Load all QA pairs from data files with unified schema.

    Returns a list of dicts, each with keys matching the Milvus scalar fields
    (plus ``qa_text`` which is derived from question + answer).
    """
    all_pairs = []
    skipped = 0

    for filename in DATA_FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            # Try per-site SE files if merged file is missing
            if filename == "stackexchange_it_qa.json":
                se_pairs = _load_stackexchange_files()
                all_pairs.extend(se_pairs)
                continue
            print(f"  ⚠️  Skipping missing file: {filepath}")
            continue

        print(f"📖 Loading {filename} ...")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            qa_text = f"{item.get('question', '')}\n\n{item.get('answer', '')}".strip()
            if len(qa_text) < 50:
                skipped += 1
                continue

            # Determine source label
            src = item.get("source", "")
            if not src:
                src = "Unknown"

            # Tags: list → JSON string, truncated if needed
            tags_raw = item.get("tags", [])
            if isinstance(tags_raw, list):
                tags_str = json.dumps(tags_raw, ensure_ascii=False)
            elif isinstance(tags_raw, str):
                tags_str = tags_raw
            else:
                tags_str = ""

            all_pairs.append({
                "qa_text": _truncate(qa_text),
                "question": _truncate(item.get("question", "")),
                "answer": _truncate(item.get("answer", "")),
                "source": src[:128],
                "tags": tags_str[:4096],
                "date": str(item.get("date", ""))[:32],
                "site": str(item.get("site", ""))[:64],
                "score": float(item.get("score", item.get("answer_score", 0))),
                "is_accepted": bool(item.get("is_accepted", False)),
                "url": str(item.get("url", ""))[:2048],
            })

            if limit and len(all_pairs) >= limit:
                break

        if limit and len(all_pairs) >= limit:
            break

    print(f"✅ Loaded {len(all_pairs):,} QA pairs ({skipped} skipped — too short)")
    return all_pairs


def _load_stackexchange_files() -> list[dict]:
    """Load per-site SE files if the merged file is missing."""
    se_sites = ["superuser", "serverfault", "askubuntu", "unix"]
    pairs = []
    for site in se_sites:
        filepath = DATA_DIR / f"stackexchange_{site}_qa.json"
        if not filepath.exists():
            continue
        print(f"📖 Loading stackexchange_{site}_qa.json ...")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            qa_text = f"{item.get('question', '')}\n\n{item.get('answer', '')}".strip()
            if len(qa_text) < 50:
                continue
            pairs.append({
                "qa_text": _truncate(qa_text),
                "question": _truncate(item.get("question", "")),
                "answer": _truncate(item.get("answer", "")),
                "source": "StackExchange",
                "tags": json.dumps(item.get("tags", []), ensure_ascii=False)[:4096],
                "date": str(item.get("date", ""))[:32],
                "site": str(item.get("site", ""))[:64],
                "score": float(item.get("score", item.get("answer_score", 0))),
                "is_accepted": bool(item.get("is_accepted", False)),
                "url": str(item.get("url", ""))[:2048],
            })
    return pairs


# ── Embedding generation ──────────────────────────────────────────────
def generate_embeddings(
    texts: list[str],
    model: "SentenceTransformer",
    batch_size: int = 100,
    label: str = "",
) -> list[list[float]]:
    """Generate embeddings for a list of texts in batches.

    Uses the BGE model (1024-dim, normalized).  Shows progress every 5 batches.
    """
    all_embeddings = []
    total = len(texts)
    t_start = time.time()
    prefix = f"  [{label}] " if label else "  "

    for i in range(0, total, batch_size):
        batch = texts[i : i + batch_size]
        vectors = model.encode(
            batch,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=batch_size,
        )
        all_embeddings.extend(vectors.tolist())

        # Progress every 5 batches (less noisy, visible in logs)
        done = min(i + batch_size, total)
        batch_num = i // batch_size + 1
        if batch_num % 5 == 0 or done == total:
            elapsed = time.time() - t_start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            print(f"{prefix}🧮 Embedded {done:6,d}/{total:,d} | {rate:.0f} docs/s | ETA {eta:.0f}s")
            sys.stdout.flush()

    elapsed = time.time() - t_start
    rate = total / elapsed if elapsed > 0 else 0
    print(f"{prefix}✅ {total:,} embeddings in {elapsed:.1f}s ({rate:.1f} docs/s)")
    sys.stdout.flush()
    return all_embeddings


# ── Milvus insertion ─────────────────────────────────────────────────
def insert_batch(
    batch: list[dict],
    embeddings: list[list[float]],
    col,  # pymilvus.Collection
) -> int:
    """Insert one batch into Milvus. Column order must match schema."""
    n = len(batch)
    entities = [
        embeddings,                                    # embedding
        [p["qa_text"] for p in batch],                 # qa_text
        [p["question"] for p in batch],                # question
        [p["answer"] for p in batch],                  # answer
        [p["source"] for p in batch],                  # source
        [p["tags"] for p in batch],                    # tags
        [p["date"] for p in batch],                    # date
        [p["site"] for p in batch],                    # site
        [p["score"] for p in batch],                   # score
        [p["is_accepted"] for p in batch],             # is_accepted
        [p["url"] for p in batch],                     # url
    ]
    col.insert(entities)
    return n


# ── Dry-run validation ────────────────────────────────────────────────
def dry_run(all_pairs: list[dict]) -> None:
    """Validate data without inserting into Milvus."""
    print(f"\n🔍 Dry run — validating {len(all_pairs):,} QA pairs\n")

    sources = {}
    sites = {}
    max_lens = {f: 0 for f in ["qa_text", "question", "answer", "tags", "url"]}

    for p in all_pairs:
        src = p["source"]
        sources[src] = sources.get(src, 0) + 1
        if p["site"]:
            sites[p["site"]] = sites.get(p["site"], 0) + 1
        for f in max_lens:
            cur = len(p.get(f, ""))
            if cur > max_lens[f]:
                max_lens[f] = cur

    print("  📊 By source:")
    for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"     {src:25s}: {cnt:6,}")

    if sites:
        print("  🌐 By site:")
        for site, cnt in sorted(sites.items(), key=lambda x: -x[1]):
            print(f"     {site:25s}: {cnt:6,}")

    print("  📏 Max field lengths:")
    for f, l in max_lens.items():
        warn = " ⚠️  TRUNCATED!" if l >= MAX_VARCHAR else ""
        print(f"     {f:15s}: {l:7,} chars{warn}")

    print("\n  📝 Sample QA (first 3):")
    for i, p in enumerate(all_pairs[:3], 1):
        print(f"\n  --- #{i} ---")
        print(f"  Source:  {p['source']}  |  Date: {p['date']}  |  Score: {p['score']}")
        print(f"  Q: {p['question'][:120]}...")
        print(f"  A: {p['answer'][:120]}...")


# ── Show collection stats ─────────────────────────────────────────────
def show_stats() -> None:
    """Print collection statistics."""
    from pymilvus import Collection

    connect_milvus(
        host=os.environ.get("MILVUS_HOST", "localhost"),
        port=int(os.environ.get("MILVUS_PORT", "19530")),
    )
    col = Collection(COLLECTION_NAME, using=CONNECTION_ALIAS)
    print(f"\n📊 Collection: {COLLECTION_NAME}")
    print(f"   Entities:   {col.num_entities:,}")
    print(f"   Loaded:     {'yes' if col.is_loaded else 'no'}")


# ── Main ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Import IT Support Q&A pairs into Milvus for RAG"
    )
    parser.add_argument(
        "--batch-size", type=int, default=100,
        help="Rows per insert batch (default: 100)"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max total rows to import (0 = all)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Load & validate data only — do not insert into Milvus"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show collection stats and exit"
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="Milvus host (default: $MILVUS_HOST or localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Milvus port (default: $MILVUS_PORT or 19530)"
    )
    parser.add_argument(
        "--model", type=str, default="BAAI/bge-large-zh-v1.5",
        help="Embedding model name (default: BAAI/bge-large-zh-v1.5)"
    )
    args = parser.parse_args()

    host = args.host or os.environ.get("MILVUS_HOST", "localhost")
    port = args.port or int(os.environ.get("MILVUS_PORT", "19530"))
    limit = args.limit if args.limit > 0 else None

    # Stats only
    if args.stats:
        show_stats()
        return

    # ── Step 1: Load data ─────────────────────────────────────────
    print("=" * 60)
    print("📥 Step 1: Loading QA pairs from data/ ...")
    print("=" * 60)
    all_pairs = load_all_qa_pairs(limit=limit)

    if not all_pairs:
        print("❌ No data loaded. Check data/ directory.")
        sys.exit(1)

    # ── Step 2: Dry run ───────────────────────────────────────────
    if args.dry_run:
        dry_run(all_pairs)
        return

    # ── Step 3: Load embedding model ───────────────────────────────
    print(f"\n🧠 Step 2: Loading embedding model: {args.model}")
    from sentence_transformers import SentenceTransformer

    t_model = time.time()
    model = SentenceTransformer(args.model)
    print(f"  ✅ Model loaded in {time.time() - t_model:.1f}s (dim={model.get_sentence_embedding_dimension()})")

    # ── Step 4: Connect Milvus ─────────────────────────────────────
    print(f"\n🔗 Step 3: Connecting to Milvus")
    connect_milvus(host, port)
    from pymilvus import Collection

    col = Collection(COLLECTION_NAME, using=CONNECTION_ALIAS)

    # ── Step 5: Generate embeddings & insert ───────────────────────
    print(f"\n🚀 Step 4: Indexing {len(all_pairs):,} QA pairs (batch={args.batch_size})")

    total_batches = (len(all_pairs) + args.batch_size - 1) // args.batch_size
    inserted = 0

    for batch_idx in range(0, len(all_pairs), args.batch_size):
        batch = all_pairs[batch_idx : batch_idx + args.batch_size]
        batch_num = batch_idx // args.batch_size + 1

        # Generate embeddings for this batch
        qa_texts = [p["qa_text"] for p in batch]
        embeddings = generate_embeddings(
            qa_texts, model,
            batch_size=min(100, args.batch_size),
            label=f"Batch {batch_num}/{total_batches}",
        )

        # Insert
        n = insert_batch(batch, embeddings, col)
        inserted += n

        print(f"  💾 Batch {batch_num:3d}/{total_batches} | {inserted:7,d} total inserted")
        sys.stdout.flush()

    col.flush()
    print(f"\n  ✅ All done — {inserted:,} rows indexed")

    # ── Summary ────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"✅ Import complete!")
    print(f"   Collection:  {COLLECTION_NAME}")
    print(f"   Total rows:  {col.num_entities:,}")
    print(f"   Index type:  IVF_FLAT / COSINE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
