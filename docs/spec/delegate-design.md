# queue.sh → queue.py 委譲設計書

## 概要

`scripts/queue.sh`（Bash実装・1089行）の各コマンドを `scripts/queue.py`（Python実装・Sprint-09作成）に段階的に委譲する。Bashスクリプトをシンラッパーとして残すことで後方互換を維持しつつ、Python側に実装を集約する。

---

## 1. 委譲の全体方針

### 基本戦略: シンラッパー方式

queue.sh の各コマンドハンドラを `python3 scripts/queue.py "$@"` への委譲に書き換える。呼び出し側（エージェント・CI・Makefile）は一切変更不要。

```
呼び出し元（エージェント）
    ↓ scripts/queue.sh start <slug>
queue.sh (シンラッパー)
    ↓ python3 scripts/queue.py start <slug>
queue.py (実装)
    ↓ 読み書き
.claude/_queue.json
```

### 段階化しない理由

全コマンドを一括委譲する。コマンドごとに段階を分けると、移行期間中に「Bashで書いたロックとPythonのfcntlロックが競合する」リスクがある。ロック方式が異なる2実装が同時に動くのは避けるべきであるため、委譲はアトミックに行う。

---

## 2. コマンドルーティング表

| コマンド | queue.py実装 | 委譲後の扱い | 備考 |
|---------|-------------|-------------|------|
| `start` | あり | queue.pyに委譲 | |
| `done` | あり | queue.pyに委譲 | |
| `handoff` | あり | queue.pyに委譲 | |
| `parallel-handoff` | **なし** | Bashに残す | queue.pyに未実装（後述） |
| `qa` | あり | queue.pyに委譲 | |
| `block` | あり | queue.pyに委譲 | |
| `retry` | あり | queue.pyに委譲 | |
| `show` | あり | queue.pyに委譲 | |
| `next` | あり | queue.pyに委譲 | |
| `graph` | **なし** | Bashに残す | Mermaid生成はスコープ外 |
| `detect-stale` | あり | queue.pyに委譲 | |
| `retro` | **一部なし** | 部分委譲（後述） | `--save`/`--decisions`フラグ差異あり |

### 委譲不可コマンドの詳細

**`parallel-handoff`**: queue.py に未実装。使用頻度が低く、queue.sh の Bash 実装をそのまま残す。将来的に queue.py へ追加する場合は別タスクとして切り出す。

**`graph`**: Mermaid 生成ロジックは今スプリントのスコープ外。queue.sh の実装をそのまま残す。

**`retro --save --decisions`**: queue.py の `retro` コマンドは基本集計のみ実装済みだが、`--save`（docs/retro/ への保存）と `--decisions`（docs/DECISIONS.md への追記）フラグが未実装。この2フラグはBashに残すか、queue.py 側に実装追加が必要。

---

## 3. queue.sh の変更範囲

### 変更後のディスパッチ部（1065行以降）

現行のディスパッチ:
```bash
case "$cmd" in
  start)            cmd_start "$@" ;;
  done)             cmd_done "$@" ;;
  ...
esac
```

変更後:
```bash
# Python委譲リスト
_PY_COMMANDS="start done handoff qa block retry show next detect-stale retro"

case "$cmd" in
  graph)
    cmd_graph "$@"
    ;;
  parallel-handoff)
    cmd_parallel_handoff "$@"
    ;;
  ""|help|-h|--help)
    sed -n '2,28p' "$0"
    ;;
  *)
    # Python委譲コマンドかチェック
    if printf '%s\n' $_PY_COMMANDS | grep -qx "$cmd"; then
      exec python3 "$(dirname "$0")/queue.py" "$cmd" "$@"
    fi
    echo "ERROR: unknown command: $cmd" >&2
    exit 1
    ;;
esac
```

### 削除可能な関数

委譲後、以下の関数は不要になる（ただし移行検証完了まで削除しない）:
- `acquire_lock` / `release_lock`
- `require_queue`
- `require_slug_exists`
- `normalize_events_filter`
- `append_event`
- `atomic_write`
- `_emit_signal`
- `calculate_risk`
- `cmd_start` / `cmd_done` / `cmd_handoff` / `cmd_qa` / `cmd_block` / `cmd_retry` / `cmd_show` / `cmd_next` / `cmd_detect_stale` / `cmd_retro`
- `_detect_stale_inline`

移行完了後の最終形では、queue.sh は約50行のシンラッパーになる。

---

## 4. 互換リスクと対策

### 4.1 ロック方式の差異（高リスク）

| | queue.sh | queue.py |
|--|---------|---------|
| ロック方式 | `mkdir`（POSIX アトミック） | `fcntl.flock`（ファイルロック） |
| ロックパス | `.claude/.queue.lock`（ディレクトリ） | `.claude/_queue.json.lock`（ファイル） |

**影響**: 移行前後で混在実行するとロックが機能しない。

**対策**: 委譲はアトミックに行う（段階的移行をしない）。移行後はqueue.py のみがロックを使う。

### 4.2 `start` コマンドの complexity バリデーション（中リスク）

queue.sh の `cmd_start` は complexity が S/M/L でない場合に exit 10 で終了する。queue.py の `start` コマンドはこのバリデーションを行わない。

**対策**: queue.py の `start` コマンドに complexity バリデーションを追加する（Riku への実装依頼事項）。

```python
# queue.py start コマンドに追加
if task.complexity not in ("S", "M", "L", None):
    typer.echo(f"ERROR: complexity must be S, M, or L for {slug} (got: {task.complexity})", err=True)
    raise typer.Exit(10)
```

### 4.3 `qa` コマンドの冪等性ガード（中リスク）

queue.sh の `cmd_qa` は `qa_result` が既に設定済みの場合 exit 14 で拒否する。queue.py の `qa` コマンドには冪等性ガードがない。

**対策**: queue.py の `qa` コマンドに冪等性ガードを追加する（Riku への実装依頼事項）。

```python
# queue.py qa コマンドに追加（lock内）
if task.qa_result is not None:
    typer.echo(f"ERROR: {slug} already has qa_result={task.qa_result}.", err=True)
    raise typer.Exit(14)
```

### 4.4 `show` コマンドの stale 検出（低リスク）

queue.sh の `cmd_show`（引数なし）は `_detect_stale_inline` を呼び出してSTDERRに警告を出す。queue.py の `show` コマンドにはこの動作がない。

**対策**: 動作差異として許容する。`detect-stale` コマンドを明示的に使う運用に変更する。なお `next` コマンドも同様に stale 検出を含むが、これも許容する。

### 4.5 終了コードの互換性

queue.py は typer の `raise typer.Exit(N)` で終了コードを制御しており、queue.sh と同一の終了コード体系を持つことが設計上の目標となっている。

**確認済み互換コード**:
- 2: ロック取得失敗
- 3: queue ファイル不在
- 4: JSON 不正
- 5: 書き込み時 JSON 不正
- 6: slug 不在
- 8: retry 上限超過
- 9: depends_on 未解決
- 11: 既に IN_PROGRESS
- 12: 既に DONE
- 13: BLOCKED
- 15: 既に DONE（done コマンド）

**未確認**: exit 10（complexity バリデーション）、exit 14（qa 冪等性）は queue.py に実装がないため未確認。上記 4.2/4.3 の対策で追加する。

### 4.6 `retro --save --decisions` フラグ（低リスク）

queue.py の `retro` コマンドは `--save` と `--decisions` フラグを受け付けるが、ファイル保存ロジックが未実装（queue.sh と比べ集計内容も簡略）。

**対策**: 今スプリントでは `retro` の委譲を「基本集計のみ」とし、`--save` / `--decisions` は Bash 実装を呼び出すフォールバックを設ける。あるいは `retro` コマンドは委譲対象から外す。

推奨: `retro` は委譲対象から外し、Bash 実装を維持する。将来 queue.py の retro を拡充してから委譲する。

---

## 5. テスト戦略

### 5.1 スモークテスト手順（委譲後）

テスト用キューファイルを使って全委譲コマンドを検証する。

```bash
# 1. テスト用キューを準備
export QUEUE_FILE=/tmp/test_queue.json
cat > $QUEUE_FILE << 'EOF'
{
  "sprint": "smoke-test",
  "tasks": [
    {
      "slug": "task-a",
      "title": "テストタスクA",
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
      "title": "テストタスクB",
      "status": "READY_FOR_SORA",
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

# 2. 各コマンドをテスト
scripts/queue.sh next                              # task-a|riku|テストタスクA を返すこと
scripts/queue.sh start task-a                      # OK: task-a → IN_PROGRESS
scripts/queue.sh done task-a Riku "テスト完了"     # OK: task-a → DONE
scripts/queue.sh handoff task-b Sora               # OK: task-b → READY_FOR_SORA
scripts/queue.sh qa task-b APPROVED "問題なし"     # OK: task-b qa_result = APPROVED
scripts/queue.sh done task-b Sora "QA完了"         # OK: task-b → DONE
scripts/queue.sh detect-stale                      # 警告なし（全DONE）
scripts/queue.sh retro                             # 集計結果を表示

# 3. エラーケースの検証
scripts/queue.sh start task-a                      # ERROR: DONE (exit 12)
scripts/queue.sh done task-a Riku "重複"          # ERROR: DONE (exit 15)
```

### 5.2 回帰テスト

既存の `tests/` 配下にテストが存在する場合は委譲前後で実行して差異がないことを確認する。

```bash
# 委譲前（現行）
python3 -m pytest tests/ -v 2>&1 | tee /tmp/test_before.txt

# 委譲後
python3 -m pytest tests/ -v 2>&1 | tee /tmp/test_after.txt

diff /tmp/test_before.txt /tmp/test_after.txt
```

### 5.3 終了コード検証

```bash
export QUEUE_FILE=/tmp/test_queue.json

# exit 6: slug not found
scripts/queue.sh start nonexistent-slug
echo "exit: $?"  # 6 を期待

# exit 9: depends_on 未解決
# task-b の依存 task-a が DONE でない状態で start を試みる
scripts/queue.sh start task-b
echo "exit: $?"  # 9 を期待
```

---

## 6. ロールバック手順

### 6.1 ロールバックの条件

以下の場合にロールバックを実施する:
- スモークテストで終了コードが期待値と異なる
- `_queue.json` の JSON が不正になった
- agents が動作しなくなった（queue コマンド失敗）

### 6.2 ロールバック手順

委譲実装は `queue.sh` のディスパッチ部のみを変更するため、git による即時ロールバックが可能。

```bash
# queue.sh を変更前の状態に戻す
git diff scripts/queue.sh                    # 変更内容確認
git checkout HEAD -- scripts/queue.sh        # 1ファイルだけ戻す

# キューファイルは変更なし（queue.py/queue.sh は同一スキーマ）
# 既存の _queue.json はそのまま使用可能
```

### 6.3 ロールバック不要な設計上の保証

- `_queue.json` のスキーマは queue.sh / queue.py で共通（設計上の要件）
- queue.py が書いたファイルは queue.sh で読み戻せる
- 環境変数 `QUEUE_FILE` は両実装で共通サポート

---

## 7. Riku への実装依頼事項

### 必須対応（委譲前に実装）

1. **queue.py `start` に complexity バリデーション追加**（4.2参照）
   - S/M/L 以外の場合は exit 10 で終了

2. **queue.py `qa` に冪等性ガード追加**（4.3参照）
   - `qa_result` が既に設定済みの場合は exit 14 で終了

3. **queue.py に `parallel-handoff` コマンド追加**（任意・今スプリントでは不要）
   - 使用頻度が低いため、今スプリントは Bash 実装を維持してもよい

### 任意対応（委譲後でもよい）

4. **queue.py `retro` の `--save` / `--decisions` フラグ実装**
   - 今スプリントは `retro` をBashに残すことで対応可

5. **queue.py `show` での stale 検出**（省略可）
   - `detect-stale` を明示呼び出しする運用で代替

### queue.sh 変更作業

6. **ディスパッチ部の書き換え**（本設計書の3章参照）
   - `start` / `done` / `handoff` / `qa` / `block` / `retry` / `show` / `next` / `detect-stale` の9コマンドを `python3 scripts/queue.py "$cmd" "$@"` に委譲
   - `graph` / `parallel-handoff` / `retro` は Bash 実装を維持

---

## 8. 完了基準

- [ ] 必須対応（1-2）が queue.py に実装されている
- [ ] queue.sh のディスパッチ部が委譲に書き換えられている
- [ ] スモークテスト（5.1）が全コマンドで期待通り動作する
- [ ] 終了コード検証（5.3）で全コードが一致する
- [ ] `_queue.json` スキーマが委譲前後で同一であることを確認
- [ ] ロールバック手順（6.2）を1コマンドで実施できることを確認
