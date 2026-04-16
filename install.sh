#!/bin/bash
# claude-crew install script
# 使い方: bash install.sh [go|vue|next]
# 例:     bash install.sh go

set -e

STACK=${1:-go}
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 claude-crew インストール開始 (stack: $STACK)"

# グローバルに4人を配置（Yuki / Alex / Mina / Sora）
echo "📦 グローバルエージェントを配置中..."
mkdir -p ~/.claude/agents
cp "$REPO_DIR/agents/pm.md"  ~/.claude/agents/pm.md
cp "$REPO_DIR/agents/architect.md"  ~/.claude/agents/architect.md
cp "$REPO_DIR/agents/ux-designer.md"  ~/.claude/agents/ux-designer.md
cp "$REPO_DIR/agents/qa.md"  ~/.claude/agents/qa.md
cp "$REPO_DIR/agents/doc-reviewer.md"  ~/.claude/agents/doc-reviewer.md
echo "  → Yuki / Alex / Mina / Sora / Hana → ~/.claude/agents/"

# Rikuをプロジェクトに配置（スタック別）
echo "📦 Riku ($STACK) をプロジェクトに配置中..."
mkdir -p .claude/agents
RIKU_SRC="$REPO_DIR/agents/riku-$STACK.md"
if [ ! -f "$RIKU_SRC" ]; then
  echo "⚠️  riku-$STACK.md が見つかりません。engineer-go.md をベースに配置します。"
  RIKU_SRC="$REPO_DIR/agents/engineer-go.md"
fi
cp "$RIKU_SRC" .claude/agents/riku.md
echo "  → Riku → .claude/agents/riku.md"

# hooks を配置
echo "📦 hooks を配置中..."
mkdir -p .claude/hooks
cp "$REPO_DIR/hooks/subagent_stop.sh" .claude/hooks/subagent_stop.sh
chmod +x .claude/hooks/subagent_stop.sh
echo "  → subagent_stop.sh → .claude/hooks/"

# テンプレートを配置（既存ファイルは上書きしない）
echo "📦 設定ファイルを配置中..."
[ -f ".claude/_queue.json" ] || cp "$REPO_DIR/templates/_queue.json" .claude/_queue.json
[ -f ".claude/settings.json" ] || cp "$REPO_DIR/templates/settings.json" .claude/settings.json
echo "  → _queue.json / settings.json → .claude/"

echo ""
echo "✅ インストール完了！"
echo ""
echo "次のステップ:"
echo "  1. Slack通知を使う場合: export SLACK_WEBHOOK_URL='https://hooks.slack.com/...'"
echo "  2. Claude Code を起動して試す:"
echo "     > Use the yuki agent to plan [作りたい機能名]"
