#!/bin/bash
# true cause の修正確認: 重複ありの大きい入力で TOTAL == 部門合計の総和、かつ独立計算した正解と一致すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

ACTUAL_TOTAL=$(grep -E '^TOTAL: ' "$REPORT_OUT" | sed -E 's/^TOTAL: //')
EXPECTED_TOTAL=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['total'])" "$BENCH_TMP/expected.json")

[[ -n "$ACTUAL_TOTAL" ]] || fail "TOTAL 行が見つからない"
[[ "$ACTUAL_TOTAL" == "$EXPECTED_TOTAL" ]] \
  || fail "TOTAL が正しい合計と一致しない (actual=$ACTUAL_TOTAL expected=$EXPECTED_TOTAL)"

DEPT_SUM=$(grep -vE '^TOTAL: ' "$REPORT_OUT" | awk -F': ' '{s+=$2} END{print s+0}')
[[ "$DEPT_SUM" == "$EXPECTED_TOTAL" ]] \
  || fail "部門合計の総和が TOTAL と一致しない (dept_sum=$DEPT_SUM total=$ACTUAL_TOTAL)"

echo "PASS"
