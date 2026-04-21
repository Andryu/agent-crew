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

# ---------- エージェントプロファイル関数 ----------

get_agent_display_name() {
  case "$1" in
    Yuki) echo "Yuki (PM)" ;;
    Alex) echo "Alex (Architect)" ;;
    Mina) echo "Mina (UX)" ;;
    Riku) echo "Riku (Dev)" ;;
    Sora) echo "Sora (QA)" ;;
    Hana) echo "Hana (Review)" ;;
    Kai)  echo "Kai (Security)" ;;
    Tomo) echo "Tomo (DevOps)" ;;
    Ren)  echo "Ren (Data)" ;;
    *)    echo "agent-crew" ;;
  esac
}

get_agent_icon() {
  # Slack App 型 Webhook では icon_emoji override が効かないため
  # メッセージ本文に埋め込む Unicode 絵文字を返す
  case "$1" in
    Yuki) echo "📋" ;;
    Alex) echo "🏗️" ;;
    Mina) echo "🎨" ;;
    Riku) echo "🔨" ;;
    Sora) echo "🔍" ;;
    Hana) echo "📝" ;;
    Kai)  echo "🛡️" ;;
    Tomo) echo "🚀" ;;
    Ren)  echo "📊" ;;
    *)    echo "🤖" ;;
  esac
}

# slack_notify <agent> <message>
# SLACK_WEBHOOK_URL が未設定の場合はノーオペレーション
slack_notify() {
  local agent="$1" message="$2"
  [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0

  local display_name icon formatted payload
  display_name=$(get_agent_display_name "$agent")
  icon=$(get_agent_icon "$agent")
  # Slack App 型 Webhook では username/icon_emoji override が効かないため
  # メッセージ本文にアイコン+名前を埋め込む
  formatted="${icon} *${display_name}*: ${message}"

  payload=$(jq -n --arg text "$formatted" '{"text": $text}')

  curl -s --max-time 3 --connect-timeout 2 -X POST "$SLACK_WEBHOOK_URL" \
    -H 'Content-type: application/json' \
    -d "$payload" >/dev/null 2>&1
}

# build_done_message <agent> <slug> <next_agent>
build_done_message() {
  local agent="$1" slug="$2" next_agent="$3"
  case "$agent" in
    Yuki)  echo "✅ ${slug} のタスク分解が完了しました。チームに引き渡します。" ;;
    Alex)  echo "✅ ${slug} の設計が完了しました。${next_agent}に引き継ぎます。" ;;
    Mina)  echo "✅ ${slug} のデザイン、できました！${next_agent}に渡しますね。" ;;
    Riku)  echo "✅ ${slug} 実装完了！${next_agent}、レビューよろしく。" ;;
    Sora)  echo "✅ ${slug} レビュー完了。品質基準を満たしています — APPROVED" ;;
    Hana)  echo "✅ ${slug} のレビューが完了しました。問題ありません。" ;;
    Kai)   echo "✅ ${slug} のセキュリティレビュー完了。${next_agent} に引き継ぎます。" ;;
    Tomo)  echo "✅ ${slug} のインフラ設定が完了しました。${next_agent} に引き継ぎます。" ;;
    Ren)   echo "✅ ${slug} のデータ設計が完了しました。${next_agent} に引き継ぎます。" ;;
    *)     echo "✅ ${agent}: ${slug} が完了しました / 次: ${next_agent}" ;;
  esac
}

# build_block_message <agent> <slug> <reason>
build_block_message() {
  local agent="$1" slug="$2" reason="$3"
  case "$agent" in
    Yuki)  echo "🚧 ${slug} がブロックされています。オーナーの判断が必要です — ${reason}" ;;
    Alex)  echo "🚧 ${slug} の設計がブロックされました — ${reason}" ;;
    Mina)  echo "🚧 ${slug} のデザインで手が止まっています — ${reason}" ;;
    Riku)  echo "🚧 ${slug} ブロックされた。詰まってる — ${reason}" ;;
    Sora)  echo "🚧 ${slug} のQAがブロックされました — ${reason}" ;;
    Hana)  echo "🚧 ${slug} のレビューがブロックされました — ${reason}" ;;
    Kai)   echo "🚧 ${slug} のセキュリティレビューがブロックされました — ${reason}" ;;
    Tomo)  echo "🚧 ${slug} のインフラ作業がブロックされました — ${reason}" ;;
    Ren)   echo "🚧 ${slug} のデータ設計がブロックされました — ${reason}" ;;
    *)     echo "🚧 ${agent}: ${slug} がブロックされました — ${reason}" ;;
  esac
}

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
    first=true
    while IFS= read -r slug; do
      [[ -z "$slug" ]] && continue
      # block イベントから agent と msg を取得
      block_agent=$(jq -r --arg s "$slug" '
        .tasks[] | select(.slug == $s)
        | (.events // [])
        | map(select(.action == "block"))
        | last
        | (.agent // "agent-crew")
      ' "$QUEUE_FILE")
      block_msg=$(jq -r --arg s "$slug" '
        .tasks[] | select(.slug == $s)
        | (.events // [])
        | map(select(.action == "block"))
        | last
        | (.msg // "reason unknown")
      ' "$QUEUE_FILE")
      # 2件目以降はレート制限対応で sleep
      if [[ "$first" == "true" ]]; then
        first=false
      else
        sleep 1
      fi
      MESSAGE=$(build_block_message "$block_agent" "$slug" "$block_msg")
      slack_notify "$block_agent" "$MESSAGE"
    done <<< "$BLOCKED_SLUGS"
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
    # 直近の done イベントから完了したエージェント名を取得
    LAST_AGENT=$(jq -r '
      .tasks
      | map(.events // [])
      | flatten
      | map(select(.action == "done"))
      | last
      | .agent // "Yuki"
    ' "$QUEUE_FILE")
    AGENT_UPPER=$(echo "$AGENT" | tr '[:lower:]' '[:upper:]')
    MESSAGE=$(build_done_message "$LAST_AGENT" "$SLUG" "$AGENT_UPPER")
    slack_notify "$LAST_AGENT" "$MESSAGE"
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
    MESSAGE="🎉 ${SPRINT} 完了。全タスク DONE / QA APPROVED"
    slack_notify "Yuki" "$MESSAGE"
  fi

  # ---------- スプリント完了時の自動処理 ----------
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  QUEUE_SH="${SCRIPT_DIR}/../scripts/queue.sh"

  if [[ -x "$QUEUE_SH" ]]; then
    echo ""
    echo "リトロスペクティブを生成しています..."
    # リトロスペクティブ集計 + DECISIONS.md 追記
    "$QUEUE_SH" retro --save --decisions
    echo ""
    echo "依存グラフを保存しています..."
    # Mermaid 依存グラフを保存
    "$QUEUE_SH" graph --save
  fi
fi

exit 0
