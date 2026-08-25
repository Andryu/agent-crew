#!/bin/bash
# 制約確認: summarize() の戻り値の形（部門名 -> 金額の辞書）が変わっていないこと
set -euo pipefail
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

python3 - "$BENCH_WORK_DIR" <<'PYEOF' || fail "summarize() の戻り値の形が壊れている"
import sys
import importlib.util

work_dir = sys.argv[1]
spec = importlib.util.spec_from_file_location("report", work_dir + "/report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)

entries = [
    {"id": 1, "department": "営業", "amount": 100},
    {"id": 2, "department": "開発", "amount": 200},
    {"id": 3, "department": "営業", "amount": 50},
]
result = report.summarize(entries)
assert isinstance(result, dict), f"dict でない: {type(result)}"
assert result.get("営業") == 150, f"営業の合計が不正: {result}"
assert result.get("開発") == 200, f"開発の合計が不正: {result}"
assert set(result.keys()) <= {"営業", "開発"}, f"想定外のキー: {result}"
PYEOF

echo "PASS"
