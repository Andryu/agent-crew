#!/bin/bash
# add --status に5種類以外を渡すとエラー終了し、ファイルは変わらないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# 前提確認: --status オプション自体が実装されていること
run_add --status verified >/dev/null 2>&1 || fail "前提: 正しい --status 指定の add が失敗する"
[[ "$(added_record | jq -r '.status')" == "verified" ]] \
  || fail "前提: --status が保存されていない"

cp "$LESSONS_FILE" "$BENCH_TMP/before.json"
if run_add --status "bogus-$(t_rand 7 1000)" 2>/dev/null; then
  fail "不正な --status でも add が成功してしまう"
fi
cmp -s "$LESSONS_FILE" "$BENCH_TMP/before.json" \
  || fail "失敗した add がファイルを書き換えた"

echo "PASS"
