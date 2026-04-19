# ADR: Slack 連携設計

## Status
Accepted

## Context

agent-crew は Claude Code のサブエージェント6体（Yuki / Alex / Mina / Riku / Sora / Hana）で個人開発パイプラインを半自動化するシステムである。現状、作業の進捗はターミナルログだけで可視化されており、オーナーがデスクを離れていると変化に気づけない。

既存の `.claude/hooks/subagent_stop.sh` には Slack Webhook への curl 通知が実装済みだが、以下の問題がある:

1. **人格なし**: 通知文が "agent-crew" 固定で、誰が何をしたかがわからない
2. **BLOCKED 通知が粗い**: 複数の BLOCKED タスクをまとめて1メッセージしか送らず、slug や理由が入らない
3. **エージェント完了時のメッセージが主語不明**: 「フェーズが完了しました / 次: RIKU」という表現で、完了したのが誰かわからない
4. **GitHub イベント（Issue/PR）に未対応**: GitHub Actions ワークフローが存在しない
5. `.env.example` が未整備でオンボーディングが困難

## Decision

### 1. エージェント名の取得方法

`subagent_stop.sh` は `_queue.json` を直接参照しているため、完了直前のイベントから `agent` フィールドを読む方式を採用する。

```bash
# 直近の done イベントから agent 名を取得する例
LAST_AGENT=$(jq -r '
  .tasks
  | map(.events // [])
  | flatten
  | map(select(.action == "done"))
  | last
  | .agent // "Yuki"
' "$QUEUE_FILE")
```

代替案として hook の STDIN（SubagentStop の JSON ペイロード）から取得する方法もあるが、SubagentStop フックは agent 名を含まないため採用しない。

`_queue.json` のイベント履歴が唯一の信頼できるソースである。

### 2. subagent_stop.sh の改善方針

各通知にエージェント名と slug を含めることで「誰が何をしたか」を明確にする。

**BLOCKED 通知（1件ずつ送信）:**
```
🚧 <agent>: <slug> がブロックされました — <理由>
```

**フェーズ完了通知:**
```
✅ <agent>: <slug> が完了しました / 次: <next_agent>
```

**スプリント完了通知:**
```
🎉 Yuki: <sprint> 完了。全タスク DONE / QA APPROVED
```

**タスク分解完了通知（Yuki が queue.sh done 後に送信）:**
```
📋 Yuki: タスクを <n> 件作成しました
```

スプリント完了は Yuki 固定とする。他のフェーズ完了は直近 `done` イベントの `agent` フィールドから取得する。

BLOCKED は slug ごとにループして個別通知する（現在は1件まとめ）。1メッセージ/秒の Slack レート制限に対応するため、ループ内に `sleep 1` を入れる。

### 3. GitHub Actions ワークフローの構成

**1ファイル構成** (`slack-notify.yml`) を採用する。

理由: Issue と PR で通知ロジックは同じ curl 呼び出しであり、ファイルを分けると webhook URL の Secret 参照が重複するだけで管理コストが上がる。トリガー条件を `on:` ブロックで列挙することで可読性を保てる。

```yaml
on:
  issues:
    types: [opened, closed]
  pull_request:
    types: [opened, closed]
```

メッセージのフォーマット:
```
# Issue 登録
📝 Yuki: Issue #<number> を登録しました — <title>

# Issue クローズ
✅ Yuki: Issue #<number> をクローズしました — <title>

# PR 作成
🔀 Riku: PR #<number> を作成しました — <title>

# PR マージ
🎉 Riku: PR #<number> がマージされました — <title>
```

Issue の主語を Yuki、PR の主語を Riku とする。これは慣習的な役割分担（Yuki = PM、Riku = 実装担当）に基づく固定割り当てであり、GitHub アカウント名から動的判定はしない（過度に複雑になるため）。

### 4. シークレット管理

| 環境 | 管理方法 |
|------|----------|
| ローカル開発 | `SLACK_WEBHOOK_URL` 環境変数（シェルプロファイルまたは `.env`） |
| GitHub Actions | Repository Secret `SLACK_WEBHOOK_URL` |

`.env.example` をリポジトリルートに置き、実際の `.env` は `.gitignore` で除外する。

`.env.example` の内容:
```bash
# Slack Incoming Webhook URL
# 取得先: https://api.slack.com/apps → Incoming Webhooks → Add New Webhook
# このファイルをコピーして .env を作成し、実際の URL を入力してください
# cp .env.example .env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 5. 通知頻度の制御方針

以下のイベントは通知しない:

| 除外イベント | 理由 |
|-------------|------|
| `IN_PROGRESS` への遷移 | エージェントが着手するたびに発火し、ノイズになる |
| `TODO` 状態のタスク作成 | Yuki がまとめてキューを作る際、件数で1件通知すれば十分 |
| `retry` による `READY_FOR_RIKU` 遷移 | CHANGES_REQUESTED の通知と重複する |
| フック起動のたびのハートビート | hook は SubagentStop のたびに呼ばれるため、変化がない場合は通知不要 |

通知する条件:
- `BLOCKED` 遷移（即時アクション必要）
- `READY_FOR_*` かつ直前イベントが `done`（フェーズ完了）
- 全タスク `DONE` かつ QA `APPROVED`（スプリント完了）
- GitHub Issue 登録/クローズ
- GitHub PR 作成/マージ

### 6. チャンネル設計

全通知を1チャンネルに集約する（Slack 無料版のアプリ連携10枠制限の範囲内で1枠使用）。チャンネル名は `#agent-crew`（または既存チャンネルに Webhook を追加）。Webhook URL 自体がチャンネルに紐付いているため、コード側でのチャンネル指定は不要。

### 7. メッセージフォーマット

Block Kit は使用しない。理由: Slack 無料版での表示差異がなく、テキスト形式のほうが curl のペイロードが単純で保守しやすい。絵文字プレフィックスで通知種別を視覚的に区別する。

| 絵文字 | 意味 |
|--------|------|
| 📋 | タスク作成 |
| 🔔 | 次フェーズへの引き継ぎ（次担当への案内） |
| ✅ | フェーズ完了 / Issue クローズ |
| 🚧 | ブロック発生 |
| 🎉 | スプリント完了 / PR マージ |
| 📝 | Issue 登録 |
| 🔀 | PR 作成 |

## Consequences

### 良くなること

- 通知メッセージから「誰が何を完了したか」が1秒で把握できる
- GitHub の Issue/PR ライフサイクルが Slack に流れ、コンテキストスイッチが減る
- `.env.example` によりオンボーディング手順が明確になる
- BLOCKED 通知が slug/理由付きになるため、何に対処すべきかが即わかる

### 変わらないこと / 制約

- Webhook URL はコードに含まれないため、クローンしただけでは動作しない（意図した制約）
- 1チャンネル集約のため、将来チームが複数人になると通知が混在する（現状は個人開発のみなので問題なし）
- エージェント名の取得は `_queue.json` への依存であり、queue ファイルが壊れると通知の主語が "Yuki" フォールバックになる
- GitHub Actions の主語（Yuki/Riku）は固定割り当てのため、実際の PR 作成者が異なる場合でも Riku 表記になる（個人開発では常にオーナー1人なので問題なし）

### トレードオフ

| 選択 | 得たもの | 失ったもの |
|------|---------|-----------|
| エージェント名を queue.json から取得 | 既存ファイルを活用、追加の仕組み不要 | queue.json が存在しない状況では動作しない |
| Actions 1ファイル構成 | 管理箇所が1か所 | トリガーごとの細かい制御が少し見づらい |
| テキスト形式（Block Kit なし） | シンプルな curl ペイロード | リッチな表現（ボタン等）は使えない |
| BLOCKED のみ slug 個別通知 | 1メッセージで理由まで伝わる | 複数 BLOCKED 時に複数メッセージが届く（rate limit 対応で sleep 1 が必要） |
