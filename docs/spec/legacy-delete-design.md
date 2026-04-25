# legacy-delete-design — queue.sh 旧Bash実装削除設計書

## 概要

Sprint-09 で queue.sh → queue.py への委譲が完了した。現在の queue.sh（1092行）は
委譲後もBash側の関数定義（cmd_start / cmd_done など）を全て保持したままになっており、
「呼ばれないが存在するデッドコード」が約1000行ある。

本設計書は、そのデッドコードを安全に削除してqueue.shを軽量なシンラッパーに変換する
作業の仕様を定義する。

---

## 1. 削除対象の関数一覧

以下の関数・変数は `exec python3 scripts/queue.py` への委譲後は実行されない。
削除後は queue.py 側の実装が単一の信頼源となる。

### 1.1 ロック制御

| 関数名 | 行番号（現行） | 理由 |
|--------|--------------|------|
| `acquire_lock` | 35–58 | queue.py は fcntl.flock を使用、mkdir ロックは不要 |
| `release_lock` | 60–63 | 同上 |
| `LOCK_STALE_SECS=30` | 33 | acquire_lock 内定数、削除対象 |

### 1.2 共通ヘルパー

| 関数名/変数 | 行番号（現行） | 理由 |
|------------|--------------|------|
| `require_queue` | 66–75 | queue.py の load_queue() が代替 |
| `today` | 77 | queue.py の today() が代替 |
| `now_iso` | 78 | queue.py の now_iso() が代替 |
| `_emit_signal` | 83–107 | queue.py の emit_signal() が代替 |
| `atomic_write` | 109–120 | queue.py の save_queue() が代替 |
| `require_slug_exists` | 122–130 | queue.py の get_task() が代替 |
| `normalize_events_filter` | 133–140 | jq フィルタ変数、queue.py 側で不要 |
| `append_event` | 142–153 | queue.py の Task.events.append() が代替 |

### 1.3 リスク計算

| 関数名 | 行番号（現行） | 理由 |
|--------|--------------|------|
| `calculate_risk` | 156–218 | queue.py の calculate_risk() が代替 |

### 1.4 コアコマンド（委譲済み）

以下のコマンド実装は `_PY_COMMANDS` リストに含まれており、
ディスパッチ部から呼ばれることはない。

| 関数名 | 行番号（現行） | 委譲先 |
|--------|--------------|--------|
| `cmd_start` | 221–296 | `queue.py start` |
| `cmd_done` | 299–345 | `queue.py done` |
| `cmd_handoff` | 349–372 | `queue.py handoff` |
| `cmd_qa` | 443–487 | `queue.py qa` |
| `cmd_block` | 490–512 | `queue.py block` |
| `cmd_retry` | 516–559 | `queue.py retry` |
| `cmd_show` | 659–668 | `queue.py show` |
| `cmd_next` | 672–680 | `queue.py next` |
| `cmd_detect_stale` | 641–657 | `queue.py detect-stale` |
| `_detect_stale_inline` | 566–638 | queue.py 内部で代替 |
| `STALE_THRESHOLD_MIN` | 564 | queue.py 側で管理 |

---

## 2. 削除しないもの

以下は queue.py に実装がないか、シェルエントリポイントとして必要なため残す。

### 2.1 コマンド実装（Bashに残す）

| 関数名 | 理由 |
|--------|------|
| `cmd_graph` | queue.py に未実装（graph-py-design タスクで別途移植設計） |
| `cmd_retro` | `--save` / `--decisions` フラグの完全互換実装が queue.py にない |
| `cmd_parallel_handoff` | queue.py に未実装・使用頻度が低い |

### 2.2 シェルエントリポイント・設定

| 対象 | 理由 |
|------|------|
| `#!/bin/bash` shebang + set -euo pipefail | スクリプト実行に必須 |
| `QUEUE_FILE` / `QUEUE_LOCK` / `MAX_RETRY` 変数定義 | 後述フォールバック対応で参照する場合あり |
| コメントヘッダー（使い方・環境変数説明） | 2–25行、人間への説明として残す |
| ディスパッチ部（case 文） | シンラッパーの核心部分 |

---

## 3. 削除後の queue.sh の期待する構造

削除後は以下の構造になる。

```
#!/bin/bash
# queue.sh — agent-crew タスクキュー操作ヘルパー (シンラッパー)
# （コメントヘッダー・使い方説明）

set -euo pipefail

QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"
MAX_RETRY="${MAX_RETRY:-3}"

# ヘルパー: Python が使用可能かチェック
_check_python() { ... }  # フォールバック対応（後述）

# ---------- コマンド: graph ----------
cmd_graph() { ... }

# ---------- コマンド: parallel-handoff ----------
cmd_parallel_handoff() { ... }

# ---------- コマンド: retro ----------
cmd_retro() { ... }

# ---------- ディスパッチ ----------
_PY_COMMANDS="start done handoff qa block retry show next detect-stale"

cmd=${1:-}
shift || true
case "$cmd" in
  graph)           cmd_graph "$@" ;;
  parallel-handoff) cmd_parallel_handoff "$@" ;;
  retro)           cmd_retro "$@" ;;
  ""|help|-h|--help)  sed -n '2,28p' "$0" ;;
  *)
    if printf '%s\n' $_PY_COMMANDS | grep -qx "$cmd"; then
      _check_python || { echo "ERROR: Python3 not available" >&2; exit 99; }
      exec python3 "$(dirname "$0")/queue.py" "$cmd" "$@"
    fi
    echo "ERROR: unknown command: $cmd" >&2
    exit 1
    ;;
esac
```

### 行数目安

| セクション | 削除前 | 削除後 |
|-----------|--------|--------|
| ヘッダー・設定 | 約35行 | 約30行 |
| ヘルパー関数群 | 約110行 | 約15行（`_check_python` のみ） |
| cmd_graph | 約75行 | 約75行（変更なし） |
| cmd_parallel_handoff | 約65行 | 約65行（変更なし） |
| cmd_retro | 約300行 | 約300行（変更なし） |
| 委譲コマンド群 | 約490行 | 0行（全削除） |
| ディスパッチ | 約28行 | 約25行 |
| **合計** | **1092行** | **約510行** |

削除行数の目安: **約580行**（全体の53%）

---

## 4. Pythonが非対応環境でのフォールバック方針

### 方針: フォールバックなし（エラー終了）

agent-crew は Python 3.12+ を前提環境として設定している（`queue.py` ヘッダーの
`# requires-python = ">=3.12"`）。Pythonなし環境でのBash実装維持は設計の複雑性を増す。

フォールバックは「エラーメッセージを出して終了」とし、問題を早期に顕在化させる。

```bash
_check_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. agent-crew requires Python 3.12+." >&2
    echo "  Install: https://python.org/downloads/" >&2
    exit 99
  fi
  local ver
  ver=$(python3 -c "import sys; print(sys.version_info >= (3, 12))" 2>/dev/null || echo "False")
  if [[ "$ver" != "True" ]]; then
    echo "WARN: Python 3.12+ recommended. queue.py may not function correctly." >&2
  fi
}
```

### 根拠

- Bash実装を「緊急フォールバック」として保持すると、「どちらが正しいか」の混乱を招く
- エラー終了することで、環境不備を検知しやすくなる
- `cmd_graph` / `cmd_retro` / `cmd_parallel_handoff` はBashのまま残るため、
  Python未使用の軽量操作はある程度カバーされる

---

## 5. ロールバック手順

削除作業は queue.sh の1ファイル変更のみであるため、git で即時ロールバック可能。

```bash
# 削除実装の確認
git diff scripts/queue.sh | head -50

# ロールバック（1ファイル）
git checkout HEAD -- scripts/queue.sh

# または特定コミットに戻す
git log --oneline scripts/queue.sh   # 変更前のコミットhashを確認
git checkout <hash> -- scripts/queue.sh
```

### ロールバック後の状態

- queue.sh は旧Bash実装を持つ完全版に戻る
- `_PY_COMMANDS` リストが生きているため、委譲コマンドはPython実行が続く
- queue.py は独立しており、ロールバック対象外

### ロールバックが不要な設計上の保証

- `_queue.json` スキーマは queue.sh / queue.py で共通
- queue.py が書いたファイルを queue.sh が読み直せる
- 環境変数 `QUEUE_FILE` / `MAX_RETRY` は両実装で共通サポート

---

## 6. 完了確認手順

### 6.1 pytestによる回帰テスト

```bash
# 依存インストール（未済の場合）
pip install typer pydantic pytest

# または uv 使用
uv run pytest tests/ -v

# 期待結果: 全テストがPASS
```

### 6.2 スモークテスト一覧

以下のコマンドを順番に実行し、期待通りの出力・終了コードを確認する。

```bash
export QUEUE_FILE=/tmp/test_legacy_delete.json
cat > $QUEUE_FILE << 'EOF'
{
  "sprint": "smoke-test",
  "tasks": [
    {
      "slug": "task-a",
      "title": "テストA",
      "status": "READY_FOR_RIKU",
      "assigned_to": "Riku",
      "complexity": "S",
      "risk_level": "low",
      "depends_on": [],
      "retry_count": 0,
      "qa_result": null,
      "events": [],
      "created_at": "2026-04-24",
      "updated_at": "2026-04-24"
    },
    {
      "slug": "task-b",
      "title": "テストB",
      "status": "TODO",
      "assigned_to": "Sora",
      "complexity": "M",
      "risk_level": "medium",
      "depends_on": ["task-a"],
      "retry_count": 0,
      "qa_result": null,
      "events": [],
      "created_at": "2026-04-24",
      "updated_at": "2026-04-24"
    }
  ]
}
EOF
```

| # | コマンド | 期待出力 | 期待終了コード |
|---|---------|---------|--------------|
| 1 | `scripts/queue.sh next` | `task-a\|riku\|テストA` | 0 |
| 2 | `scripts/queue.sh start task-a` | `OK: task-a → IN_PROGRESS` | 0 |
| 3 | `scripts/queue.sh start task-a` | `ERROR: already IN_PROGRESS` | 11 |
| 4 | `scripts/queue.sh done task-a Riku "完了"` | `OK: task-a → DONE` | 0 |
| 5 | `scripts/queue.sh done task-a Riku "重複"` | `ERROR: already DONE` | 15 |
| 6 | `scripts/queue.sh handoff task-b Sora` | `OK: task-b → READY_FOR_SORA` | 0 |
| 7 | `scripts/queue.sh start task-b` | `OK: task-b → IN_PROGRESS` | 0 |
| 8 | `scripts/queue.sh qa task-b APPROVED "OK"` | `OK: task-b qa_result = APPROVED` | 0 |
| 9 | `scripts/queue.sh qa task-b APPROVED "重複"` | `ERROR: already has qa_result` | 14 |
| 10 | `scripts/queue.sh done task-b Sora "完了"` | `OK: task-b → DONE` | 0 |
| 11 | `scripts/queue.sh detect-stale` | 警告なし（全DONE） | 0 |
| 12 | `scripts/queue.sh block task-a Riku "テスト"` | `BLOCKED: task-a (テスト)` | ※ |
| 13 | `scripts/queue.sh start nonexistent` | `ERROR: slug not found` | 6 |
| 14 | `scripts/queue.sh graph` | Mermaid flowchart 出力 | 0 |
| 15 | `scripts/queue.sh retro` | 集計結果テキスト出力 | 0 |

※ task-a は DONE 状態のため、DONE→BLOCKED 遷移の可否は queue.py の実装に依存。
  動作確認のみ行い、終了コードは記録する。

### 6.3 削除完了の確認

```bash
# 行数確認（目安: 550行以下）
wc -l scripts/queue.sh

# 削除済みのはずの関数が残っていないことを確認
grep -n "^cmd_start\|^cmd_done\|^cmd_handoff\|^cmd_qa\|^cmd_block\|^cmd_retry\|^acquire_lock\|^release_lock" scripts/queue.sh
# 出力なしを期待

# 残存すべき関数が存在することを確認
grep -n "^cmd_graph\|^cmd_retro\|^cmd_parallel_handoff" scripts/queue.sh
# 3行ヒットを期待
```

---

## 7. 依存タスク

- `graph-py-design`: cmd_graph の Python 移植設計（本タスク完了後に着手）
- `legacy-delete-impl`: 本設計書に基づく Riku の実装タスク
