#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物・固定値）:
#   priority 4 の教訓が sprint-24 のファイルに転記されることを確かめる。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/vault" "$TMP/home"

jq -n '{
  schema_version: "1.1.0",
  lessons: [
    {id: "smoke-001", project: "agent-crew", sprint: "sprint-24",
     category: "tooling", type: "failure", priority_score: 4,
     description: "visible smoke 用の教訓", action: "確認する"}
  ]
}' > "$TMP/_lessons.json"

(
  cd "$WORK" &&
  env HOME="$TMP/home" VAULT_DIR="$TMP/vault" LESSONS_FILE="$TMP/_lessons.json" \
    bash scripts/lessons-to-vault.sh
)

OUT="$TMP/vault/inbox/agent-crew-lessons-sprint-24.md"
[[ -f "$OUT" ]] || { echo "NG: 出力ファイルが無い" >&2; exit 1; }
grep -q "smoke-001" "$OUT" || { echo "NG: 教訓 id が入っていない" >&2; exit 1; }
echo "visible smoke: OK"
