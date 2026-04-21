# install.sh 汎用化 設計メモ

GitHub Issue #32 / branch: `feat/portable-install`

## 概要

`install.sh` を汎用化し、agent-crew リポジトリ外の任意のプロジェクトへの導入を可能にする。

## 引数・オプション設計

```
bash install.sh [OPTIONS] [STACK] [TARGET_DIR]
```

### 位置引数

| 引数 | デフォルト | 説明 |
|------|-----------|------|
| `STACK` | `go` | スタック識別子（`go` / `vue` / `next`）。Riku の variant を決定 |
| `TARGET_DIR` | `.` | インストール先プロジェクトのパス |

### オプション

| オプション | 説明 |
|-----------|------|
| `--dry-run` | 変更内容をプレビュー表示。実際のファイル操作は行わない |
| `--only=<component>` | 選択的インストール（カンマ区切り） |
| `--no-global` | グローバルエージェントのインストールをスキップ |
| `--force` | 競合検出プロンプトをスキップして全て上書き |
| `--uninstall` | インストール済みファイルを削除 |
| `--help` | 使い方を表示 |

### `--only` のコンポーネント

| 値 | 対象 |
|----|------|
| `agents` | グローバルエージェント + Riku |
| `global-agents` | グローバルエージェントのみ |
| `riku` | Riku のみ |
| `hooks` | `subagent_stop.sh` |
| `config` | `_queue.json` + `settings.json` |

## コピー対象ファイルと配置先

### グローバル（`~/.claude/agents/`）

| ソース | 配置先 | 上書きポリシー |
|--------|--------|---------------|
| `agents/pm.md` | `~/.claude/agents/pm.md` | 競合検出 |
| `agents/architect.md` | `~/.claude/agents/architect.md` | 競合検出 |
| `agents/ux-designer.md` | `~/.claude/agents/ux-designer.md` | 競合検出 |
| `agents/qa.md` | `~/.claude/agents/qa.md` | 競合検出 |
| `agents/doc-reviewer.md` | `~/.claude/agents/doc-reviewer.md` | 競合検出 |

### プロジェクトローカル（`<TARGET_DIR>/.claude/`）

| ソース | 配置先 | 上書きポリシー |
|--------|--------|---------------|
| `agents/riku-<STACK>.md` | `.claude/agents/riku.md` | 競合検出 |
| `hooks/subagent_stop.sh` | `.claude/hooks/subagent_stop.sh` | 常に上書き |
| `templates/_queue.json` | `.claude/_queue.json` | 既存ならスキップ |
| `templates/settings.json` | `.claude/settings.json` | 既存ならスキップ |

## 競合検出フロー

```
for each ファイル in コピー対象:
  if 配置先が存在しない → コピー
  elif 上書きポリシー == "スキップ" → "[SKIP]" 表示
  elif 上書きポリシー == "常に上書き" → コピー
  else (競合検出):
    if --force → 上書き
    elif --dry-run → "[CONFLICT]" 表示
    else → diff 表示 + プロンプト [y/N/a/q]
```

### dry-run 出力例

```
[DRY-RUN] インストール対象:
  [NEW]       ~/.claude/agents/pm.md
  [CONFLICT]  ~/.claude/agents/qa.md  ← 既に存在
  [SKIP]      .claude/_queue.json  ← 既存ファイルを保護
  [OVERWRITE] .claude/hooks/subagent_stop.sh
```

## アンインストール設計

削除対象:
- `<TARGET_DIR>/.claude/agents/riku.md`
- `<TARGET_DIR>/.claude/hooks/subagent_stop.sh`

削除しないもの:
- `_queue.json`、`settings.json`（オーナーデータ保護）
- グローバルエージェント（複数プロジェクトで共有の可能性）

## エラーハンドリング

`set -euo pipefail` を採用。

| 終了コード | 意味 |
|-----------|------|
| 0 | 成功 |
| 1 | 引数・オプションエラー |
| 2 | ソースファイル不在 |
| 3 | 書き込み権限なし |
| 4 | オーナーが中断 |

## トレードオフ

| 決定 | 採用 | 却下 | 理由 |
|------|------|------|------|
| `--only` の粒度 | コンポーネント単位 | エージェント名単位 | 個別選択の需要は稀 |
| アンインストール時の `_queue.json` | 保護 | 削除 | スプリントデータ誤削除リスク |
| グローバルエージェントの削除 | 保護 | 自動削除 | 複数プロジェクト共有のため |
