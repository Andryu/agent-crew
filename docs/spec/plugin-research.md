# Claude Code Plugin 仕様リサーチ

Sprint-20 `plugin-research` タスク成果物。  
調査日: 2026-06-14 / 担当: Alex (architect agent) + claude-code-guide

---

## 1. プラグインディレクトリ構造

`claude plugin init <name>` で生成される標準レイアウト：

```
plugin-root/
├── .claude-plugin/
│   └── plugin.json          # マニフェスト（必須）
├── skills/                  # スキル定義
│   └── <skill-name>/
│       └── SKILL.md
├── agents/                  # エージェント定義
│   └── <agent-name>.md
├── hooks/                   # フック設定・スクリプト
│   └── hooks.json
├── commands/                # レガシー（フラットMD形式）
└── README.md
```

**重要**: `skills/`, `agents/`, `hooks/` の各パスは `plugin.json` で上書き可能。  
例: `"skills": "./.claude/skills/"` と指定することで、既存の `.claude/skills/` を移動せずに使える。

---

## 2. plugin.json スキーマ

必須フィールドは `name` のみ。

```json
{
  "name": "agent-crew",
  "displayName": "Agent Crew",
  "version": "1.0.0",
  "description": "PM・Architect・QA など専門エージェントと Skill を提供するプラグイン",
  "author": {
    "name": "Andryu",
    "url": "https://github.com/Andryu/agent-crew"
  },
  "repository": "https://github.com/Andryu/agent-crew",
  "license": "MIT",
  "agents": "./.claude/agents/",
  "skills": "./.claude/skills/",
  "defaultEnabled": true
}
```

### Hooks の書き方（hooks.json）

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pre_tool.sh" }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop.sh" }]
      }
    ]
  }
}
```

### Plugin-shipped agents の制約

プラグイン内の `agents/*.md` は以下のフィールドを **サポートしない**：
- `hooks` — エージェント固有のフック定義
- `mcpServers` — エージェント固有の MCP 設定
- `permissionMode` — 実行権限モード

→ **impact**: agent-crew のエージェントは現在これらを使っていないため影響なし。

---

## 3. marketplace.json スキーマ

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "agent-crew-marketplace",
  "description": "Andryu の Claude Code プラグインマーケットプレイス",
  "plugins": [
    {
      "name": "agent-crew",
      "displayName": "Agent Crew",
      "description": "PM・Architect・QA など専門エージェントと個人開発スキルを提供",
      "category": "productivity",
      "tags": ["agent", "pm", "personal-dev"],
      "source": {
        "source": "url",
        "url": "https://github.com/Andryu/agent-crew.git",
        "sha": ""
      }
    }
  ]
}
```

ユーザーのインストール手順：

```bash
claude plugin marketplace add Andryu/agent-crew
claude plugin install agent-crew
```

---

## 4. `~/.claude/` 書き込み制約

**結論: 書き込み可能。`pm-learned-rules.md` 問題は低リスク。**

| 書き込み先 | 可否 | 条件 |
|-----------|------|------|
| `~/.claude/agents/pm-learned-rules.md` | ✓ 可 | Bash ツール権限が必要 |
| `~/.claude/_lessons.json` | ✓ 可 | 同上 |
| `.claude/_queue.json` (プロジェクト) | ✓ 可 | Write ツール権限が必要 |

plugin コンテキストでも Bash/Write ツールが `permissions.allow` に登録されていれば、プラグインのエージェントは `~/.claude/` へ自由に書き込める。  
既存の `.claude/settings.json` の `permissions.allow` が引き続き有効。

---

## 5. スキルとエージェントのネームスペース

プラグインとしてインストールされた場合、スキルは **ネームスペース付き** で呼び出す：

```
現在:  /life-planner
変更後: /agent-crew:life-planner
```

| 配置方法 | 呼び出し形式 |
|---------|-------------|
| plugin の `skills/<name>/SKILL.md` | `/plugin-name:skill-name` |
| `~/.claude/skills/<name>/SKILL.md` (スタンドアロン) | `/<name>` (ネームスペースなし) |
| `.claude/skills/<name>/SKILL.md` (プロジェクトローカル) | `/<name>` (ネームスペースなし) |

**重要**: agent-crew を plugin インストールした場合、`/life-planner` は `/agent-crew:life-planner` になる。  
現在の install.sh でシンボリックリンク配置した `~/.claude/skills/` は**そのまま `/<name>` で呼べる**（ネームスペースなし）。

---

## 設計上の重要な発見

### ディレクトリ移行が不要な可能性

`plugin.json` の `agents` / `skills` フィールドにカスタムパスを指定できるため、  
**`.claude/agents/` と `.claude/skills/` を移動せずにプラグイン化できる**。

```json
{
  "name": "agent-crew",
  "agents": "./.claude/agents/",
  "skills": "./.claude/skills/"
}
```

これにより Sprint-20 の実装を大幅に簡略化できる。

### フックの扱い（設計決定が必要）

agent-crew のフック（PreToolUse, SubagentStop, TaskCompleted）は **スプリント管理専用** のため、  
プラグイン配布物に含めるべきではない：

- alpha-predict-jp 等でプラグインを使用する場合、`_queue.json` が存在しないためフックが失敗する
- フックは agent-crew 自身のプロジェクト開発に特化した機能

**推奨**: フックは `.claude/settings.json` に残し、プラグイン配布物には含めない。

### Hooks との非互換性

現在の `.claude/settings.json` の hooks コマンドパス：

```json
".claude/hooks/task_completed.sh"
```

この形式は agent-crew プロジェクト内でのみ有効。プラグインの `hooks.json` では `${CLAUDE_PLUGIN_ROOT}` を使う必要があるが、agent-crew のフックをプラグインに含める場合は Sprint-21 以降で対応。

---

## Sprint-20 実装方針（推奨）

**Option B（ミニマル移行）を採用する**：

| タスク | 元計画 | 推奨変更 |
|--------|--------|---------|
| `plugin-manifest` | `.claude-plugin/plugin.json` + `marketplace.json` 作成 | **実行** |
| `dir-migrate-agents` | `.claude/agents/` → `agents/` 移動 | **スキップ**（plugin.json でパス指定） |
| `dir-migrate-skills` | `.claude/skills/` → `skills/` 移動 | **スキップ**（plugin.json でパス指定） |
| `dir-migrate-hooks` | `.claude/hooks/` → `hooks/` 移動 | **スキップ**（フックはプラグイン外） |
| `install-sh-refactor` | グローバル配置ロジック削除 | **条件付き実行**（プラグイン install コマンドに言及するコメント追加のみ） |
| `sprint20-qa` | 全移行の検証 | **スコープ縮小**（plugin.json 単体の検証） |

**合計削減**: 11pt → 5pt 相当（スキップにより）

---

## 未解決事項

1. **E2E テスト方法**: `claude plugin install github:Andryu/agent-crew` でのローカルテストが必要。実際の `claude plugin` コマンドが環境に存在するか未確認。
2. **ネームスペース通知**: 既存ユーザーへの `/life-planner` → `/agent-crew:life-planner` 変更の周知方法。
3. **agent-crew 開発中の plugin ロード**: `feat/sprint-20` ブランチで開発中に `--plugin-dir ./` でローカルテストが可能か確認が必要。
