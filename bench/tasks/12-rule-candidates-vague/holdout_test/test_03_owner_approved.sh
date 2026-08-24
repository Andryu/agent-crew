#!/bin/bash
# add --owner-approved: 保存されること・外部由来でも承認済みなら抽出対象になること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_empty_lessons
DESC_A="外部由来・未承認の教訓 $(t_rand 6 10000)"
DESC_B="外部由来・承認済みの教訓 $(t_rand 7 10000)"

run_lessons add \
  --project agent-crew --sprint sprint-32 --category tooling \
  --severity 3 --frequency 1 --type observation \
  --description "$DESC_A" --action "承認フローを通すこと" \
  --source-repo "https://github.com/external/foo" \
  || fail "未承認 add が失敗した"

run_lessons add \
  --project agent-crew --sprint sprint-32 --category qa \
  --severity 3 --frequency 1 --type observation \
  --description "$DESC_B" --action "承認済みとして扱うこと" \
  --source-repo "https://github.com/external/foo" \
  --owner-approved \
  || fail "--owner-approved 付き add が失敗した"

ID_A=$(jq -r --arg d "$DESC_A" '.lessons[] | select(.description == $d) | .id' "$LESSONS_FILE")
ID_B=$(jq -r --arg d "$DESC_B" '.lessons[] | select(.description == $d) | .id' "$LESSONS_FILE")
[[ -n "$ID_A" && -n "$ID_B" ]] || fail "追加レコードが見つからない"

[[ "$(jq -r --arg id "$ID_B" '.lessons[] | select(.id == $id) | .owner_approved' "$LESSONS_FILE")" == "true" ]] \
  || fail "--owner-approved が真偽値 true で保存されていない"
[[ "$(jq -r --arg id "$ID_A" '.lessons[] | select(.id == $id) | .owner_approved // false' "$LESSONS_FILE")" == "false" ]] \
  || fail "未指定の owner_approved が true になっている"

INC=$(list_ids --min-priority 1)
grep -qx "$ID_B" <<< "$INC" || fail "承認済みの外部由来教訓が抽出対象になっていない"
if grep -qx "$ID_A" <<< "$INC"; then
  fail "未承認の外部由来教訓が抽出対象に入っている"
fi

EXC=$(list_ids --min-priority 1 --excluded)
grep -qx "$ID_A" <<< "$EXC" || fail "未承認の外部由来教訓が --excluded に出ていない"
if grep -qx "$ID_B" <<< "$EXC"; then
  fail "承認済みの教訓まで --excluded に出ている"
fi

echo "PASS"
