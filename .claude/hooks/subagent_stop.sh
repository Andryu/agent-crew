#!/bin/bash
# .claude/hooks/subagent_stop.sh
# SubagentStop フック：エージェント完了後に次のステップを提示 + Slack通知
#
# 役割:
# 1. BLOCKED タスクがあればアラート（最優先）
# 2. READY_FOR_* のタスクがあれば次担当を提示
# 3. 全タスクが DONE かつ qa_result=APPROVED ならスプリント完了宣言
# 4. SLACK_WEBHOOK_URL が設定されていれば通知

set -u

QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"

if [[ ! -f "$QUEUE_FILE" ]]; then
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "WARN: jq not found, subagent_stop hook is degraded" >&2
  exit 0
fi

# ---------- 1. BLOCKED の検出（最優先）----------
BLOCKED_SLUGS=$(jq -r '.tasks[] | select(.status == "BLOCKED") | .slug' "$QUEUE_FILE" 2>/dev/null)
if [[ -n "$BLOCKED_SLUGS" ]]; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🚧 BLOCKED タスクがあります"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  while IFS= read -r slug; do
    [[ -z "$slug" ]] && continue
    note=$(jq -r --arg s "$slug" '.tasks[] | select(.slug == $s) | (.events // []) | map(select(.action == "block")) | last | (.msg // "reason unknown")' "$QUEUE_FILE")
    echo "  - $slug: $note"
  done <<< "$BLOCKED_SLUGS"
  echo ""
  echo "オーナー（人間）の判断が必要です。"
  echo "解除するには notes を確認してから scripts/queue.sh handoff <slug> <agent> で再投入してください。"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    MESSAGE="🚧 *agent-crew*: BLOCKED タスクが発生しました"
    curl -s --max-time 3 --connect-timeout 2 -X POST "$SLACK_WEBHOOK_URL" -H 'Content-type: application/json' -d "{\"text\": \"$MESSAGE\"}" >/dev/null 2>&1
  fi
  exit 0
fi

# ---------- 2. 次の READY_FOR_* を提示 ----------
NEXT=$(jq -r '
  .tasks
  | map(select(.status | startswith("READY_FOR_")))
  | first
  | if . == null then empty
    else .slug + "|" + (.status | sub("READY_FOR_"; "") | ascii_downcase) + "|" + .title
    end
' "$QUEUE_FILE" 2>/dev/null)

if [[ -n "$NEXT" ]]; then
  SLUG=$(echo "$NEXT" | cut -d'|' -f1)
  AGENT=$(echo "$NEXT" | cut -d'|' -f2)
  TITLE=$(echo "$NEXT" | cut -d'|' -f3)

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🔔 YUKI: 次のステップの提案"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "タスク: $TITLE ($SLUG)"
  echo "次の担当: $AGENT"
  echo ""
  echo "実行するには以下をコピーしてください:"
  echo "  Use the $AGENT agent on \"$SLUG\""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    AGENT_UPPER=$(echo "$AGENT" | tr '[:lower:]' '[:upper:]')
    MESSAGE="✅ $TITLE ($SLUG) のフェーズが完了しました / 次: $AGENT_UPPER"
    curl -s --max-time 3 --connect-timeout 2 -X POST "$SLACK_WEBHOOK_URL" -H 'Content-type: application/json' -d "{\"text\": \"$MESSAGE\"}" >/dev/null 2>&1
  fi
  exit 0
fi

# ---------- 3. スプリント完了判定 ----------
INCOMPLETE=$(jq -r '.tasks | map(select(.status != "DONE")) | length' "$QUEUE_FILE" 2>/dev/null)
QA_PENDING=$(jq -r '.tasks | map(select(.assigned_to == "Sora" and (.qa_result // null) != "APPROVED")) | length' "$QUEUE_FILE" 2>/dev/null)

if [[ "$INCOMPLETE" == "0" && "$QA_PENDING" == "0" ]]; then
  SPRINT=$(jq -r '.sprint // "sprint"' "$QUEUE_FILE")
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🎉 $SPRINT 完了"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "全タスク DONE、QA判定すべて APPROVED です。"
  echo "オーナーへの最終報告を推奨します。"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    MESSAGE="🎉 agent-crew: $SPRINT 完了。全タスクDONE / QA APPROVED"
    curl -s --max-time 3 --connect-timeout 2 -X POST "$SLACK_WEBHOOK_URL" -H 'Content-type: application/json' -d "{\"text\": \"$MESSAGE\"}" >/dev/null 2>&1
  fi
fi

exit 0
