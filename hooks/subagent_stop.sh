#!/bin/bash
# .claude/hooks/subagent_stop.sh
# SubagentStop フック：エージェント完了後に次のステップを提示 + Slack通知
#
# 設定方法（.claude/settings.json に追加）:
# {
#   "hooks": {
#     "SubagentStop": [
#       {
#         "hooks": [
#           {
#             "type": "command",
#             "command": ".claude/hooks/subagent_stop.sh"
#           }
#         ]
#       }
#     ]
#   }
# }

QUEUE_FILE=".claude/_queue.json"

# キューファイルがなければ何もしない
if [ ! -f "$QUEUE_FILE" ]; then
  exit 0
fi

# 次のアクションを読み取る
NEXT_STATUS=$(python3 -c "
import json, sys
try:
    with open('$QUEUE_FILE') as f:
        q = json.load(f)
    for task in q.get('tasks', []):
        s = task.get('status', '')
        slug = task.get('slug', '')
        title = task.get('title', '')
        if s.startswith('READY_FOR_'):
            agent = s.replace('READY_FOR_', '').lower()
            print(f'{slug}|{agent}|{title}')
            break
except Exception as e:
    pass
" 2>/dev/null)

if [ -z "$NEXT_STATUS" ]; then
  exit 0
fi

SLUG=$(echo "$NEXT_STATUS" | cut -d'|' -f1)
AGENT=$(echo "$NEXT_STATUS" | cut -d'|' -f2)
TITLE=$(echo "$NEXT_STATUS" | cut -d'|' -f3)

# 次ステップを提示（STDOUTに出力 → Claudeのトランスクリプトに表示される）
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

# Slack通知（SLACK_WEBHOOK_URL が設定されている場合のみ）
if [ -n "$SLACK_WEBHOOK_URL" ]; then
  AGENT_UPPER=$(echo "$AGENT" | tr '[:lower:]' '[:upper:]')
  MESSAGE="✅ *$TITLE* ($SLUG) のフェーズが完了しました\n次: $AGENT_UPPER が担当します"
  curl -s -X POST "$SLACK_WEBHOOK_URL" \
    -H 'Content-type: application/json' \
    -d "{\"text\": \"$MESSAGE\"}" \
    > /dev/null 2>&1
fi
