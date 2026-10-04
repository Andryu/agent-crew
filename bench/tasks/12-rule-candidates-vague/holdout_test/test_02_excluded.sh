#!/bin/bash
# --excluded は「信頼境界のみで落ちた」教訓だけを出す
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_combo_lessons

# 前提確認: 通常の抽出が動くこと
[[ -n "$(list_ids --min-priority "$MINP")" ]] || fail "前提: 通常の抽出が空"

GOT=$(list_ids --min-priority "$MINP" --excluded) || fail "--excluded 付きの実行が失敗した"
WANT="$ID_EXT"

[[ "$GOT" == "$WANT" ]] || fail "--excluded の結果が期待と違う（優先度/status/enforcement 落ちを混ぜていないか）
--- 期待 ---
$WANT
--- 実際 ---
$GOT"

echo "PASS"
