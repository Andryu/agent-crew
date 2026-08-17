#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物・固定値）:
#   IN_PROGRESS 1件で task_completed シグナルが1行追記されることを確かめる。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

jq -n '{
  sprint: "sprint-17",
  tasks: [{slug: "smoke-hook", title: "smoke", status: "IN_PROGRESS",
           assigned_to: "Riku", created_at: "2026-01-01", updated_at: "2026-01-01",
           notes: "", events: [], retry_count: 0, qa_result: null, summary: null}]
}' > "$TMP/_queue.json"

(
  cd "$WORK" &&
  env QUEUE_FILE="$TMP/_queue.json" SIGNALS_FILE="$TMP/_signals.jsonl" \
    bash .claude/hooks/task_completed.sh
)

[[ "$(wc -l < "$TMP/_signals.jsonl" | tr -d ' ')" == "1" ]] \
  || { echo "NG: シグナルが1行になっていない" >&2; exit 1; }
jq -e 'select(.event == "task_completed" and .slug == "smoke-hook")' \
  "$TMP/_signals.jsonl" >/dev/null \
  || { echo "NG: シグナル内容が想定と違う" >&2; exit 1; }
echo "visible smoke: OK"
