#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物・固定値）:
#   add の status 既定値と set-status の基本動作を確かめる。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo '{"schema_version":"1.1.0","lessons":[]}' > "$TMP/_lessons.json"

run() {
  (
    cd "$WORK" &&
    env LESSONS_FILE="$TMP/_lessons.json" LOCK_FILE="$TMP/.lock" \
      bash scripts/lessons.sh "$@"
  )
}

run add --project agent-crew --sprint sprint-05 --category tooling \
  --severity 2 --frequency 2 \
  --description "visible smoke 用のレコードです" --action "手順に従う" >/dev/null

ID=$(jq -r '.lessons[0].id' "$TMP/_lessons.json")
[[ "$(jq -r '.lessons[0].status' "$TMP/_lessons.json")" == "proposed" ]] \
  || { echo "NG: 既定 status が proposed でない" >&2; exit 1; }

run set-status "$ID" verified >/dev/null
[[ "$(jq -r '.lessons[0].status' "$TMP/_lessons.json")" == "verified" ]] \
  || { echo "NG: set-status が反映されていない" >&2; exit 1; }

echo "visible smoke: OK"
