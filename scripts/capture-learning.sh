#!/bin/bash
# scripts/capture-learning.sh
# グローバル SubagentStop フック: 全リポジトリの学習イベントを ~/.claude/learning-logs.jsonl に記録
#
# ~/.claude/settings.json（グローバル）の hooks.SubagentStop に登録して使用
# install.sh --global-hooks で自動セットアップ可能

set -uo pipefail

LEARNING_LOG="${HOME}/.claude/learning-logs.jsonl"

# SubagentStop ペイロードを stdin から受け取る
PAYLOAD=$(cat 2>/dev/null || echo "{}")
CWD=$(echo "$PAYLOAD" | jq -r '.cwd // empty' 2>/dev/null || echo "")

# cwd が取得できない場合はスキップ
[ -z "$CWD" ] && exit 0
[ ! -d "$CWD" ] && exit 0

# リポジトリ情報を取得
REPO_URL=$(git -C "$CWD" remote get-url origin 2>/dev/null || echo "local")
REPO_NAME=$(basename "$REPO_URL" .git 2>/dev/null || basename "$CWD")
AGENT_TYPE=$(echo "$PAYLOAD" | jq -r '.agent_type // "unknown"' 2>/dev/null || echo "unknown")
SESSION_ID=$(echo "$PAYLOAD" | jq -r '.session_id // ""' 2>/dev/null || echo "")

# learning-logs.jsonl に追記（JSONL 形式）
ENTRY=$(jq -n \
  --arg ts "$(date -u +%FT%TZ)" \
  --arg repo "$REPO_NAME" \
  --arg repo_url "$REPO_URL" \
  --arg agent_type "$AGENT_TYPE" \
  --arg cwd "$CWD" \
  --arg session_id "$SESSION_ID" \
  '{ts: $ts, repo: $repo, repo_url: $repo_url, agent_type: $agent_type, cwd: $cwd, session_id: $session_id}' \
  2>/dev/null || echo "")

[ -z "$ENTRY" ] && exit 0

echo "$ENTRY" >> "$LEARNING_LOG" 2>/dev/null || true

exit 0
