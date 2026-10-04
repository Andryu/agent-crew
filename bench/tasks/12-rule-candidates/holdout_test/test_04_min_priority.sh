#!/bin/bash
# --min-priority: 数値以外はエラー終了・省略時の既定値は 3
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# 既定値 3 の確認用 fixture（自リポジトリ由来・proposed のみ）
ID_P3="bench-p3-$SUF"
ID_P2="bench-p2-$SUF"
{
  mk_lesson "$ID_P3" tooling 3 '"proposed"' prompt "\"${OWN_HTTPS}\"" false
  mk_lesson "$ID_P2" tooling 2 '"proposed"' prompt "\"${OWN_HTTPS}\"" false
} | jq -s '{schema_version: "1.3.0", lessons: .}' > "$LESSONS_FILE"

# 前提確認: 数値指定は動く
run_lessons list-rule-candidates --min-priority 3 >/dev/null \
  || fail "前提: --min-priority 3 の実行が失敗した"

# 本題1: 数値以外はエラー終了
if run_lessons list-rule-candidates --min-priority abc >/dev/null 2>&1; then
  fail "--min-priority abc がエラーにならない"
fi

# 本題2: 省略時の既定値は 3（priority 3 は入り、2 は入らない）
GOT=$(list_ids)
grep -qx "$ID_P3" <<< "$GOT" || fail "既定しきい値で priority 3 が抽出されない"
if grep -qx "$ID_P2" <<< "$GOT"; then
  fail "既定しきい値で priority 2 まで抽出されている"
fi

echo "PASS"
