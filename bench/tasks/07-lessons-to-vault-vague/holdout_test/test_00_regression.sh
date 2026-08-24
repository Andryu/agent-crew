#!/bin/bash
# 回帰: 教訓ファイル自体は書き換えない（読み取りのみ）こと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_lessons
cp "$LESSONS_FILE" "$BENCH_TMP/lessons.before"

run_vault || fail "スクリプトが非ゼロで終了した"

cmp -s "$LESSONS_FILE" "$BENCH_TMP/lessons.before" \
  || fail "教訓ファイルが書き換えられた"

echo "PASS"
