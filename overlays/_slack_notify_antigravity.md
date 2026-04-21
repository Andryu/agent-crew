
---

## Slack 通知（Antigravity）

Antigravity では SubagentStop hook が存在しないため、Slack 通知はエージェントが Bash ツールを使って直接 curl を呼ぶか、STDOUT への通知内容提示で代替します。

### 前提条件

`SLACK_WEBHOOK_URL` 環境変数が設定されている場合のみ通知を送信します。未設定の場合は通知をスキップし、エラーを出しません。

### Bash ツールが使える場合（curl で直接通知）

以下のスニペットを完了報告と合わせて実行してください。

```bash
# Slack通知（SLACK_WEBHOOK_URL未設定の場合はスキップ）
if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
  curl -s -X POST "$SLACK_WEBHOOK_URL" \
    -H 'Content-Type: application/json' \
    -d "{\"text\": \"[agent-crew] <エージェント名> が <slug> を完了しました\"}" \
    > /dev/null
fi
```

### 通知タイミング

以下の3タイミングで通知を送ることを推奨します。

| タイミング | メッセージ例 |
|-----------|------------|
| タスク完了 | `[agent-crew] Riku が user-auth を完了しました` |
| BLOCKED 発生 | `[agent-crew] BLOCKED: user-auth — <理由>` |
| スプリント完了 | `[agent-crew] スプリント sprint-01 が完了しました` |

### Bash ツールが使えない場合（STDOUT 提示）

Bash ツールが許可されていない場合、完了報告に以下を含めてオーナーへ手動通知を促します。

```
--- SLACK 通知 ---
以下のメッセージを Slack へ投稿してください:
「[agent-crew] <エージェント名> が <slug> を完了しました」
---
```

### Webhook URL のセットアップ

1. [Slack API](https://api.slack.com/apps) → Incoming Webhooks → Add New Webhook から URL を取得
2. プロジェクトの `.env` ファイルに記載:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

3. エージェント起動前に `source .env` を実行するか、環境変数として渡す
