#!/bin/bash
# 冪等性: 2回実行しても vault の中身がバイト単位で変わらないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_lessons
run_vault || fail "1回目の実行が非ゼロで終了した"

snapshot() {
  (cd "$VAULT_DIR" && find . -type f | sort | xargs shasum)
}
SUM1=$(snapshot)
[[ -n "$SUM1" ]] || fail "1回目の実行で何も生成されていない"

run_vault || fail "2回目の実行が非ゼロで終了した"
SUM2=$(snapshot)

[[ "$SUM1" == "$SUM2" ]] || fail "2回目の実行で vault の中身が変わった"

echo "PASS"
