#!/bin/bash
# set-status が対象レコードの status だけを更新すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_add || fail "準備の add が失敗した"
ID=$(added_record | jq -r '.id')
[[ -n "$ID" && "$ID" != "null" ]] || fail "追加レコードの id が取れない"

CANDIDATES=(issue_created implemented verified dismissed)
NEW_STATUS="${CANDIDATES[$(t_rand 8 4)]}"

TARGET_BEFORE=$(added_record | jq -cS 'del(.status, .updated_at)')
SAMPLE_BEFORE=$(sample_record)

run_lessons set-status "$ID" "$NEW_STATUS" || fail "set-status が非ゼロで終了した"

[[ "$(added_record | jq -r '.status')" == "$NEW_STATUS" ]] \
  || fail "status が $NEW_STATUS に更新されていない"
[[ "$(added_record | jq -cS 'del(.status, .updated_at)')" == "$TARGET_BEFORE" ]] \
  || fail "対象レコードの status 以外のフィールドが変わった"
[[ "$(sample_record)" == "$SAMPLE_BEFORE" ]] \
  || fail "対象外レコードが変更された"

echo "PASS"
