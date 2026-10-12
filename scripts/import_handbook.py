#!/usr/bin/env python3
"""
Import GitLab Handbook into Milvus for RAG retrieval.

Clones the GitLab Handbook repository (https://handbook.gitlab.com/),
parses Markdown files from IT-relevant sections, chunks by heading,
embeds with BAAI/bge-large-zh-v1.5, and indexes into the ``it_knowledge``
Milvus collection.

Sections indexed:
  - security/              — Security policies, threat management, incident response
  - business-technology/   — IT operations, internal tools, data platform
  - engineering/           — Development practices, on-call, infrastructure

Usage:
    python scripts/import_handbook.py                    # full import
    python scripts/import_handbook.py --dry-run           # validate & show stats
    python scripts/import_handbook.py --limit 500         # first 500 chunks only
    python scripts/import_handbook.py --no-clone           # skip git clone (already cloned)
    python scripts/import_handbook.py --sections security,business-technology  # specific sections

Environment:
    MILVUS_HOST  — Milvus server host (default: localhost)
    MILVUS_PORT  — Milvus gRPC port  (default: 19530)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── Constants ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = PROJECT_ROOT / "data"
HANDBOOK_DIR = DATA_DIR / "handbook"
COLLECTION_NAME = "it_knowledge"
DIMENSION = 1024
MAX_VARCHAR = 65535
CONNECTION_ALIAS = "cyberbuddy_handbook_import"

# Handbook repo
HANDBOOK_REPO = "https://gitlab.com/gitlab-com/content-sites/handbook.git"

# Sections to index (relative to content/handbook/)
# Using targeted engineering subdirs to avoid importing product-development
# content (13K+ chunks) that isn't relevant to enterprise IT support.
DEFAULT_SECTIONS = [
    "security",
    "business-technology",
    "engineering/infrastructure",
    "engineering/infrastructure-platforms",
    "engineering/devops",
    "engineering/error-budgets",
    "engineering/monitoring",
    "engineering/development",
    "engineering/workflow",
]

# Max chunk size in characters (BGE-large context window is 512 tokens ≈ ~2000 chars)
MAX_CHUNK_SIZE = 2000


# ── Git operations ────────────────────────────────────────────────────
def clone_handbook() -> bool:
    """Shallow-clone the GitLab Handbook repo. Returns True on success."""
    if HANDBOOK_DIR.exists():
        print(f"📂 Handbook already cloned at {HANDBOOK_DIR}")
        # Pull latest
        print("🔄 Pulling latest changes...")
        result = subprocess.run(
            ["git", "-C", str(HANDBOOK_DIR), "pull", "--ff-only"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("✅ Handbook up to date")
            return True
        else:
            print(f"⚠️  Pull failed: {result.stderr[:200]}, using existing clone")
            return True

    print(f"⬇️  Cloning GitLab Handbook (shallow)...")
    HANDBOOK_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "git", "clone", "--depth", "1",
            HANDBOOK_REPO, str(HANDBOOK_DIR),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"❌ Clone failed: {result.stderr[:500]}")
        return False

    print("✅ Handbook cloned successfully")
    return True


# ── Markdown parsing ─────────────────────────────────────────────────
def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter (between --- delimiters) from markdown text.

    Returns (metadata_dict, body_text).
    """
    meta = {}
    body = text

    # Frontmatter is between first two --- lines
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            # Simple key: value parser (handles nested keys like "stage: Tenant Scale")
            for line in fm_text.split("\n"):
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if value:
                        meta[key] = value

    return meta, body


def chunk_markdown(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split markdown text into chunks by ## headings.

    Each H2 section becomes a chunk.  If a chunk exceeds ``max_size``,
    it is further split by H3 headings, then by paragraphs.
    """
    if not text.strip():
        return []

    # Strategy: split on "## " (level-2 ATX headings)
    # Preserve the heading text as part of each chunk
    sections = re.split(r"\n(?=## )", text)

    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(section) <= max_size:
            chunks.append(section)
        else:
            # Try H3 split
            subs = re.split(r"\n(?=### )", section)
            for sub in subs:
                sub = sub.strip()
                if not sub:
                    continue
                if len(sub) <= max_size:
                    chunks.append(sub)
                else:
                    # Paragraph split as last resort
                    chunks.extend(_split_by_paragraphs(sub, max_size))

    return chunks


# HTML tag pattern (for stripping Hugo shortcodes and inline HTML)
_HTML_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and Hugo shortcodes from markdown text."""
    # Remove HTML tags
    text = _HTML_RE.sub("", text)
    # Remove Hugo shortcode markers: {{< ... >}} and {{% ... %}}
    text = re.sub(r"\{\{[<%][^}]*[>%]\}\}", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_by_paragraphs(text: str, max_size: int) -> list[str]:
    """Split long text by paragraph boundaries, respecting max_size."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= max_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds max_size, hard-split
            if len(para) > max_size:
                for i in range(0, len(para), max_size):
                    chunks.append(para[i:i + max_size])
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def url_for_file(rel_path: str) -> str:
    """Convert a repo file path to the handbook.gitlab.com URL."""
    # content/handbook/security/index.md → /handbook/security/
    # content/handbook/security/some-page.md → /handbook/security/some-page/
    base_url = "https://handbook.gitlab.com"
    # Strip "content/" prefix — repo paths are content/handbook/<section>/...
    url_path = rel_path.replace("content/", "", 1)
    url_path = re.sub(r"/(_?index)\.md$", "/", url_path)
    url_path = url_path.replace(".md", "/")
    return f"{base_url}/{url_path.lstrip('/')}"


# ── Document loader ───────────────────────────────────────────────────
def load_handbook_docs(
    sections: list[str],
    limit: Optional[int] = None,
) -> list[dict]:
    """Walk the handbook content directories and return chunked documents.

    Each returned dict has:
      - text: chunk content (markdown, stripped of HTML)
      - metadata: JSON-serializable dict with source, section, title, url, headings

    Returns a list of dicts ready for embedding + insertion.
    """
    content_root = HANDBOOK_DIR / "content" / "handbook"

    if not content_root.exists():
        print(f"❌ Content directory not found: {content_root}")
        print("   Did the clone succeed? Try running without --no-clone first.")
        sys.exit(1)

    docs = []
    skipped_empty = 0
    skipped_size = 0

    for section in sections:
        section_dir = content_root / section
        if not section_dir.is_dir():
            print(f"  ⚠️  Section directory not found: {section_dir} (skipping)")
            continue

        md_files = sorted(section_dir.rglob("*.md"))
        print(f"\n📂 {section}/ — {len(md_files)} markdown files")

        for md_file in md_files:
            rel_path = str(md_file.relative_to(HANDBOOK_DIR))

            try:
                raw = md_file.read_text(encoding="utf-8")
            except Exception as exc:
                print(f"  ⚠️  Cannot read {md_file.name}: {exc}")
                continue

            # Parse frontmatter
            meta, body = parse_frontmatter(raw)
            if not body:
                skipped_empty += 1
                continue

            # Strip HTML tags and Hugo shortcodes
            body = _strip_html(body)
            if not body:
                skipped_empty += 1
                continue

            # Extract title from frontmatter or first # heading
            title = meta.get("title", "")
            if not title:
                h1_match = re.search(r"^# (.+)$", body, re.MULTILINE)
                if h1_match:
                    title = h1_match.group(1).strip()
            if not title:
                title = md_file.stem.replace("-", " ").replace("_", " ")

            # Chunk
            chunks = chunk_markdown(body)
            if not chunks:
                skipped_empty += 1
                continue

            # Build document entries
            url = url_for_file(rel_path)
            section_path = str(md_file.relative_to(content_root))

            for i, chunk in enumerate(chunks):
                # Skip very small chunks (just a heading with no content)
                if len(chunk) < 50:
                    skipped_size += 1
                    continue

                # Build metadata
                chunk_meta = {
                    "source": "GitLab Handbook",
                    "section": section,
                    "title": title,
                    "url": url,
                    "file_path": rel_path,
                    "section_path": section_path,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
                # Include frontmatter fields for filtering
                for fm_key in ("stage", "group", "description", "type"):
                    if meta.get(fm_key):
                        chunk_meta[fm_key] = meta[fm_key]

                docs.append({
                    "text": chunk,
                    "metadata": chunk_meta,
                })

                if limit and len(docs) >= limit:
                    break

            if limit and len(docs) >= limit:
                break

        if limit and len(docs) >= limit:
            break

    print(f"\n📊 Loaded {len(docs):,} document chunks")
    print(f"   Skipped: {skipped_empty} empty, {skipped_size} too-small")
    return docs


# ── Milvus connection ─────────────────────────────────────────────────
def connect_milvus(host: str, port: int):
    """Connect to Milvus and ensure it_knowledge collection exists."""
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
        return col

    # Create collection
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIMENSION),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=MAX_VARCHAR),
        FieldSchema(name="metadata", dtype=DataType.JSON),
    ]
    schema = CollectionSchema(fields, description="企业IT手册与安全合规制度")
    col = Collection(COLLECTION_NAME, schema=schema, using=CONNECTION_ALIAS)

    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    col.create_index(field_name="embedding", index_params=index_params)
    col.load()
    print(f"📦 Created collection '{COLLECTION_NAME}' with IVF_FLAT/COSINE index")
    return col


# ── Embedding ─────────────────────────────────────────────────────────
def generate_embeddings(
    texts: list[str],
    model: "SentenceTransformer",
    batch_size: int = 100,
    label: str = "",
) -> list[list[float]]:
    """Generate BGE embeddings for a list of texts."""
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


# ── Insertion ─────────────────────────────────────────────────────────
def insert_batch(
    batch: list[dict],
    embeddings: list[list[float]],
    col,  # pymilvus.Collection
) -> int:
    """Insert one batch into Milvus it_knowledge collection.

    Column order (schema): id(auto), embedding, text, metadata.
    """
    entities = [
        embeddings,
        [doc["text"] for doc in batch],
        [doc["metadata"] for doc in batch],
    ]
    col.insert(entities)
    return len(batch)


# ── Dry-run ───────────────────────────────────────────────────────────
def dry_run(docs: list[dict], sections: list[str]) -> None:
    """Validate documents without inserting into Milvus."""
    print(f"\n🔍 Dry run — validating {len(docs):,} document chunks\n")

    # Stats by section
    by_section = {}
    max_text_len = 0
    total_chars = 0

    for doc in docs:
        sec = doc["metadata"].get("section", "unknown")
        by_section[sec] = by_section.get(sec, 0) + 1
        cur_len = len(doc["text"])
        if cur_len > max_text_len:
            max_text_len = cur_len
        total_chars += cur_len

    print("  📊 By section:")
    for sec in sorted(by_section, key=lambda k: -by_section[k]):
        bar = "█" * min(50, by_section[sec] // max(1, len(docs) // 50))
        print(f"     {sec:30s}: {by_section[sec]:6,} chunks  {bar}")

    print(f"\n  📏 Text stats:")
    print(f"     Total chunks:   {len(docs):,}")
    print(f"     Total chars:    {total_chars:,}")
    print(f"     Avg chunk size: {total_chars // max(1, len(docs)):,} chars")
    print(f"     Max chunk size: {max_text_len:,} chars")
    if max_text_len >= MAX_VARCHAR:
        print(f"     ⚠️  MAX EXCEEDED! Some chunks will be truncated.")

    # Sample
    print(f"\n  📝 Sample chunks (first 3):")
    for i, doc in enumerate(docs[:3], 1):
        meta = doc["metadata"]
        print(f"\n  --- #{i} ---")
        print(f"  Section:  {meta.get('section', '?')}  |  Title: {meta.get('title', '?')[:80]}")
        print(f"  URL:      {meta.get('url', '?')}")
        print(f"  Text:     {doc['text'][:200]}...")

    # Estimate embedding time
    est_rate = 5  # docs/s on CPU
    est_min = len(docs) / (est_rate * 60)
    print(f"\n  ⏱️  Estimated embedding time: ~{est_min:.0f} min (at ~{est_rate} docs/s on CPU)")


# ── Main ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Import GitLab Handbook into Milvus for RAG"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Load & validate data only — do not insert into Milvus"
    )
    parser.add_argument(
        "--no-clone", action="store_true",
        help="Skip git clone (handbook already at data/handbook/)"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max total chunks to import (0 = all)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=100,
        help="Chunks per insert batch (default: 100)"
    )
    parser.add_argument(
        "--sections", type=str, default=None,
        help="Comma-separated section names (default: security,business-technology,engineering)"
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
        help="Embedding model name"
    )
    args = parser.parse_args()

    host = args.host or os.environ.get("MILVUS_HOST", "localhost")
    port = args.port or int(os.environ.get("MILVUS_PORT", "19530"))
    limit = args.limit if args.limit > 0 else None
    sections = (
        [s.strip() for s in args.sections.split(",")]
        if args.sections
        else DEFAULT_SECTIONS
    )

    print("=" * 60)
    print("🏢 GitLab Handbook → Milvus Importer")
    print("=" * 60)
    print(f"   Sections: {', '.join(sections)}")
    print(f"   Collection: {COLLECTION_NAME}")
    if limit:
        print(f"   Limit: {limit:,} chunks")

    # ── Step 1: Clone ──────────────────────────────────────────────
    if not args.no_clone:
        print(f"\n📥 Step 1: Cloning GitLab Handbook...")
        if not clone_handbook():
            sys.exit(1)
    else:
        print(f"\n📥 Step 1: Skipping clone (--no-clone)")
        if not HANDBOOK_DIR.exists():
            print(f"❌ Handbook directory not found at {HANDBOOK_DIR}")
            sys.exit(1)

    # ── Step 2: Load documents ─────────────────────────────────────
    print(f"\n📖 Step 2: Loading documents from content/handbook/...")
    docs = load_handbook_docs(sections, limit=limit)

    if not docs:
        print("❌ No documents loaded. Check sections and repository content.")
        sys.exit(1)

    # ── Step 3: Dry-run or import ───────────────────────────────────
    if args.dry_run:
        dry_run(docs, sections)
        return

    # ── Step 4: Load embedding model ────────────────────────────────
    print(f"\n🧠 Step 3: Loading embedding model: {args.model}")
    from sentence_transformers import SentenceTransformer

    t_model = time.time()
    model = SentenceTransformer(args.model)
    print(f"  ✅ Model loaded in {time.time() - t_model:.1f}s "
          f"(dim={model.get_sentence_embedding_dimension()})")

    # ── Step 5: Connect Milvus ──────────────────────────────────────
    print(f"\n🔗 Step 4: Connecting to Milvus")
    col = connect_milvus(host, port)

    # ── Step 6: Generate embeddings & insert ────────────────────────
    print(f"\n🚀 Step 5: Indexing {len(docs):,} chunks (batch={args.batch_size})")

    total_batches = (len(docs) + args.batch_size - 1) // args.batch_size
    inserted = 0
    t_start = time.time()

    for batch_idx in range(0, len(docs), args.batch_size):
        batch = docs[batch_idx : batch_idx + args.batch_size]
        batch_num = batch_idx // args.batch_size + 1

        # Generate embeddings
        texts = [doc["text"] for doc in batch]
        embeddings = generate_embeddings(
            texts, model,
            batch_size=min(100, args.batch_size),
            label=f"Batch {batch_num}/{total_batches}",
        )

        # Insert
        n = insert_batch(batch, embeddings, col)
        inserted += n

        elapsed = time.time() - t_start
        rate = inserted / elapsed if elapsed > 0 else 0
        print(f"  💾 Batch {batch_num:3d}/{total_batches} | "
              f"{inserted:7,d} total inserted | {rate:.0f} chunks/s")
        sys.stdout.flush()

    col.flush()
    print(f"\n  ✅ All done — {inserted:,} chunks indexed")
    print(f"  ⏱️  Total time: {time.time() - t_start:.0f}s")

    # ── Summary ────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"✅ Import complete!")
    print(f"   Collection:  {COLLECTION_NAME}")
    print(f"   Total rows:  {col.num_entities:,}")
    print(f"   Index type:  IVF_FLAT / COSINE")
    print(f"   Sections:    {', '.join(sections)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
