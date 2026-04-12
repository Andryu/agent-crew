#!/bin/bash
# agent-crew install script for Google Antigravity
# 使い方: bash install-antigravity.sh [go|vue|next]
# 例:     bash install-antigravity.sh go

set -e

STACK=${1:-go}
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 agent-crew インストール開始 (Antigravity / stack: $STACK)"

# グローバルに4人を配置（Yuki / Alex / Mina / Sora）
echo "📦 グローバルSkillsを配置中..."
for agent in pm architect ux-designer qa; do
  mkdir -p ~/.gemini/antigravity/skills/$agent
  cp "$REPO_DIR/agents/$agent.md" ~/.gemini/antigravity/skills/$agent/SKILL.md
done
echo "  → Yuki / Alex / Mina / Sora → ~/.gemini/antigravity/skills/"

# Rikuをプロジェクトに配置（スタック別）
echo "📦 Riku ($STACK) をプロジェクトに配置中..."
RIKU_SRC="$REPO_DIR/agents/riku-$STACK.md"
if [ ! -f "$RIKU_SRC" ]; then
  echo "⚠️  riku-$STACK.md が見つかりません。engineer-go.md をベースに配置します。"
  RIKU_SRC="$REPO_DIR/agents/engineer-go.md"
fi
mkdir -p .agent/skills/riku
cp "$RIKU_SRC" .agent/skills/riku/SKILL.md
echo "  → Riku → .agent/skills/riku/SKILL.md"

# _queue.json だけ配置（hookはAntigravityでは未サポート）
echo "📦 タスクキューを配置中..."
mkdir -p .agent
[ -f ".agent/_queue.json" ] || cp "$REPO_DIR/templates/_queue.json" .agent/_queue.json
echo "  → _queue.json → .agent/"

echo ""
echo "✅ インストール完了！"
echo ""
echo "注意:"
echo "  SubagentStop hookはAntigravityでは未サポートのため、"
echo "  パイプラインの自動提示は動作しません。"
echo "  手動で各エージェントを順番に呼び出してください。"
echo ""
echo "使い方:"
echo "  @yuki [作りたい機能名] を計画して"
echo "  @alex [slug] の設計をして"
echo "  @mina [slug] のUX仕様を作って"
echo "  @riku [slug] を実装して"
echo "  @sora [slug] をレビューして"
