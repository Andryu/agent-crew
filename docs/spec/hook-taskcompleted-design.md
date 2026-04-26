# TaskCompleted Hook 設計書

**Issue**: #61 — TaskCompleted/PreToolUse hookの活用  
**Sprint**: sprint-17  
**作成**: Alex / 2026-04-26  

---

## 1. 背景と目的

現在の hook 構成は `SubagentStop` 1本に依存しており、以下の責務が混在している。

| 現状の責務（subagent_stop.sh） | 問題 |
|---|---|
| BLOCKED タスクのアラート | タスク完了とは無関係に毎回実行される |
| 次の READY_FOR_* タスクの提示 | タスク完了後処理と次ステップ提示が分離されていない |
| スプリント完了宣言 | 実際にタスクが完了したかどうかに関わらず実行される |
| Slack 通知 | 上記すべての後処理を1ファイルで担当 |

`TaskCompleted` hook を導入することで、**タスク完了時の自動後処理**（_signals.jsonl への emit など）を `SubagentStop` から分離し、各 hook の責務を明確化する。

---

## 2. hook 責務の再定義

### 2.1 TaskCompleted hook（新規）

**責務**: エージェントがタスクを完了したときの即時後処理

| 処理 | 内容 |
|---|---|
| シグナル emit | `_signals.jsonl` に `task_completed` シグナルを記録 |
| queue 状態サマリー | 完了タスク slug・担当・タイムスタンプを STDOUT 出力（デバッグ用） |

**発火タイミング**: Claude がツール呼び出しを含むタスクを完了したとき（Claude Code の TaskCompleted フック）

**入力**: Claude Code が環境変数で渡すタスク情報（`CLAUDE_TOOL_USE_ID` など）

> 注: TaskCompleted hook では `_queue.json` の直接更新は行わない。queue 更新は引き続き `scripts/queue.sh done` を各エージェントが明示的に呼ぶ設計を維持する。

### 2.2 SubagentStop hook（変更後）

**責務**: サブエージェント停止時のオーケストレーション（次ステップ提示・完了宣言・Slack通知）

現状と変わらない責務を維持するが、シグナル emit 処理を TaskCompleted に移管することで**軽量化**する。

現状からの変更点:
- シグナル emit 処理があれば TaskCompleted に移管
- それ以外のロジック（BLOCKED検出・READY_FOR_*提示・スプリント完了判定）は変更なし

> Sprint-17 時点では `subagent_stop.sh` にシグナル emit 処理は存在しないため、実質的な変更はなし。

---

## 3. TaskCompleted hook 実装仕様

### 3.1 ファイルパス

```
.claude/hooks/task_completed.sh
```

### 3.2 settings.json への登録

```json
{
  "hooks": {
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/task_completed.sh"
          }
        ]
      }
    ]
  }
}
```

既存の `PreToolUse`・`SubagentStop`・`Stop` エントリはそのまま維持する。

### 3.3 スクリプト仕様

#### 入力（Claude Code が設定する環境変数）

| 変数名 | 内容 | 例 |
|---|---|---|
| `CLAUDE_TOOL_USE_ID` | ツール呼び出し ID | `toolu_01...` |

> TaskCompleted hook に渡される環境変数の詳細は Claude Code の仕様に依存する。
> 取得できない場合は `unknown` にフォールバックする。

#### 処理フロー

```
1. jq コマンドの存在確認 → なければ警告して exit 0
2. QUEUE_FILE (.claude/_queue.json) の存在確認 → なければ exit 0
3. 現在の IN_PROGRESS タスクを _queue.json から取得
4. _signals.jsonl に task_completed シグナルを emit
5. STDOUT に完了サマリーを出力（デバッグ用）
```

#### emit するシグナルの形式

```jsonl
{"ts":"2026-04-26T22:00:00+0000","sprint":"sprint-17","slug":"hook-impl","agent":"Riku","event":"task_completed","tool_use_id":"unknown"}
```

#### スクリプト本体

```bash
#!/bin/bash
# .claude/hooks/task_completed.sh
# TaskCompleted フック: タスク完了時に _signals.jsonl へシグナルを emit する

set -euo pipefail

QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"
SIGNALS_FILE="${SIGNALS_FILE:-.claude/_signals.jsonl}"

# 依存チェック
if ! command -v jq >/dev/null 2>&1; then
  echo "WARN: jq not found, task_completed hook is degraded" >&2
  exit 0
fi

if [[ ! -f "$QUEUE_FILE" ]]; then
  exit 0
fi

# IN_PROGRESS タスクを取得（複数ある場合は最初の1件）
SLUG=$(jq -r '
  .tasks
  | map(select(.status == "IN_PROGRESS"))
  | first
  | .slug // empty
' "$QUEUE_FILE" 2>/dev/null || true)

AGENT=$(jq -r '
  .tasks
  | map(select(.status == "IN_PROGRESS"))
  | first
  | .assigned_to // "unknown"
' "$QUEUE_FILE" 2>/dev/null || true)

SPRINT=$(jq -r '.sprint // "unknown"' "$QUEUE_FILE" 2>/dev/null || true)

# IN_PROGRESS タスクがなければ何もしない
if [[ -z "$SLUG" ]]; then
  exit 0
fi

TS=$(date -u +"%Y-%m-%dT%H:%M:%S+0000")
TOOL_USE_ID="${CLAUDE_TOOL_USE_ID:-unknown}"

# シグナル emit
SIGNAL=$(jq -cn \
  --arg ts "$TS" \
  --arg sprint "$SPRINT" \
  --arg slug "$SLUG" \
  --arg agent "$AGENT" \
  --arg event "task_completed" \
  --arg tool_use_id "$TOOL_USE_ID" \
  '{ts: $ts, sprint: $sprint, slug: $slug, agent: $agent, event: $event, tool_use_id: $tool_use_id}')

echo "$SIGNAL" >> "$SIGNALS_FILE"

echo "TASK_COMPLETED: $SLUG ($AGENT) @ $TS" >&2

exit 0
```

### 3.4 構文バリデーション

実装後に以下で構文確認を行うこと（Alex ルール準拠）:

```bash
bash -n .claude/hooks/task_completed.sh
```

---

## 4. settings.json 変更差分

### 変更前（抜粋）

```json
"hooks": {
  "PreToolUse": [...],
  "SubagentStop": [...],
  "Stop": [...]
}
```

### 変更後（抜粋）

```json
"hooks": {
  "TaskCompleted": [
    {
      "hooks": [
        {
          "type": "command",
          "command": ".claude/hooks/task_completed.sh"
        }
      ]
    }
  ],
  "PreToolUse": [...],
  "SubagentStop": [...],
  "Stop": [...]
}
```

---

## 5. SubagentStop との責務分離まとめ

| hook | 発火条件 | 主な責務 |
|---|---|---|
| `TaskCompleted` | Claude がタスクを完了したとき | シグナル emit（観測） |
| `SubagentStop` | サブエージェントが停止したとき | 次ステップ提示・完了宣言・Slack通知（オーケストレーション） |
| `Stop` | セッション停止時 | subagent_stop と同処理 + propose-lesson-rules --dry-run |
| `PreToolUse` | ツール呼び出し前 | セッション開始表示（session_start.sh） |

---

## 6. ロールバック手順

1. `settings.json` から `TaskCompleted` エントリを削除する
2. `.claude/hooks/task_completed.sh` を削除する
3. 既存の `subagent_stop.sh` と `session_start.sh` はそのまま維持される

---

## 7. 完了条件

- [ ] `.claude/hooks/task_completed.sh` が作成されている
- [ ] `bash -n .claude/hooks/task_completed.sh` でエラーなし
- [ ] `settings.json` に `TaskCompleted` hook が登録されている
- [ ] `jq . .claude/settings.json` で valid JSON
- [ ] `subagent_stop.sh` に変更なし（Sprint-17 スコープ外）
