#!/usr/bin/env python3
"""
Routing accuracy evaluation — measures SupervisorAgent intent routing
accuracy (CHAT / CONSULT / RISK) against a labelled test set.

Reads ``data/router_eval_queries.json`` (query + expected route), classifies
each via SupervisorAgent, and reports overall accuracy, a confusion matrix,
and any low-confidence decisions that were forced to CHAT by the fallback.

Usage:
    python scripts/eval_router.py
    python scripts/eval_router.py --concurrency 8

Environment:
    Run from backend/ so pydantic-settings reads .env (LLM config).
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
DEFAULT_TESTSET = PROJECT_ROOT / "data" / "router_eval_queries.json"

sys.path.insert(0, str(BACKEND_DIR))

from app.agents.base import AgentState  # noqa: E402
from app.agents.supervisor_agent import SupervisorAgent, _CONFIDENCE_FALLBACK  # noqa: E402

ROUTES = ("CHAT", "CONSULT", "RISK")


async def _classify_one(agent: SupervisorAgent, query: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        state = AgentState(session_id="eval", user_id="eval", user_input=query)
        decision = await agent._classify(agent._build_messages(state))
        raw = decision.route.value
        conf = decision.confidence
        final = raw if conf >= _CONFIDENCE_FALLBACK else "CHAT"
        return {"query": query, "raw": raw, "final": final, "confidence": conf}


async def evaluate(tests: list[dict], concurrency: int) -> dict:
    agent = SupervisorAgent()
    sem = asyncio.Semaphore(concurrency)

    tasks = [_classify_one(agent, t["query"], sem) for t in tests]
    results = await asyncio.gather(*tasks)

    matrix = defaultdict(lambda: defaultdict(int))
    correct = 0
    low_conf = []
    raw_correct = 0

    for t, r in zip(tests, results):
        expected = t["expected"]
        matrix[expected][r["final"]] += 1
        if r["final"] == expected:
            correct += 1
        if r["raw"] == expected:
            raw_correct += 1
        if r["confidence"] < _CONFIDENCE_FALLBACK:
            low_conf.append(r)

    n = len(tests)
    return {
        "n": n,
        "accuracy": correct / n,
        "raw_accuracy": raw_correct / n,
        "matrix": matrix,
        "low_conf": low_conf,
        "results": list(zip(tests, results)),
    }


def report(stats: dict) -> None:
    print("=" * 72)
    print(f"路由准确率评估  (n={stats['n']}, fallback 阈值={_CONFIDENCE_FALLBACK})")
    print("=" * 72)
    print(f"\n准确率（fallback 后）: {stats['accuracy']:.3f}")
    print(f"准确率（原始分类）  : {stats['raw_accuracy']:.3f}")

    print("\n混淆矩阵 (行=期望, 列=实际):")
    print(f"{'':>10}" + "".join(f"{r:>10}" for r in ROUTES))
    for expected in ROUTES:
        row = "".join(f"{stats['matrix'][expected].get(actual, 0):>10}" for actual in ROUTES)
        print(f"{expected:>10}{row}")

    # Misclassified
    mis = [ (t, r) for t, r in stats["results"] if r["final"] != t["expected"] ]
    if mis:
        print(f"\n❌ 误分类 {len(mis)} 条:")
        for t, r in mis:
            print(f"   [{t['expected']:>7} → {r['final']:>7}] (conf={r['confidence']:.2f}) {t['query']}")
    else:
        print("\n✅ 无误分类")

    if stats["low_conf"]:
        print(f"\n⚠️  低置信度样本 ({len(stats['low_conf'])} 条, 被强制回退 CHAT):")
        for r in stats["low_conf"]:
            print(f"   [{r['raw']:>7}] (conf={r['confidence']:.2f}) {r['query']}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Routing accuracy evaluation")
    parser.add_argument("--testset", type=str, default=str(DEFAULT_TESTSET))
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    tests = json.loads(Path(args.testset).read_text(encoding="utf-8"))
    print(f"Loaded {len(tests)} test queries from {args.testset}")

    stats = await evaluate(tests, args.concurrency)
    report(stats)


if __name__ == "__main__":
    asyncio.run(main())
