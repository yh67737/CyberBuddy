#!/usr/bin/env python3
"""
Fetch IT-related Q&A from StackExchange API (2022+).

Sites: Super User, Server Fault, Ask Ubuntu, Unix & Linux
Two-step: 1) fetch questions → 2) batch fetch their answers

StackExchange API is free. Rate limit: 300 req/day without key,
10,000 req/day with a free app key.

Usage:
    python fetch_stackexchange_qa.py                          # without API key
    python fetch_stackexchange_qa.py --key YOUR_KEY           # with free app key
    python fetch_stackexchange_qa.py --key YOUR_KEY --pages 50 --start-site askubuntu
"""

import argparse
import json
import os
import ssl
import time
import urllib.request
import urllib.parse
import urllib.error
import gzip
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────────
API_BASE = "https://api.stackexchange.com/2.3"

SITES = [
    "superuser",      # General PC/software/hardware
    "serverfault",    # Servers, networking, sysadmin
    "askubuntu",      # Ubuntu Linux
    "unix",           # Unix & Linux
]

FROM_DATE = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
PAGE_SIZE = 100
REQUEST_DELAY = 0.15  # seconds between requests

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "stackexchange_it_qa.json")

# Reusable SSL context (macOS cert workaround)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def api_get(path: str, params: dict) -> dict:
    """Make a StackExchange API request, return parsed JSON."""
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    url = f"{API_BASE}/{path}?{query}"

    req = urllib.request.Request(url, headers={
        "User-Agent": "CyberBuddy-RAG-Collector/1.0",
        "Accept-Encoding": "gzip",
    })

    try:
        resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=30)
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"    HTTP {e.code}: {body[:300]}")
        return {"items": [], "has_more": False}
    except Exception as e:
        print(f"    Error: {e}")
        return {"items": [], "has_more": False}


def fetch_questions(site: str, page: int, api_key: str | None) -> dict:
    """Fetch one page of questions sorted by votes, 2022+."""
    return api_get("questions", {
        "site": site,
        "page": page,
        "pagesize": PAGE_SIZE,
        "order": "desc",
        "sort": "votes",
        "fromdate": FROM_DATE,
        "filter": "withbody",
        "key": api_key or "",
    })


def fetch_answers(site: str, question_ids: list[int], api_key: str | None) -> dict:
    """Batch fetch answers for a list of question IDs."""
    ids_str = ";".join(str(qid) for qid in question_ids)
    return api_get(f"questions/{ids_str}/answers", {
        "site": site,
        "pagesize": 100,
        "order": "desc",
        "sort": "votes",
        "filter": "withbody",
        "key": api_key or "",
    })


def clean_html(text: str) -> str:
    """Basic HTML tag stripping for answer/body text."""
    import re
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode common HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
    text = text.replace('&nbsp;', ' ').replace('\r\n', '\n').replace('\r', '\n')
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def process_site(site: str, api_key: str | None, max_pages: int) -> list[dict]:
    """Fetch all Q&A pairs for one StackExchange site."""
    qa_list = []
    page = 1
    question_cache = {}  # qid -> question data (for matching answers)

    while True:
        if max_pages and page > max_pages:
            print(f"  Reached page limit ({max_pages})")
            break

        # ── Step 1: Fetch questions ──
        data = fetch_questions(site, page, api_key)
        items = data.get("items", [])
        quota = data.get("quota_remaining", "?")
        has_more = data.get("has_more", False)
        backoff = data.get("backoff", 0)

        if backoff:
            print(f"  ⏳ Backoff {backoff}s...")
            time.sleep(backoff + 1)
            continue

        if not items:
            break

        # Cache questions that have answers
        answered_ids = []
        for item in items:
            if item.get("is_answered") and item.get("answer_count", 0) > 0:
                answered_ids.append(item["question_id"])
                question_cache[item["question_id"]] = item

        # ── Step 2: Batch fetch answers for answered questions ──
        if answered_ids:
            time.sleep(REQUEST_DELAY)
            ans_data = fetch_answers(site, answered_ids, api_key)
            ans_items = ans_data.get("items", [])

            # Check for backoff in answer response
            ans_backoff = ans_data.get("backoff", 0)
            if ans_backoff:
                time.sleep(ans_backoff + 1)

            # Map answers to questions
            ans_by_qid: dict[int, dict] = {}
            for ans in ans_items:
                qid = ans["question_id"]
                # Keep accepted or highest-scored answer
                existing = ans_by_qid.get(qid)
                if existing is None or ans.get("is_accepted") or ans.get("score", 0) > existing.get("score", 0):
                    ans_by_qid[qid] = ans

            # Build Q&A pairs
            for qid, q_item in question_cache.items():
                ans = ans_by_qid.get(qid)
                if not ans:
                    continue

                question_body = clean_html(q_item.get("body", ""))
                title = (q_item.get("title") or "").strip()
                question = f"{title}\n\n{question_body}" if question_body else title
                if len(question) < 20:
                    continue

                answer_body = clean_html(ans.get("body", ""))
                if len(answer_body) < 30:
                    continue

                qa_list.append({
                    "id": f"SE_{site}_{qid}",
                    "question": question,
                    "answer": answer_body,
                    "score": q_item.get("score", 0),
                    "answer_score": ans.get("score", 0),
                    "is_accepted": ans.get("is_accepted", False),
                    "tags": q_item.get("tags", []),
                    "date": datetime.fromtimestamp(q_item["creation_date"], tz=timezone.utc).strftime("%Y-%m-%d"),
                    "site": site,
                    "source": "StackExchange",
                    "url": q_item.get("link", ""),
                })

        # Progress
        latest_str = datetime.fromtimestamp(items[-1]["creation_date"]).strftime("%Y-%m-%d") if items else "?"
        print(f"  Page {page:3d} | {len(items):3d} Q | {len(answered_ids):3d} with answers | "
              f"{len(qa_list):5d} total QA | quota={quota} | latest={latest_str}")

        # Save partial progress every 10 pages
        if page % 10 == 0 and qa_list:
            tmp_file = os.path.join(OUTPUT_DIR, f"stackexchange_{site}_qa_partial.json")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(qa_list, f, ensure_ascii=False, indent=2)

        if not has_more:
            print(f"  No more pages for {site}")
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return qa_list


def main():
    parser = argparse.ArgumentParser(description="Fetch IT Q&A from StackExchange")
    parser.add_argument("--key", type=str, default=None, help="StackExchange API key (free, 10k req/day)")
    parser.add_argument("--pages", type=int, default=0, help="Max pages per site (0=unlimited)")
    parser.add_argument("--start-site", type=str, default=None, help="Resume from specific site")
    args = parser.parse_args()

    if args.key:
        print(f"✅ Using API key (10,000 req/day)")
    else:
        print(f"⚠️  No API key (300 req/day). Get free key: https://stackapps.com/apps/oauth/register")
    print(f"Sites: {', '.join(SITES)}")
    print(f"Date: 2022-01-01 → now, sorted by votes\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_qa = []
    site_counts = {}

    for site in SITES:
        if args.start_site and site != args.start_site:
            print(f"⏭️  Skipping {site}")
            continue

        print(f"{'='*60}")
        print(f"📥 {site}.stackexchange.com")
        print(f"{'='*60}")

        qa = process_site(site, args.key, args.pages)
        site_counts[site] = len(qa)
        all_qa.extend(qa)

        # Save per-site
        site_file = os.path.join(OUTPUT_DIR, f"stackexchange_{site}_qa.json")
        with open(site_file, "w", encoding="utf-8") as f:
            json.dump(qa, f, ensure_ascii=False, indent=2)
        print(f"  💾 {site_file} ({len(qa)} QA pairs)\n")

    # ── Combined output ────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_qa, f, ensure_ascii=False, indent=2)

    print(f"{'='*60}")
    print(f"✅ Done! Total: {len(all_qa)} QA pairs")
    print(f"{'='*60}")
    for site, count in site_counts.items():
        print(f"  {site}: {count}")
    print(f"\n  📦 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
