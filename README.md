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

### Claude Code

```
Use the yuki agent to plan [作りたい機能名]
Use the alex agent on "[slug]"
Use the mina agent on "[slug]"
Use the riku agent on "[slug]"
Use the sora agent on "[slug]"
```

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

## Slack 通知（Claude Code のみ）

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

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
