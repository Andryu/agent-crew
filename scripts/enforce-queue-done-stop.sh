#!/usr/bin/env bash
# scripts/enforce-queue-done-stop.sh
#
# SubagentStop フック用スクリプト（Issue #139）。
# サブエージェント（Riku/Sora/みゆきち/Alex等）が queue.sh done/qa/block を
# 呼ばずに応答を終えてしまい、_queue.json 上のタスクが IN_PROGRESS のまま
# 取り残される再発パターン（agent-crew-sprint-25-process-001 で2連続確認）
# への構造的対策。
#
# 設計方針（risk_level: high につき明記, enforce-retro-stop.sh の前例踏襲）:
#   このスクリプトは SubagentStop を「ブロック」しない（exit 2 は使わない）。
#   常に exit 0 で終了し、警告は stderr へのメッセージのみとする。
#
# バイパス条件（いずれか1つでも満たせば即 exit 0、警告なし）:
#   1. jq が使用できない
#   2. .claude/_queue.json が存在しない、または壊れている
#   3. .sprint フィールドがない（スプリント外のキュー）
#   4. IN_PROGRESS のタスクが1件も無い（＝該当タスクなし。既にDONE等も含む）
#
# 環境変数:
#   QUEUE_FILE  キューファイルパス（default: $REPO_ROOT/.claude/_queue.json）
#               QA実機検証（subagent-stop-enforce-qa）でコピーしたキューを
#               対象にテストする際に上書きする。

set -uo pipefail
# 注意: set -e は使わない。途中の jq コマンドが失敗しても
# 「警告を出さずに exit 0」へ安全にフォールスルーさせるため。

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [[ -z "$REPO_ROOT" ]]; then
  exit 0
fi

QUEUE_FILE="${QUEUE_FILE:-$REPO_ROOT/.claude/_queue.json}"

if [[ ! -f "$QUEUE_FILE" ]]; then
  exit 0
fi

if ! jq -e . "$QUEUE_FILE" >/dev/null 2>&1; then
  exit 0
fi

SPRINT=$(jq -r '.sprint // empty' "$QUEUE_FILE" 2>/dev/null)
if [[ -z "$SPRINT" ]]; then
  exit 0
fi

# --- IN_PROGRESS タスクのうち、start イベント以降に何も記録されていないものを検出 ---
STALE_TASKS=$(jq -r '
  .tasks[]?
  | select(.status == "IN_PROGRESS")
  | select(((.events // []) | map(select(.action != "start")) | length) == 0)
  | .slug + "|" + (.assigned_to // "unknown")
' "$QUEUE_FILE" 2>/dev/null)

if [[ -z "$STALE_TASKS" ]]; then
  exit 0
fi

{
  echo ""
  echo "⚠️  [enforce-queue-done-stop] スプリント '${SPRINT}' に、start 後まだ"
  echo "    done/qa/block が記録されていない IN_PROGRESS タスクがあります:"
  while IFS='|' read -r slug agent; do
    [[ -z "$slug" ]] && continue
    echo "      - ${slug}（担当: ${agent}）"
  done <<< "$STALE_TASKS"
  echo "    queue.sh done/qa/block の実行を忘れていないか確認してください。"
  echo "    （このメッセージは警告のみで、処理はブロックされません）"
  echo ""
} >&2

exit 0
