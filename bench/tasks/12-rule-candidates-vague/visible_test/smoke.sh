#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物・固定値）:
#   list-rule-candidates が自リポジトリ由来の proposed だけを返すことを確かめる。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/repo"
git -C "$TMP/repo" init -q
git -C "$TMP/repo" remote add origin "git@github.com:benchuser/myrepo.git"

jq -n '{
  schema_version: "1.3.0",
  lessons: [
    {id: "smoke-own", priority_score: 4, status: "proposed", enforcement: "prompt",
     source_repo: "https://github.com/benchuser/myrepo", owner_approved: false,
     category: "tooling", sprint: "sprint-30",
     description: "visible smoke own", action: "確認する"},
    {id: "smoke-ext", priority_score: 4, status: "proposed", enforcement: "prompt",
     source_repo: "https://github.com/external/repo", owner_approved: false,
     category: "tooling", sprint: "sprint-30",
     description: "visible smoke ext", action: "確認する"}
  ]
}' > "$TMP/_lessons.json"

IDS=$(
  cd "$TMP/repo" &&
  env LESSONS_FILE="$TMP/_lessons.json" LOCK_FILE="$TMP/.lock" \
    bash "$WORK/scripts/lessons.sh" list-rule-candidates | jq -r '.id'
)
[[ "$IDS" == "smoke-own" ]] \
  || { echo "NG: 期待 smoke-own のみ、実際: $IDS" >&2; exit 1; }
echo "visible smoke: OK"
