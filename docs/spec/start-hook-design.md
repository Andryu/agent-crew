# Start hook 設計（session_start.sh）

作成日: 2026-04-21
ステータス: Accepted
対応 Issue: #27
依存設計: docs/spec/lessons-json-schema.md（タスク2）

---

## 概要

Claude Code のセッション開始時（`PreToolUse` または `Start` hook）に
`hooks/session_start.sh` を自動実行し、以下の情報を表示する：

1. 現在スプリントの未完了タスク一覧（`_queue.json` より）
2. このプロジェクト向けの直近 lesson サマリー（`_lessons.json` より、priority 上位 3 件）

エージェントがセッションの冒頭で「今どこにいるか」と「前回の失敗パターン」を
把握した状態で作業を開始できるようにする。

---

## 前提・決定事項

- **hook の発動はプロジェクト単位**（`.claude/settings.json` で登録）
- **`_lessons.json` はグローバル**（`~/.claude/_lessons.json`）
- **`_queue.json` はプロジェクトローカル**（`.claude/_queue.json`）
- `project` フィールドでプロジェクトごとの lesson をフィルタリングする

---

## `.claude/settings.json` への hook 登録

既存の `settings.json` 構造は以下のとおり：

```json
{
  "hooks": {
    "SubagentStop": [ ... ],
    "Stop": [ ... ]
  }
}
```

`PreToolUse` hook を追加する。これにより最初のツール呼び出し前に実行される。

### 更新後の `settings.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/session_start.sh"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/subagent_stop.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/subagent_stop.sh"
          }
        ]
      }
    ]
  }
}
```

**注意**: `PreToolUse` は毎ツール呼び出しごとに実行される。
毎回表示されるとノイズになるため、以下の仕組みで「1セッション1回のみ」に制限する（後述）。

---

## `hooks/session_start.sh` の仕様

### ファイルパス

`.claude/hooks/session_start.sh`

### 動作の全体像

```
起動
 │
 ▼
1回実行済みか？（セッションフラグ確認）
 YES → 即座に exit 0（何も出力しない）
 NO  ↓
 ▼
jq が使えるか確認
 NO → 警告を出して exit 0
 YES ↓
 ▼
未完了タスクを _queue.json から取得して表示
 ↓
_lessons.json が存在するか確認
 NO → "lessons.json 未作成" と表示して終了
 YES ↓
 ▼
このプロジェクトの priority 上位 3 件を取得して表示
 ↓
セッションフラグを立てて exit 0
```

### セッション内1回制限の実装方法

`/tmp/` に `claude_session_start_<PID>.lock` ファイルを作成する。
Claude Code のセッション中は同一の `$PPID`（親PID）が継続するため、
`/tmp/claude_session_start_${PPID}.lock` の有無で判定する。

```bash
SESSION_FLAG="/tmp/claude_session_start_${PPID}.lock"
if [[ -f "$SESSION_FLAG" ]]; then
  exit 0
fi
touch "$SESSION_FLAG"
```

`/tmp/` のファイルはOS再起動またはセッション終了後に消える。
手動でクリアしたい場合は `rm /tmp/claude_session_start_*.lock`。

### プロジェクト名の取得

`_queue.json` の sprint フィールドやリポジトリ名から取得する。
最も確実な方法は `git remote get-url origin` からリポジトリ名を抽出する：

```bash
PROJECT=$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')
if [[ -z "$PROJECT" ]]; then
  # フォールバック: カレントディレクトリ名
  PROJECT=$(basename "$(pwd)")
fi
```

### 表示する情報と jq クエリ

#### 未完了タスク（_queue.json）

```bash
QUEUE_FILE=".claude/_queue.json"

# 未完了タスク（DONE以外）を status・slug・title で表示
jq -r '
  .tasks[] |
  select(.status != "DONE") |
  "  [\(.status)] \(.slug) — \(.title)"
' "$QUEUE_FILE"
```

#### 直近 lesson サマリー（_lessons.json、上位3件）

```bash
LESSONS_FILE="${HOME}/.claude/_lessons.json"

# このプロジェクト向けで未対処（issue_url == null）の lesson を
# priority_score 降順・created_at 降順で上位3件取得
jq -r --arg proj "$PROJECT" '
  [
    .lessons[] |
    select(
      .project == $proj and
      .issue_url == null
    )
  ] |
  sort_by([-.priority_score, -.created_at]) |
  .[0:3][] |
  "  [score:\(.priority_score)] [\(.category)] \(.description | .[0:60])\(if (.description | length) > 60 then "..." else "" end)"
' "$LESSONS_FILE"
```

---

## 出力フォーマット

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SESSION START — agent-crew / sprint-03
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[未完了タスク]
  [IN_PROGRESS] evidence-gate-design — エビデンス閾値ゲートの設計
  [READY_FOR_ALEX] start-hook-design — Start hook 設計
  [TODO] lessons-json-impl — _lessons.json 実装

[直近 lesson（このプロジェクト / 未対処 / priority 上位3件）]
  [score:9] [tooling] queue.sh の Issue open 処理が重複して呼び出される...
  [score:6] [planning] タスク依存関係の設定漏れで並列実行が意図せず発生...
  [score:4] [qa] QA 差し戻し後の retry_count 更新が反映されないことがある...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

未完了タスクが0件の場合：

```
[未完了タスク]
  (なし — 全タスク完了済み)
```

lesson が0件の場合（または `_lessons.json` 未作成の場合）：

```
[直近 lesson]
  (なし — _lessons.json が存在しないか、対象 lesson がありません)
```

---

## エラーハンドリング

| 状況 | 対応 |
|------|------|
| `jq` がインストールされていない | `WARN: jq not found, session_start hook is degraded` を出力して `exit 0` |
| `_queue.json` が存在しない | `[未完了タスク]` セクション自体を省略して出力 |
| `_lessons.json` が存在しない | `(なし — _lessons.json が存在しないか...)` を表示して続行 |
| `git remote` が取得できない | フォールバックでカレントディレクトリ名を使用 |
| jq のパースエラー | エラー出力を抑制（`2>/dev/null`）し、各セクションを `(取得失敗)` と表示 |
| セッションフラグが `/tmp/` に作れない | フラグ機能をスキップし、毎回表示される（許容可能なフォールバック） |

すべてのエラーで `exit 0` を返し、hook の失敗が作業の妨げにならないようにする。

---

## スクリプト全体（設計レベルの擬似実装）

```bash
#!/bin/bash
# .claude/hooks/session_start.sh
# Start hook: セッション開始時に未完了タスクと直近 lesson を表示する

set -u

# ---------- 1. 1セッション1回制限 ----------
SESSION_FLAG="/tmp/claude_session_start_${PPID}.lock"
if [[ -f "$SESSION_FLAG" ]]; then
  exit 0
fi
touch "$SESSION_FLAG" 2>/dev/null || true  # /tmp/ 書き込み失敗は無視

# ---------- 2. 依存チェック ----------
if ! command -v jq >/dev/null 2>&1; then
  echo "WARN: jq not found, session_start hook is degraded" >&2
  exit 0
fi

# ---------- 3. 設定 ----------
QUEUE_FILE=".claude/_queue.json"
LESSONS_FILE="${HOME}/.claude/_lessons.json"

# プロジェクト名取得（git remote → ディレクトリ名フォールバック）
PROJECT=$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')
if [[ -z "$PROJECT" ]]; then
  PROJECT=$(basename "$(pwd)")
fi

# スプリント名取得
SPRINT=$(jq -r '.sprint // "unknown"' "$QUEUE_FILE" 2>/dev/null || echo "unknown")

# ---------- 4. ヘッダー ----------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SESSION START — ${PROJECT} / ${SPRINT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ---------- 5. 未完了タスク ----------
echo "[未完了タスク]"
if [[ -f "$QUEUE_FILE" ]]; then
  INCOMPLETE=$(jq -r '
    .tasks[] |
    select(.status != "DONE") |
    "  [\(.status)] \(.slug) — \(.title)"
  ' "$QUEUE_FILE" 2>/dev/null)
  if [[ -n "$INCOMPLETE" ]]; then
    echo "$INCOMPLETE"
  else
    echo "  (なし — 全タスク完了済み)"
  fi
else
  echo "  (_queue.json が見つかりません)"
fi

echo ""

# ---------- 6. 直近 lesson ----------
echo "[直近 lesson（このプロジェクト / 未対処 / priority 上位3件）]"
if [[ -f "$LESSONS_FILE" ]]; then
  LESSONS=$(jq -r --arg proj "$PROJECT" '
    [
      .lessons[] |
      select(
        .project == $proj and
        (.issue_url == null)
      )
    ] |
    sort_by([-.priority_score, -.created_at]) |
    .[0:3][] |
    "  [score:\(.priority_score)] [\(.category)] \(.description | .[0:60])\(if (.description | length) > 60 then "..." else "" end)"
  ' "$LESSONS_FILE" 2>/dev/null)
  if [[ -n "$LESSONS" ]]; then
    echo "$LESSONS"
  else
    echo "  (なし — 対象 lesson がありません)"
  fi
else
  echo "  (なし — ~/.claude/_lessons.json が存在しません)"
  echo "  初回セットアップ: install.sh を実行してください"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exit 0
```

---

## install.sh への追加事項

タスク11（start-hook-impl）で `install.sh` を更新する際に含める内容：

```bash
# _lessons.json の初期化（存在しない場合のみ）
if [ ! -f "${HOME}/.claude/_lessons.json" ]; then
  echo "INFO: ~/.claude/_lessons.json を初期化します"
  cp "$(dirname "$0")/templates/_lessons.json" "${HOME}/.claude/_lessons.json"
fi

# session_start.sh に実行権限を付与
chmod +x "$(dirname "$0")/.claude/hooks/session_start.sh"
```

---

## 設計トレードオフ

### PreToolUse vs Start hook

Claude Code の hook イベントとして `PreToolUse` と `Start` がある。
`Start` は会話の開始時のみ発火するが、サブエージェント呼び出し時には
発火しないケースがある（環境依存）。
`PreToolUse` は確実に最初のツール使用前に実行されるため採用した。
1回制限（セッションフラグ）で毎ツール実行のノイズを防ぐ。

### PPID vs セッション ID

Claude Code の「セッション」を特定する公式な環境変数は存在しない。
`$PPID`（親プロセスID）は同一セッション中は変化しないため、
セッション識別子として代用できる。
マルチプロセス環境での衝突リスクは低く、許容できる。

### 全 lesson vs プロジェクト固有

グローバルな `_lessons.json` には複数プロジェクトの lesson が混在する可能性がある。
`project` フィールドでフィルタリングすることで、
関係のない lesson が表示されるノイズを防ぐ。

### 3件という件数制限

表示件数を 3 件に絞る理由：
- 毎セッション表示される情報は簡潔であるべき
- 4件以上は「確認したがよく分からない」状態になりやすい
- priority_score 降順で並べるため、重要度の高い 3 件が必ず表示される
- 全件確認が必要な場合は `jq` コマンドを直接実行すればよい

---

## 他コンポーネントとの関係

| コンポーネント | 関係 |
|-------------|------|
| `_lessons.json` スキーマ（タスク2） | `project`・`priority_score`・`issue_url`・`category`・`description` フィールドを使用 |
| エビデンスゲート設計（タスク3） | `issue_url == null` かつ `priority_score >= 4` の条件を共有 |
| みゆきち連携フロー（タスク4） | みゆきちが書き込んだ lesson が次セッションで Start hook に表示される |
| Start hook 実装（タスク11） | このドキュメントの仕様に基づき `session_start.sh` と `settings.json` を更新 |
