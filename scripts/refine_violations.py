#!/usr/bin/env python3
"""
Refine the extracted violation catalogue — a second LLM pass.

The first pass (``extract_violations.py``) produces ~150 entries from the
Tailscale policy documents. That raw list has three problems:

  1. No ``critical`` entries (Tailscale is normative, not incident-oriented)
  2. Noise — many entries describe *security-team operating duties*
     ("安全团队未定期检查日志") rather than *employee violations*
     ("将客户数据导出到个人U盘")
  3. Redundancy — near-duplicate entries across files

This script runs the raw list back through the LLM to (a) drop the
operating-duty noise, (b) merge near-duplicates, (c) add canonical
``critical`` scenarios, and (d) compress to 40–60 high-signal entries.

Usage:
    python scripts/refine_violations.py                  # refine + overwrite data/security_violations.json
    python scripts/refine_violations.py --out /tmp/x.json

Environment:
    Reads LLM config from backend/.env (run from backend/ dir, or set cwd there).
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
INPUT_FILE = PROJECT_ROOT / "data" / "security_violations.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "security_violations.json"

SYSTEM_PROMPT = """你是企业安全策略分析师。下面是一份从安全策略文档提炼出的「违规行为清单」（JSON 数组）。

请对它做二次精炼，目标是生成一份高质量、可直接用于「判断员工上报内容的风险等级」的违规条目库。

## 精炼规则
1. **过滤噪音**：删除「安全团队/组织内部运营职责」类条目（例如"安全团队未定期检查日志"、"未每年审查政策"、"未记录资产清单"）。只保留「员工/个人违规行为」类条目（例如"将客户数据导出到个人U盘"、"使用弱密码"、"共享账号"）。
2. **合并相似**：合并语义相近的条目（例如"密码过短"和"使用弱密码"合并为一条）。
3. **补充 critical**：补充以下典型 critical 级违规场景（原清单缺失）：
   - 大规模/批量数据泄露（导出大量客户数据、整库泄露）
   - 勒索软件感染 / 文件被加密
   - APT 攻击 / 高级持续性威胁
   - 核心系统或管理员账户失守
   - 冒充高管欺诈（CEO 欺诈）成功
4. **控制数量**：最终控制在 40–60 条，聚焦"员工可能上报的高风险行为"。

## severity 标准（保持四级）
- critical: 大规模数据泄露、勒索软件、APT攻击、核心系统/账户失守、CEO欺诈成功
- high: 数据泄露、钓鱼点击、恶意软件感染、权限异常提升、凭证泄露
- medium: 可疑登录、异常下载、安全策略违规、弱密码、未授权访问尝试
- low: 可疑但无明确威胁证据、轻微策略偏离

## 输出要求
只输出一个 JSON 数组，每条字段与输入一致：
- "violation": 违规行为简明中文描述
- "category": 数据泄露 / 账号密码 / 访问控制 / 异常行为 / 设备安全 / 其他
- "severity": critical / high / medium / low
- "example_phrases": 员工可能说的话，2-3 个中文口语示例

不要输出 source 字段，不要任何其他文字或解释。

## 输入清单
{entries_json}"""


def parse_json_array(text: str) -> list[dict]:
    """Extract a JSON array from an LLM response, with tolerance."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    print(f"  ⚠️  Could not parse JSON from: {text[:200]}", file=sys.stderr)
    return []


def normalize(entry: dict) -> dict | None:
    if not isinstance(entry, dict):
        return None
    violation = str(entry.get("violation", "")).strip()
    if not violation:
        return None
    severity = str(entry.get("severity", "medium")).strip().lower()
    if severity not in ("critical", "high", "medium", "low"):
        severity = "medium"
    category = str(entry.get("category", "其他")).strip()
    allowed = ("数据泄露", "账号密码", "访问控制", "异常行为", "设备安全", "其他")
    if category not in allowed:
        category = "其他"
    phrases = entry.get("example_phrases", [])
    if isinstance(phrases, str):
        phrases = [phrases]
    phrases = [str(p).strip() for p in phrases if str(p).strip()]
    return {
        "violation": violation,
        "category": category,
        "severity": severity,
        "example_phrases": phrases,
    }


async def main(out_path: Path) -> None:
    sys.path.insert(0, str(BACKEND_DIR))
    from app.core.llm import get_llm

    raw = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(raw)} raw entries")

    # Strip 'source' before sending (keep it compact; refine merges sources)
    compact = [
        {k: v for k, v in e.items() if k != "source"}
        for e in raw
    ]
    entries_json = json.dumps(compact, ensure_ascii=False, indent=1)

    llm = get_llm(temperature=0.0)
    prompt = SYSTEM_PROMPT.format(entries_json=entries_json)

    print("Refining via LLM (this may take 1-2 min)...")
    response = await llm.ainvoke(prompt)

    refined_raw = parse_json_array(response.content)
    refined = [n for e in refined_raw if (n := normalize(e))]

    print(f"Refined: {len(refined_raw)} parsed → {len(refined)} valid entries")

    # Deduplicate by violation text
    seen = set()
    deduped = []
    for e in refined:
        key = e["violation"].strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    # Summary
    from collections import Counter
    sev = Counter(e["severity"] for e in deduped)
    cat = Counter(e["category"] for e in deduped)
    print(f"\n📊 Final: {len(deduped)} entries")
    print("  severity:", dict(sorted(sev.items())))
    print("  category:", dict(sorted(cat.items(), key=lambda x: -x[1])))

    out_path.write_text(
        json.dumps(deduped, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n✅ Wrote {len(deduped)} entries to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refine extracted violation catalogue")
    parser.add_argument("--out", type=str, default=str(OUTPUT_FILE))
    args = parser.parse_args()
    asyncio.run(main(Path(args.out)))
