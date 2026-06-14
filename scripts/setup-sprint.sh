#!/bin/bash
# scripts/setup-sprint.sh
# 別リポジトリへのスプリント管理機能セットアップスクリプト
#
# 使い方:
#   bash /path/to/agent-crew/scripts/setup-sprint.sh [TARGET_REPO_PATH] [SPRINT_NAME]
#
# 例:
#   bash ~/Workspace/agent-crew/scripts/setup-sprint.sh . sprint-1
#   bash ~/Workspace/agent-crew/scripts/setup-sprint.sh ~/Workspace/my-project

set -euo pipefail

AGENT_CREW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-.}"
SPRINT_NAME="${2:-sprint-1}"

# --help
if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
  cat <<EOF
使い方: $0 [TARGET_REPO_PATH] [SPRINT_NAME]

  TARGET_REPO_PATH  スプリント機能を追加するリポジトリのパス（デフォルト: カレントディレクトリ）
  SPRINT_NAME       初期スプリント名（デフォルト: sprint-1）

例:
  $0 .                                    # カレントディレクトリに追加
  $0 ~/Workspace/my-project sprint-1     # 別リポジトリに追加

実行内容:
  1. TARGET/.claude/hooks/ にスプリントフックをシンボリックリンク
  2. TARGET/.claude/_queue.json が存在しない場合、空のキューを作成
  3. TARGET/.claude/settings.json に hooks エントリを追記（存在しない場合は新規作成）
EOF
  exit 0
fi

TARGET="$(cd "$TARGET" && pwd)"

echo "=== agent-crew スプリント機能セットアップ ==="
echo "対象リポジトリ: $TARGET"
echo "agent-crew:     $AGENT_CREW_DIR"
echo "スプリント名:    $SPRINT_NAME"
echo ""

# ---------- 1. .claude/hooks/ にシンボリックリンクを作成 ----------
HOOKS_DIR="$TARGET/.claude/hooks"
mkdir -p "$HOOKS_DIR"

for hook in task_completed subagent_stop session_start; do
  SRC="$AGENT_CREW_DIR/.claude/hooks/${hook}.sh"
  DST="$HOOKS_DIR/${hook}.sh"
  if [[ ! -f "$SRC" ]]; then
    echo "WARN: $SRC が見つかりません。スキップします。" >&2
    continue
  fi
  if [[ -L "$DST" ]]; then
    echo "  [SKIP]    $DST (既にシンボリックリンク済み)"
  else
    ln -sf "$SRC" "$DST"
    echo "  [SYMLINK] $DST -> $SRC"
  fi
done
echo ""

# ---------- 2. _queue.json が存在しない場合に作成 ----------
QUEUE_FILE="$TARGET/.claude/_queue.json"
if [[ -f "$QUEUE_FILE" ]]; then
  echo "  [SKIP]    $QUEUE_FILE (既に存在)"
else
  cat > "$QUEUE_FILE" <<QUEUEEOF
{
  "sprint": "${SPRINT_NAME}",
  "tasks": []
}
QUEUEEOF
  echo "  [CREATE]  $QUEUE_FILE"
fi
echo ""

# ---------- 3. settings.json に hooks エントリを追記 ----------
SETTINGS_FILE="$TARGET/.claude/settings.json"

HOOKS_SNIPPET=$(cat <<'SNIPPET'
{
  "hooks": {
    "TaskCompleted": [
      { "hooks": [{ "type": "command", "command": ".claude/hooks/task_completed.sh" }] }
    ],
    "SubagentStop": [
      { "hooks": [{ "type": "command", "command": ".claude/hooks/subagent_stop.sh" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": ".claude/hooks/subagent_stop.sh" }] }
    ]
  }
}
SNIPPET
)

if [[ -f "$SETTINGS_FILE" ]]; then
  MERGED=$(jq -s '.[0] * .[1]' "$SETTINGS_FILE" <(echo "$HOOKS_SNIPPET") 2>/dev/null || echo "")
  if [[ -n "$MERGED" ]]; then
    echo "$MERGED" > "$SETTINGS_FILE"
    echo "  [MERGE]   $SETTINGS_FILE に hooks エントリを追記"
  else
    echo "WARN: settings.json のマージに失敗しました。手動で hooks を追加してください。" >&2
  fi
else
  mkdir -p "$(dirname "$SETTINGS_FILE")"
  echo "$HOOKS_SNIPPET" > "$SETTINGS_FILE"
  echo "  [CREATE]  $SETTINGS_FILE"
fi
echo ""

echo "=== セットアップ完了 ==="
echo ""
echo "次のステップ:"
echo "  1. $QUEUE_FILE にタスクを追加"
echo "  2. Claude Code でこのリポジトリを開いてスプリントを開始"
echo "  3. pm エージェントを呼んで計画を立てる"
