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

# queue.sh を配置し、QUEUE_FILE のデフォルトを .agent/_queue.json に書き換え
echo "📦 スクリプトを配置中..."
mkdir -p .agent/scripts
cp "$REPO_DIR/scripts/queue.sh" .agent/scripts/queue.sh
chmod +x .agent/scripts/queue.sh
sed 's|QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"|QUEUE_FILE="${QUEUE_FILE:-.agent/_queue.json}"|' \
  .agent/scripts/queue.sh > .agent/scripts/queue.sh.tmp
sed 's|QUEUE_LOCK="${QUEUE_LOCK:-.claude/.queue.lock}"|QUEUE_LOCK="${QUEUE_LOCK:-.agent/.queue.lock}"|' \
  .agent/scripts/queue.sh.tmp > .agent/scripts/queue.sh
rm -f .agent/scripts/queue.sh.tmp
echo "  → queue.sh → .agent/scripts/queue.sh"

# notify_slack.sh が存在する場合はコピー
if [ -f "$REPO_DIR/scripts/notify_slack.sh" ]; then
  cp "$REPO_DIR/scripts/notify_slack.sh" .agent/scripts/notify_slack.sh
  chmod +x .agent/scripts/notify_slack.sh
  echo "  → notify_slack.sh → .agent/scripts/notify_slack.sh"
fi

echo ""
echo "インストール完了！"
echo ""
echo "注意:"
echo "  SubagentStop hookはAntigravityでは未サポートのため、"
echo "  パイプラインの自動提示は動作しません。"
echo "  各エージェントは完了時に「--- NEXT STEP ---」ブロックで次のコマンドを提示します。"
echo "  オーナーがそのコマンドをコピーして次エージェントを呼び出してください。"
echo ""
echo "キュー操作:"
echo "  .agent/scripts/queue.sh start <slug>"
echo "  .agent/scripts/queue.sh done <slug> <agent> \"<summary>\""
echo "  .agent/scripts/queue.sh show"
echo ""
echo "使い方:"
echo "  @yuki [作りたい機能名] を計画して"
echo "  @alex [slug] の設計をして"
echo "  @mina [slug] のUX仕様を作って"
echo "  @riku [slug] を実装して"
echo "  @sora [slug] をレビューして"
