#!/bin/bash
# 回帰: フックはキューファイルを一切書き換えない（読み取りのみ）こと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_queue "IN_PROGRESS" "DONE"
cp "$QUEUE_FILE" "$BENCH_TMP/queue.before"

run_hook || fail "フックが非ゼロで終了した"

cmp -s "$QUEUE_FILE" "$BENCH_TMP/queue.before" \
  || fail "フックがキューファイルを書き換えた"

echo "PASS"
