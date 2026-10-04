#!/bin/bash
# 回帰: add の既存の動き（追記・priority計算・既存レコード保持・id採番）が壊れていないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

SAMPLE_BEFORE=$(sample_record)

run_add || fail "add が非ゼロで終了した"

[[ "$(lesson_count)" == "2" ]] || fail "レコード数が 2 になっていない（$(lesson_count)）"
REC=$(added_record)
[[ -n "$REC" ]] || fail "追加したレコードが見つからない"

[[ "$(jq -r '.project' <<< "$REC")" == "agent-crew" ]] || fail "project が保存されていない"
[[ "$(jq -r '.sprint' <<< "$REC")" == "$SPRINT" ]] || fail "sprint が保存されていない"
[[ "$(jq -r '.priority_score' <<< "$REC")" == "$(( SEV * FREQ ))" ]] \
  || fail "priority_score が severity×frequency ($(( SEV * FREQ ))) になっていない"

ID=$(jq -r '.id' <<< "$REC")
[[ -n "$ID" && "$ID" != "null" && "$ID" != "$SAMPLE_ID" ]] || fail "id が採番されていない: '$ID'"

[[ "$(sample_record)" == "$SAMPLE_BEFORE" ]] || fail "既存レコードが変更された"

# 必須オプション検査: --description 抜きは失敗し、ファイルは変わらないこと
cp "$LESSONS_FILE" "$BENCH_TMP/before_invalid.json"
if run_lessons add --project agent-crew --sprint "$SPRINT" --category tooling \
     --severity "$SEV" --frequency "$FREQ" --action "$ACTION" 2>/dev/null; then
  fail "必須オプション欠如でも add が成功してしまう"
fi
cmp -s "$LESSONS_FILE" "$BENCH_TMP/before_invalid.json" \
  || fail "失敗した add がファイルを書き換えた"

echo "PASS"
