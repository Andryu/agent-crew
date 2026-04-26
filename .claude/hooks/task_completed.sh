#!/bin/bash
# .claude/hooks/task_completed.sh
# TaskCompleted フック: タスク完了時に _signals.jsonl へシグナルを emit する
#
# 役割:
# - IN_PROGRESS タスクの slug/agent/sprint を _queue.json から取得
# - _signals.jsonl に task_completed シグナルを記録（観測用）
#
# SubagentStop との責務分離:
# - TaskCompleted: シグナル emit（観測）
# - SubagentStop:  次ステップ提示・完了宣言・Slack通知（オーケストレーション）

set -euo pipefail

QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"
SIGNALS_FILE="${SIGNALS_FILE:-.claude/_signals.jsonl}"

# 依存チェック
if ! command -v jq >/dev/null 2>&1; then
  echo "WARN: jq not found, task_completed hook is degraded" >&2
  exit 0
fi

if [[ ! -f "$QUEUE_FILE" ]]; then
  exit 0
fi

# IN_PROGRESS タスクを取得（複数ある場合は最初の1件）
SLUG=$(jq -r '
  .tasks
  | map(select(.status == "IN_PROGRESS"))
  | first
  | .slug // empty
' "$QUEUE_FILE" 2>/dev/null || true)

AGENT=$(jq -r '
  .tasks
  | map(select(.status == "IN_PROGRESS"))
  | first
  | .assigned_to // "unknown"
' "$QUEUE_FILE" 2>/dev/null || true)

SPRINT=$(jq -r '.sprint // "unknown"' "$QUEUE_FILE" 2>/dev/null || true)

# IN_PROGRESS タスクがなければ何もしない
if [[ -z "$SLUG" ]]; then
  exit 0
fi

TS=$(date -u +"%Y-%m-%dT%H:%M:%S+0000")
TOOL_USE_ID="${CLAUDE_TOOL_USE_ID:-unknown}"

# シグナル emit
SIGNAL=$(jq -cn \
  --arg ts "$TS" \
  --arg sprint "$SPRINT" \
  --arg slug "$SLUG" \
  --arg agent "$AGENT" \
  --arg event "task_completed" \
  --arg tool_use_id "$TOOL_USE_ID" \
  '{ts: $ts, sprint: $sprint, slug: $slug, agent: $agent, event: $event, tool_use_id: $tool_use_id}')

echo "$SIGNAL" >> "$SIGNALS_FILE"

echo "TASK_COMPLETED: $SLUG ($AGENT) @ $TS" >&2

exit 0
