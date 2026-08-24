#!/bin/bash
# 抽出条件の全組み合わせ: priority境界・status・enforcement・信頼境界（表記ゆれ含む）
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_combo_lessons

GOT=$(list_ids --min-priority "$MINP") || fail "list-rule-candidates が失敗した"
WANT=$(combo_expected_ids)

[[ "$GOT" == "$WANT" ]] || fail "抽出結果が期待と違う
--- 期待 ---
$WANT
--- 実際 ---
$GOT"

# 出力が1行1JSONで、元のレコード内容を含むこと
run_lessons list-rule-candidates --min-priority "$MINP" | while IFS= read -r line; do
  jq -e '.id' >/dev/null <<< "$line" || exit 1
done || fail "出力が1行1JSONになっていない"

echo "PASS"
