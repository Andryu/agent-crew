#!/bin/bash
# set-status に存在しない id を渡すと非ゼロ終了し、ファイルは変わらないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# 前提確認: set-status コマンド自体が実装されていること
run_lessons set-status "$SAMPLE_ID" verified >/dev/null 2>&1 \
  || fail "前提: 正しい引数の set-status が失敗する"
[[ "$(sample_record | jq -r '.status')" == "verified" ]] \
  || fail "前提: set-status が反映されていない"

cp "$LESSONS_FILE" "$BENCH_TMP/before.json"
if run_lessons set-status "no-such-id-$(t_rand 10 10000)" verified 2>/dev/null; then
  fail "存在しない id でも set-status が成功してしまう"
fi
cmp -s "$LESSONS_FILE" "$BENCH_TMP/before.json" \
  || fail "失敗した set-status がファイルを書き換えた"

echo "PASS"
