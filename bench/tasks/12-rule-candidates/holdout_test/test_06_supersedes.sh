#!/bin/bash
# add --supersedes: 存在しないIDはエラー終了して何も書かず、存在するIDは保存される
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

ID_BASE="bench-base-$SUF"
{
  mk_lesson "$ID_BASE" tooling 3 '"proposed"' prompt "\"${OWN_HTTPS}\"" false
} | jq -s '{schema_version: "1.3.0", lessons: .}' > "$LESSONS_FILE"

DESC_OK="改訂版の教訓レコード $(t_rand 8 10000)"

cp "$LESSONS_FILE" "$BENCH_TMP/before.json"
if run_lessons add \
     --project agent-crew --sprint sprint-33 --category tooling \
     --severity 1 --frequency 2 --type observation \
     --description "存在しないIDを指す改訂の試み" --action "IDを確認すること" \
     --supersedes "no-such-id-$(t_rand 9 10000)" 2>/dev/null; then
  fail "存在しない --supersedes でも add が成功してしまう"
fi
cmp -s "$LESSONS_FILE" "$BENCH_TMP/before.json" \
  || fail "失敗した add がファイルを書き換えた"

run_lessons add \
  --project agent-crew --sprint sprint-33 --category tooling \
  --severity 1 --frequency 2 --type observation \
  --description "$DESC_OK" --action "旧教訓を置き換えること" \
  --supersedes "$ID_BASE" \
  || fail "存在するIDへの --supersedes 付き add が失敗した"

[[ "$(jq -r --arg d "$DESC_OK" '.lessons[] | select(.description == $d) | .supersedes' "$LESSONS_FILE")" == "$ID_BASE" ]] \
  || fail "--supersedes が保存されていない"

echo "PASS"
