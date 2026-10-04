#!/bin/bash
# false lead (dedupe) を壊さず、部門ごとの金額が重複除去後の正しい値と一致すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

python3 - "$REPORT_OUT" "$BENCH_TMP/expected.json" <<'PYEOF' || fail "部門別の金額が正解と一致しない"
import json
import sys

report_out_path, expected_path = sys.argv[1], sys.argv[2]
actual = {}
for line in open(report_out_path):
    line = line.strip()
    if not line or line.startswith("TOTAL:"):
        continue
    dept, amount = line.rsplit(": ", 1)
    actual[dept] = int(amount)

expected = json.load(open(expected_path))["totals"]
assert actual == expected, f"actual={actual} expected={expected}"
PYEOF

echo "PASS"
