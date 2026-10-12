#!/usr/bin/env python3
"""
RAG recall evaluation — measure HitRate@k and MRR across the three
Milvus collections used by CyberBuddy.

Reads a ground-truth test set (``data/rag_eval_queries.json``) where each
entry is a query plus the collection it should hit and how to recognise a
correct hit:

  - ``security_violations``: hit if a returned entry's ``severity`` equals
    ``expected_severity`` (primary), else any ``match_keywords`` appear in
    the violation/example phrase.
  - ``qa_pairs`` / ``it_knowledge``: hit if any ``match_keywords`` appear
    (case-insensitive) in the returned text.

Metrics:
  HitRate@1 / @3 / @5 — fraction of queries with a correct hit in the top-k.
  MRR                — mean reciprocal rank of the first correct hit.

Usage:
    python scripts/eval_rag.py                     # default test set
    python scripts/eval_rag.py --top-k 5 --min-score 0.5
    python scripts/eval_rag.py --testset /path/to/queries.json

Environment:
    Run from backend/ so pydantic-settings reads .env (Milvus + embedding cfg).
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_TESTSET = PROJECT_ROOT / "data" / "rag_eval_queries.json"

sys.path.insert(0, str(BACKEND_DIR))

from app.core.embeddings import get_embedding_service  # noqa: E402
from app.core.config import settings  # noqa: E402


# ── Search + hit helpers ──────────────────────────────────────────────

async def _search(collection: str, vec: list[float], top_k: int, min_score: float) -> list[dict]:
    from app.rag.vector_store import (
        search_knowledge_base,
        search_qa_pairs,
        search_violations,
    )

    if collection == "security_violations":
        return await search_violations(vec, top_k=top_k, min_score=min_score)
    if collection == "qa_pairs":
        return await search_qa_pairs(vec, top_k=top_k, min_score=min_score)
    return await search_knowledge_base(vec, top_k=top_k, min_score=min_score)


def _hit_text(hit: dict, collection: str) -> str:
    if collection == "security_violations":
        return f"{hit.get('violation', '')} {hit.get('phrase', '')}"
    if collection == "qa_pairs":
        return hit.get("qa_text", "") or hit.get("question", "")
    return hit.get("text", "")


def _is_hit(item: dict, hit: dict, collection: str) -> bool:
    if collection == "security_violations" and item.get("expected_severity"):
        if hit.get("severity") == item["expected_severity"]:
            return True
    kws = item.get("match_keywords", [])
    if not kws:
        return False
    text = _hit_text(hit, collection).lower()
    return any(kw.lower() in text for kw in kws)


# ── Evaluation ────────────────────────────────────────────────────────

async def evaluate(tests: list[dict], top_k: int, min_score: float) -> dict:
    svc = get_embedding_service()
    per_collection = defaultdict(lambda: {"n": 0, "hit_at": {k: 0 for k in (1, 3, 5)}, "rr": 0.0, "miss": []})

    for item in tests:
        collection = item["collection"]
        query = item["query"]

        vec = await svc.embed_query(query)
        hits = await _search(collection, vec, top_k=top_k, min_score=min_score)

        bucket = per_collection[collection]
        bucket["n"] += 1

        first_rank = None
        for i, h in enumerate(hits, 1):
            if _is_hit(item, h, collection):
                first_rank = i
                break

        if first_rank is not None:
            bucket["rr"] += 1.0 / first_rank
            for k in (1, 3, 5):
                if first_rank <= k:
                    bucket["hit_at"][k] += 1
        else:
            bucket["miss"].append(query)

    return per_collection


def report(per_collection: dict, top_k: int, min_score: float) -> None:
    print("=" * 72)
    print(f"RAG 召回评估  (top_k={top_k}, min_score={min_score})")
    print("=" * 72)

    total_n = 0
    total_hit = {k: 0 for k in (1, 3, 5)}
    total_rr = 0.0

    for collection in ("security_violations", "qa_pairs", "it_knowledge"):
        b = per_collection.get(collection)
        if not b:
            continue
        n = b["n"]
        total_n += n
        total_rr += b["rr"]
        for k in (1, 3, 5):
            total_hit[k] += b["hit_at"][k]

        print(f"\n📦 {collection}  ({n} 条)")
        for k in (1, 3, 5):
            rate = b["hit_at"][k] / n if n else 0.0
            print(f"   HitRate@{k}: {rate:.3f}  ({b['hit_at'][k]}/{n})")
        mrr = b["rr"] / n if n else 0.0
        print(f"   MRR:        {mrr:.3f}")

        if b["miss"]:
            print(f"   ❌ 未命中 {len(b['miss'])} 条:")
            for q in b["miss"]:
                print(f"        - {q}")

    if total_n:
        print(f"\n{'─' * 72}")
        print(f"📊 总体 ({total_n} 条)")
        for k in (1, 3, 5):
            print(f"   HitRate@{k}: {total_hit[k] / total_n:.3f}  ({total_hit[k]}/{total_n})")
        print(f"   MRR:        {total_rr / total_n:.3f}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="RAG recall evaluation")
    parser.add_argument("--testset", type=str, default=str(DEFAULT_TESTSET))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=None)
    args = parser.parse_args()

    min_score = args.min_score if args.min_score is not None else settings.MILVUS_MIN_SCORE

    tests = json.loads(Path(args.testset).read_text(encoding="utf-8"))
    print(f"Loaded {len(tests)} test queries from {args.testset}")

    per_collection = await evaluate(tests, args.top_k, min_score)
    report(per_collection, args.top_k, min_score)


if __name__ == "__main__":
    asyncio.run(main())
