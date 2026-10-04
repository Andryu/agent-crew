#!/bin/bash
# regression: 同梱 entries.jsonl（小さめ・重複なし）に対して基本動作・出力フォーマットが壊れていないこと
set -euo pipefail
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

OUT=$(cd "$BENCH_WORK_DIR" && python3 report.py entries.jsonl) || fail "report.py が失敗した"
echo "$OUT" | grep -qE '^TOTAL: [0-9]+$' || fail "TOTAL 行の形式が壊れている"
echo "$OUT" | grep -qE '^[^:]+: [0-9]+$' || fail "部門行の形式が壊れている"

echo "PASS"
