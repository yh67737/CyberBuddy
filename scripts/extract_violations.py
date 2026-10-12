#!/usr/bin/env python3
"""
Extract security violation entries from Tailscale security policies.

Reads the Tailscale security-policies markdown files (cloned under
``data/security-policies/``), and uses the LLM to reverse-engineer a
structured Chinese "violation catalogue" — each entry maps a rule
violation to a severity, with example employee phrases.

The output (``data/security_violations.json``) becomes the static
severity-judgement reference for SecurityGuardian, replacing its
coarse 4-line severity rubric with a richer, policy-grounded one.

Usage:
    python scripts/extract_violations.py                # full extraction
    python scripts/extract_violations.py --limit 3      # only first 3 files
    python scripts/extract_violations.py --out /tmp/v.json

Environment:
    Reads LLM config from backend/.env (LLM_API_KEY, LLM_MODEL, LLM_BASE_URL).
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

# Line-buffer stdout so progress is visible even when redirected to a file
sys.stdout.reconfigure(line_buffering=True)

# ── Constants ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
POLICIES_DIR = PROJECT_ROOT / "data" / "security-policies"
OUTPUT_FILE = PROJECT_ROOT / "data" / "security_violations.json"

# Policy files to process (exclude README/_index/overview which are not policies)
POLICY_FILES = [
    "information-classification/index.md",
    "incident-response-policy/index.md",
    "incident-response-process/index.md",
    "access-control/index.md",
    "password/index.md",
    "patch-management/index.md",
    "personnel/index.md",
    "vendor/index.md",
    "change-management/index.md",
    "data-retention-deletion/index.md",
    "risk-assessment/index.md",
    "testing/index.md",
    "bcp-dr/index.md",
    "incident-disclosure/index.md",
]

# Severity rubric — must match SecurityGuardian's existing 4-level scheme
SEVERITY_RUBRIC = """- critical: 大规模数据泄露、勒索软件、APT攻击、核心系统/账户完全失守
- high: 数据泄露、钓鱼攻击成功、恶意软件感染、权限异常提升、凭证泄露
- medium: 可疑登录、异常文件下载、安全策略违规、弱密码、未授权访问尝试
- low: 可疑但无明确威胁证据、轻微策略偏离"""

SYSTEM_PROMPT = """你是企业安全策略分析师。根据下面的安全策略文档（英文原文），提炼出一份中文「违规行为清单」。

对文档中的每条安全规范，反推出「违反它的行为」，并判断严重程度。这些条目将用于一个企业安全助手判断员工上报内容的风险等级。

## 严重程度分级标准
{severity_rubric}

## 输出要求
对每条违规行为，输出一个 JSON 对象，字段如下：
- "violation": 违规行为的简明中文描述（例如 "将客户数据导出到个人存储设备"）
- "category": 类别，取值必须是以下之一：数据泄露 / 账号密码 / 访问控制 / 异常行为 / 设备安全 / 其他
- "severity": 必须是 critical / high / medium / low 之一
- "example_phrases": 员工可能说的话，2-3 个中文口语化示例（例如 "我把客户数据库导到U盘了"）

只输出一个 JSON 数组，不要输出任何其他文字或解释。如果文档中没有可提炼的违规行为，输出空数组 []。

## 安全策略文档
{content}"""


# ── Frontmatter / content parsing ─────────────────────────────────────
def parse_markdown(text: str) -> tuple[str, str]:
    """Split markdown into (frontmatter_meta, body)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[1].strip(), parts[2].strip()
    return "", text


def clean_body(body: str) -> str:
    """Light cleanup: strip HTML tags, collapse blank lines."""
    body = re.sub(r"<[^>]+>", "", body)               # remove HTML tags
    body = re.sub(r"\{\{[<%][^}]*[>%]\}\}", "", body)  # Hugo shortcodes
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


# ── JSON parsing (DeepSeek doesn't support structured output) ────────
def parse_json_array(text: str) -> list[dict]:
    """Extract a JSON array from an LLM response, with tolerance."""
    text = text.strip()

    # Strip markdown code fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find the [...] block
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


def normalize_entry(entry: dict, source: str) -> dict | None:
    """Validate and normalize a single violation entry."""
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
        "source": source,
    }


# ── Extraction ────────────────────────────────────────────────────────
async def extract_for_file(llm, filepath: Path) -> list[dict]:
    """Extract violation entries from one policy markdown file."""
    source = filepath.parent.name  # e.g. "password", "access-control"
    text = filepath.read_text(encoding="utf-8")
    _, body = parse_markdown(text)
    body = clean_body(body)

    prompt = SYSTEM_PROMPT.format(
        severity_rubric=SEVERITY_RUBRIC,
        content=body[:12000],  # guard against very long docs
    )

    try:
        response = await llm.ainvoke(prompt)
        entries = parse_json_array(response.content)
    except Exception as exc:
        print(f"  ❌ LLM call failed for {source}: {exc}", file=sys.stderr)
        return []

    normalized = []
    for e in entries:
        n = normalize_entry(e, source)
        if n:
            normalized.append(n)

    print(f"  ✓ {source}: {len(normalized)} entries")
    return normalized


def deduplicate(entries: list[dict]) -> list[dict]:
    """Remove near-duplicate entries (same violation text)."""
    seen = set()
    unique = []
    for e in entries:
        key = e["violation"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


# ── Main ──────────────────────────────────────────────────────────────
async def main(limit: int | None, out_path: Path) -> None:
    sys.path.insert(0, str(BACKEND_DIR))
    from app.core.llm import get_llm

    llm = get_llm(temperature=0.0)

    files = POLICY_FILES[:limit] if limit else POLICY_FILES
    print(f"Extracting violations from {len(files)} policy files...\n")

    all_entries = []
    for rel in files:
        filepath = POLICIES_DIR / rel
        if not filepath.exists():
            print(f"  ⚠️  Missing: {rel}")
            continue
        entries = await extract_for_file(llm, filepath)
        all_entries.extend(entries)

    # Deduplicate
    unique = deduplicate(all_entries)
    print(f"\n📊 Total: {len(all_entries)} raw → {len(unique)} unique entries")

    # Distribution summary
    by_severity = {}
    by_category = {}
    for e in unique:
        by_severity[e["severity"]] = by_severity.get(e["severity"], 0) + 1
        by_category[e["category"]] = by_category.get(e["category"], 0) + 1

    print("  Severity distribution:")
    for sev in ("critical", "high", "medium", "low"):
        print(f"     {sev:9s}: {by_severity.get(sev, 0)}")
    print("  Category distribution:")
    for cat, cnt in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"     {cat:8s}: {cnt}")

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(unique, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n✅ Wrote {len(unique)} entries to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract security violations from Tailscale policies")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N files")
    parser.add_argument("--out", type=str, default=str(OUTPUT_FILE), help="Output JSON path")
    args = parser.parse_args()

    limit = args.limit if args.limit > 0 else None
    asyncio.run(main(limit, Path(args.out)))
