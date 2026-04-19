# agent-crew

個人開発を加速するAIチーム設定リポジトリ。Claude Code・Google Antigravity の両方に対応。

## チーム構成

| エージェント | 役割 | スコープ |
|------------|------|---------|
| **Yuki** | PM・オーケストレーター・Slack通知 | グローバル |
| **Alex** | アーキテクト（設計・ADR） | グローバル |
| **Mina** | UXデザイナー（フロー・仕様書） | グローバル |
| **Riku** | 実装エンジニア（スタック依存） | プロジェクト単位 |
| **Sora** | QA・コードレビュー | グローバル |
| **Hana** | ドキュメントレビュー（PRD/仕様書） | グローバル |

---

## インストール

### Claude Code

```bash
bash install.sh go        # Go スタック
bash install.sh vue       # Vue3（riku-vue.md を追加したら）
bash install.sh next      # Next.js（riku-next.md を追加したら）
```

| エージェント | 配置先 |
|------------|--------|
| Yuki / Alex / Mina / Sora | `~/.claude/agents/`（グローバル） |
| Riku | `.claude/agents/`（プロジェクト） |
| hooks / queue / settings | `.claude/`（プロジェクト） |

### Google Antigravity

```bash
bash install-antigravity.sh go
```

| エージェント | 配置先 |
|------------|--------|
| Yuki / Alex / Mina / Sora | `~/.gemini/antigravity/skills/`（グローバル） |
| Riku | `.agent/skills/`（プロジェクト） |

> **注意:** Antigravity は SubagentStop hook 未対応のため、パイプラインの自動提示は動作しません。各エージェントを手動で順番に呼び出してください。

---

## 使い方

### 起動の仕方

agent-crew のエージェントは **Claude Code 本体から起動します**。Claude Code 内のサブエージェントから他のサブエージェントを直接 spawn することはできないため、人間（またはトップレベルの Claude Code セッション）が次エージェントを呼び出す構造です。

### Claude Code

```
Use the yuki agent to plan [作りたい機能名]
Use the alex agent on "[slug]"
Use the mina agent on "[slug]"
Use the riku agent on "[slug]"
Use the sora agent on "[slug]"
```

### 運用モード

agent-crew は2つの運用モードをサポートします。

#### 1. confirm モード（デフォルト、安全）

各エージェント完了時に `SubagentStop` hook が次の担当を**提示**し、ユーザーが確認してから次のコマンドを実行します。

```
[Alex 完了]
  ↓
🔔 YUKI: 次のステップの提案
  実行するには以下をコピーしてください:
    Use the mina agent on "bookmark-api"
  ↓
[ユーザーがコピペして承認]
  ↓
[Mina 実行]
```

#### 2. auto モード（介入最小化、推奨）

トップレベルの Claude Code セッションで「パイプラインを進めて」と指示すれば、Claude が `.claude/_queue.json` を読んで次の READY 状態のタスクを自動的に担当エージェントへ委譲します。

```
ユーザー: 「bookmark-api のパイプラインを進めて」
  ↓
[Claude が queue を読む]
  ↓
[Alex→Mina→Riku→Sora と自動で順次 spawn]
  ↓
[BLOCKED かゴー/ノーゴー チェックポイントで停止]
```

**auto モードで停止する条件:**
- タスクが `BLOCKED` に遷移した
- Yuki が明示的に「checkpoint」フラグを立てたタスク（重要な設計判断など）
- リトライ回数が上限（3回）に達した

auto モードを使うには、ユーザーが明示的に「continue the pipeline」「パイプラインを進めて」のように指示します。裏でのフロー全体を見たい場合は confirm モードのままがよいでしょう。

### Antigravity

```
@yuki [作りたい機能名] を計画して
@alex [slug] の設計をして
@mina [slug] のUX仕様を作って
@riku [slug] を実装して
@sora [slug] をレビューして
```

---

## ディレクトリ構成

```
agent-crew/
├── agents/
│   ├── pm.md              # PM・オーケストレーター
│   ├── architect.md              # アーキテクト
│   ├── ux-designer.md              # UXデザイナー
│   ├── engineer-go.md           # 実装（Go）
│   └── qa.md              # QA・コードレビュー
├── hooks/
│   └── subagent_stop.sh     # 自動パイプライン hook（Claude Code用）
├── templates/
│   ├── _queue.json          # タスクキューテンプレート
│   └── settings.json        # Claude Code 設定テンプレート
├── install.sh               # Claude Code 用インストーラー
├── install-antigravity.sh   # Antigravity 用インストーラー
└── README.md
```

---

## Riku のスタック追加

```bash
cp agents/engineer-go.md agents/riku-next.md
# riku-next.md を Next.js 向けに編集する
```

---

## タスクキュー操作（scripts/queue.sh）

`.claude/_queue.json` は必ず `scripts/queue.sh` 経由で更新します。直接編集はアトミック更新・ロック・events履歴が失われるため禁止です。

```bash
scripts/queue.sh start <slug>                                    # IN_PROGRESS へ
scripts/queue.sh done <slug> <agent> "<summary>"                 # DONE へ
scripts/queue.sh handoff <next-slug> <next-agent>                # READY_FOR_<AGENT>
scripts/queue.sh qa <slug> APPROVED|CHANGES_REQUESTED "<msg>"    # QA判定記録
scripts/queue.sh retry <slug>                                    # retry_count++ → RIKU
scripts/queue.sh block <slug> <agent> "<reason>"                 # BLOCKED
scripts/queue.sh show [<slug>]                                   # 状態表示
scripts/queue.sh next                                            # 次に実行可能なREADY 1件
```

### スキーマ拡張

- `events[]`: 全状態遷移の履歴（ts / agent / action / msg）
- `retry_count`: CHANGES_REQUESTED 毎に +1、`MAX_RETRY`（=3）超過で自動 BLOCKED
- `qa_result`: `APPROVED` / `CHANGES_REQUESTED` / `null`

### Quality Gate（スプリント完了判定）

1. 全タスク `status == "DONE"` かつ
2. QA対象の全タスクで `qa_result == "APPROVED"`

両方を満たしたとき `subagent_stop.sh` が完了を通知します。

---

## Slack 通知（Claude Code のみ）

`subagent_stop.sh` が各エージェント完了・BLOCKED・スプリント完了のタイミングで Slack に通知します。

### セットアップ

#### ローカル開発

```bash
# 1. .env.example をコピーして .env を作成
cp .env.example .env

# 2. .env を編集して実際の Webhook URL を入力
#    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Webhook URL は [Slack API](https://api.slack.com/apps) → Incoming Webhooks → Add New Webhook から取得してください。

`.env` は `.gitignore` で除外されているため、リポジトリにコミットされません。

#### GitHub Actions

リポジトリの Settings → Secrets and variables → Actions → New repository secret に以下を追加してください:

| Secret 名 | 値 |
|-----------|-----|
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |

Secret を設定後、`.github/workflows/slack-notify.yml` が Issue/PR イベントを Slack に通知します。

---

## ツール対応状況

| 機能 | Claude Code | Antigravity |
|------|:-----------:|:-----------:|
| エージェント本体 | ✅ | ✅ |
| グローバル配置 | ✅ | ✅ |
| プロジェクト配置 | ✅ | ✅ |
| 自動パイプライン（hook） | ✅ | ❌ 未対応 |
| Slack 通知 | ✅ | ❌ 未対応 |
| タスクキュー管理 | ✅ | 手動 |
