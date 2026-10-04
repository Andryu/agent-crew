#!/bin/bash
# 回帰: add / set-status / promote の既存の動きが壊れていないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_empty_lessons
SEV=$(( 1 + $(t_rand 3 3) ))
FREQ=$(( 1 + $(t_rand 4 3) ))
DESC="ベンチ回帰確認用の教訓レコード $(t_rand 5 10000)"

run_lessons add \
  --project agent-crew --sprint sprint-31 --category tooling \
  --severity "$SEV" --frequency "$FREQ" \
  --description "$DESC" --action "ベンチ手順に従うこと" \
  --type observation \
  || fail "add が非ゼロで終了した"

REC=$(jq -c --arg d "$DESC" '.lessons[] | select(.description == $d)' "$LESSONS_FILE")
[[ -n "$REC" ]] || fail "追加したレコードが見つからない"
ID=$(jq -r '.id' <<< "$REC")
[[ -n "$ID" && "$ID" != "null" ]] || fail "id が採番されていない"
[[ "$(jq -r '.priority_score' <<< "$REC")" == "$(( SEV * FREQ ))" ]] \
  || fail "priority_score が severity×frequency になっていない"
[[ "$(jq -r '.status' <<< "$REC")" == "proposed" ]] || fail "status の既定値が proposed でない"
[[ "$(jq -r '.scope' <<< "$REC")" == "project" ]] || fail "scope の既定値が project でない"

run_lessons set-status "$ID" implemented >/dev/null || fail "set-status が非ゼロで終了した"
[[ "$(jq -r --arg id "$ID" '.lessons[] | select(.id == $id) | .status' "$LESSONS_FILE")" == "implemented" ]] \
  || fail "set-status が反映されていない"
[[ "$(jq -r --arg id "$ID" '.lessons[] | select(.id == $id) | .description' "$LESSONS_FILE")" == "$DESC" ]] \
  || fail "set-status が他フィールドを壊した"

run_lessons promote "$ID" global >/dev/null || fail "promote が非ゼロで終了した"
[[ "$(jq -r --arg id "$ID" '.lessons[] | select(.id == $id) | .scope' "$LESSONS_FILE")" == "global" ]] \
  || fail "promote が scope を更新していない"

echo "PASS"
