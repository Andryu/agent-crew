#!/bin/bash
# scripts/aggregate-learnings.sh
# グローバル Stop フック: ~/.claude/learning-logs.jsonl を集計し外部リポジトリ活動を報告
#
# ~/.claude/settings.json（グローバル）の hooks.Stop に登録して使用
# install.sh --global-hooks で自動セットアップ可能

set -uo pipefail

LEARNING_LOG="${HOME}/.claude/learning-logs.jsonl"

# ログファイル不在の場合はスキップ
[ ! -f "$LEARNING_LOG" ] && exit 0

TODAY=$(date +%Y-%m-%d)

# 当日エントリのうち agent-crew 以外のリポジトリを集計
SUMMARY=$(jq -r --arg today "$TODAY" '
  select(.ts | startswith($today))
  | select(.repo != "agent-crew" and .repo != "" and .repo != null)
  | "\(.repo) (\(.agent_type))"
' "$LEARNING_LOG" 2>/dev/null | sort | uniq -c | sort -rn || true)

[ -z "$SUMMARY" ] && exit 0

echo "" >&2
echo "=== 本日の外部リポジトリ活動サマリー ===" >&2
echo "$SUMMARY" | while IFS= read -r line; do
  echo "  $line" >&2
done
echo "  ログ: $LEARNING_LOG" >&2

exit 0
