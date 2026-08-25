#!/usr/bin/env python3
"""entries.jsonl を読み、部門ごとの合計と全体合計を表示する。"""
import json
import sys


def load_entries(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def dedupe(entries):
    """同じ id のエントリ（リトライによる重複記録）を除去する。最初に見つかった方を残す。"""
    seen = set()
    result = []
    for e in entries:
        key = e["id"]
        if key in seen:
            continue
        seen.add(key)
        result.append(e)
    return result


def summarize(entries):
    """部門名 -> 合計金額の辞書を返す。"""
    deduped = dedupe(entries)
    totals = {}
    for e in deduped:
        dept = e["department"]
        totals[dept] = totals.get(dept, 0) + e["amount"]
    return totals


def total_amount(entries):
    """全件の合計金額を返す。"""
    return sum(e["amount"] for e in entries)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "entries.jsonl"
    entries = load_entries(path)
    totals = summarize(entries)
    for dept in sorted(totals):
        print(f"{dept}: {totals[dept]}")
    print(f"TOTAL: {total_amount(entries)}")


if __name__ == "__main__":
    main()
