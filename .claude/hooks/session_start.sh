#!/bin/bash
# .claude/hooks/session_start.sh
# Start hook: セッション開始時に未完了タスクと直近 lesson を表示する

set -u

# ---------- 1. 1セッション1回制限 ----------
SESSION_FLAG="/tmp/claude_session_start_${PPID}.lock"
if [[ -f "$SESSION_FLAG" ]]; then
  exit 0
fi
touch "$SESSION_FLAG" 2>/dev/null || true

# ---------- 2. 依存チェック ----------
if ! command -v jq >/dev/null 2>&1; then
  echo "WARN: jq not found, session_start hook is degraded" >&2
  exit 0
fi

# ---------- 3. 設定 ----------
QUEUE_FILE=".claude/_queue.json"
LESSONS_FILE="${LESSONS_FILE:-$HOME/.claude/_lessons.json}"

# プロジェクト名取得（git remote → ディレクトリ名フォールバック）
PROJECT=$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')
if [[ -z "$PROJECT" ]]; then
  PROJECT=$(basename "$(pwd)")
fi

# スプリント名取得
SPRINT=$(jq -r '.sprint // "unknown"' "$QUEUE_FILE" 2>/dev/null || echo "unknown")

# ---------- 4. ヘッダー ----------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SESSION START — ${PROJECT} / ${SPRINT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ---------- 5. 未完了タスク ----------
echo "[未完了タスク]"
if [[ -f "$QUEUE_FILE" ]]; then
  INCOMPLETE=$(jq -r '
    .tasks[] |
    select(.status != "DONE") |
    "  [\(.status)] \(.slug) — \(.title)"
  ' "$QUEUE_FILE" 2>/dev/null)
  if [[ -n "$INCOMPLETE" ]]; then
    echo "$INCOMPLETE"
  else
    echo "  (なし — 全タスク完了済み)"
  fi
else
  echo "  (_queue.json が見つかりません)"
fi

echo ""

# スタック検出
DETECTED_STACK="null"
if [[ -f "go.mod" ]]; then
  DETECTED_STACK="go"
# shellcheck disable=SC2010
elif ls next.config.* 1> /dev/null 2>&1; then
  DETECTED_STACK="next"
elif [[ -f "package.json" ]] && grep -q '"vue"' package.json 2>/dev/null; then
  DETECTED_STACK="vue"
fi

# ---------- 6. 直近 lesson ----------
echo "[直近 lesson（関連スコープ / 未対処 / priority 上位5件）]"
if [[ -f "$LESSONS_FILE" ]]; then
  LESSONS=$(jq -r --arg proj "$PROJECT" --arg stack "$DETECTED_STACK" '
    [
      .lessons[] |
      select(
        (
          (.scope == "global") or
          (.scope == "stack" and .stack == $stack) or
          ((.scope == "project" or .scope == null) and .project == $proj)
        ) and
        (.issue_url == null)
      )
    ] |
    unique_by(.description) |
    sort_by([.priority_score, .created_at]) | reverse |
    .[0:5][] |
    "  [\(.scope // "project")] [score:\(.priority_score)] [\(.category)] \(.description | .[0:60])\(if (.description | length) > 60 then "..." else "" end)"
  ' "$LESSONS_FILE" 2>/dev/null)
  if [[ -n "$LESSONS" ]]; then
    echo "$LESSONS"
  else
    echo "  (なし — 対象 lesson がありません)"
  fi
else
  echo "  (なし — ~/.claude/_lessons.json が存在しません)"
  echo "  初回セットアップ: scripts/lessons_init.sh を実行してください"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exit 0
