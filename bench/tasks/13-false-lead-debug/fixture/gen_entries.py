#!/usr/bin/env python3
"""entries.jsonl を決定的に生成する（bench 内部用。setup.sh / holdout_test から呼ぶ）。

使い方: gen_entries.py <seed> <count> <dup_rate_percent> > entries.jsonl

dup_rate_percent はイベントがリトライで重複記録される確率（%）。
0 にすると重複なしの入力になる（小さい件数・症状が再現しない側の fixture 用）。
"""
import json
import random
import sys

DEPARTMENTS = ["営業", "開発", "総務", "マーケティング", "サポート"]


def main():
    seed = int(sys.argv[1])
    count = int(sys.argv[2])
    dup_rate = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    rng = random.Random(seed)
    entries = []
    next_id = 1
    for _ in range(count):
        dept = rng.choice(DEPARTMENTS)
        amount = rng.randint(500, 50000)
        entries.append({"id": next_id, "department": dept, "amount": amount})
        next_id += 1
        if rng.randint(1, 100) <= dup_rate:
            entries.append(dict(entries[-1]))  # リトライによる重複記録

    rng.shuffle(entries)
    for e in entries:
        print(json.dumps(e, ensure_ascii=False))


if __name__ == "__main__":
    main()
