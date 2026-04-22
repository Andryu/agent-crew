# 設計ドキュメント: fix-sora-dup — Sora 重複実行防止

**作成日**: 2026-04-22
**担当**: Alex
**対応 Issue**: GitHub #38
**ステータス**: 確定（Riku へ引き継ぎ）

---

## 1. 問題の概要

sprint-02 において、QAエージェント Sora が同一タスクに対して以下の2パターンの重複イベントを発行することが確認された。

| パターン | 発生状況 | 影響 |
|---------|---------|------|
| `start` 重複 | 同一タスクに `start` を複数回実行（8時間以上のギャップあり） | `events[]` に start イベントが複数記録され、retro の実行時間計算が崩れる |
| `qa` 二重送信 | QAタスク8件中6件（75%）で `qa` イベントが2回記録される | `qa_result` が最後の実行結果で上書きされる。APPROVED → CHANGES_REQUESTED または逆転のリスクがある |

---

## 2. 根本原因分析

### 2.1 `start` コマンドに状態チェックが存在しない

`cmd_start` の現実装（queue.sh 191-242行）を確認すると、以下のチェックしか行っていない：

1. `depends_on` の全タスクが DONE であること
2. `complexity` が S/M/L のいずれかであること

**現在の status 遷移制限がゼロ**。タスクが `IN_PROGRESS` や `DONE` であっても `start` を再実行できてしまう。

Sora のエージェントプロセスが何らかの理由（タイムアウト後の再起動、並列呼び出し）で再起動した場合、`start` を再発行すると無条件に受け付けられる。

### 2.2 `qa` コマンドに冪等性チェックが存在しない

`cmd_qa` の現実装（queue.sh 374-398行）を確認すると、`qa_result` フィールドへの上書き制限がない。

- `qa_result` が既に `APPROVED` であっても、再度 `qa CHANGES_REQUESTED` を送ると上書きされる
- エージェントが同じコマンドを2回送信した場合、後の結果で前の結果が消える

### 2.3 `done` コマンドにも同様のリスクがある

`cmd_done`（queue.sh 245-278行）も status が `DONE` のタスクに対して再実行できてしまう。`events[]` に重複 done イベントが積まれ、`summary` が上書きされる。

### 2.4 エージェント側（Sora）の再起動が引き金

Sora が 8 時間以上のギャップをおいて `start` を再発行していることから、以下のシナリオが考えられる。

```
時刻 T1: Sora が start 実行 → IN_PROGRESS
時刻 T2: Sora プロセスがタイムアウト or 何らかの理由で終了
時刻 T3: Sora が再起動、あるいは別の呼び出しが発生
時刻 T4: Sora が再度 start を実行 → 拒否されずに events に重複記録
```

根本的には「エージェントの冪等性保証がない」ことが問題だが、それをエージェント側だけで解決するのは困難（エージェント自身が状態を把握できない場合がある）。

---

## 3. 修正方針の選定

### 案1: エージェント（Sora）側でチェック

Sora が `start` 前に `queue.sh show <slug>` で現在 status を確認し、`IN_PROGRESS` なら `start` しない。

**トレードオフ**:
- 良い: queue.sh に変更不要
- 悪い: エージェントの実装に依存するため信頼性が低い。Sora のプロンプト改訂だけでは将来の他エージェントの問題を防げない。「信頼できない呼び出し元を信頼する」設計になる

### 案2: queue.sh 側にガード追加（採用）

queue.sh の各コマンドに事前条件チェックを追加し、不正な状態遷移を拒否してエラー終了する。

**トレードオフ**:
- 良い: エージェントの実装品質に依存しない。一箇所の変更で全エージェントに適用される。ログにエラーとして記録されるため問題の検出も容易
- 悪い: queue.sh の各コマンドに数行追加が必要。エラー時にエージェントが適切にハンドリングしないと作業が止まる可能性がある

**案2を採用する**。エージェント呼び出し元を信頼しない「防御的スクリプティング」の原則に沿っており、変更箇所が集中していてレビューしやすい。

---

## 4. 設計: queue.sh に追加するガード

### 4.1 ガードが必要なコマンドと許可する遷移

| コマンド | 現在の status 制限 | 追加するチェック |
|---------|-----------------|----------------|
| `start` | なし | `IN_PROGRESS` または `DONE` なら拒否 |
| `qa` | なし | `qa_result` が既に非 null なら拒否 |
| `done` | なし | `DONE` なら拒否 |

### 4.2 許可する status 遷移マトリクス

```
start コマンド:
  READY_FOR_*  → IN_PROGRESS  (許可)
  TODO         → IN_PROGRESS  (許可: depends_on が空の場合)
  IN_PROGRESS  → エラー終了   (ガード追加)
  DONE         → エラー終了   (ガード追加)
  BLOCKED      → エラー終了   (ガード追加)

qa コマンド:
  qa_result == null  → qa_result 更新  (許可)
  qa_result != null  → エラー終了      (ガード追加)

done コマンド:
  IN_PROGRESS         → DONE  (許可)
  READY_FOR_*         → DONE  (許可: 現行動作を維持)
  DONE                → エラー終了  (ガード追加)
```

### 4.3 疑似コード（diff 形式）

#### cmd_start へのガード追加

```diff
  cmd_start() {
    local slug=${1:?slug required}
    acquire_lock
    require_queue
    require_slug_exists "$slug"

+   # 状態ガード: 既に IN_PROGRESS または DONE なら重複実行を拒否
+   local current_status
+   current_status=$(jq -r --arg s "$slug" \
+     '.tasks[] | select(.slug == $s) | .status' "$QUEUE_FILE")
+   case "$current_status" in
+     IN_PROGRESS)
+       release_lock
+       echo "ERROR: $slug is already IN_PROGRESS. 'start' is idempotent-safe; skip if already started." >&2
+       exit 11
+       ;;
+     DONE)
+       release_lock
+       echo "ERROR: $slug is already DONE. Cannot re-start a completed task." >&2
+       exit 12
+       ;;
+     BLOCKED)
+       release_lock
+       echo "ERROR: $slug is BLOCKED. Resolve the block before restarting." >&2
+       exit 13
+       ;;
+   esac

    # depends_on の全タスクが DONE かチェック（既存コード）
    ...
```

#### cmd_qa へのガード追加

```diff
  cmd_qa() {
    local slug=${1:?slug required}
    local result=${2:?result required (APPROVED|CHANGES_REQUESTED)}
    local msg=${3:-""}
    case "$result" in
      APPROVED|CHANGES_REQUESTED) ;;
      *) echo "ERROR: result must be APPROVED or CHANGES_REQUESTED" >&2; exit 7 ;;
    esac
    acquire_lock
    require_queue
    require_slug_exists "$slug"

+   # 冪等性ガード: qa_result が既に設定済みなら重複送信を拒否
+   local current_qa_result
+   current_qa_result=$(jq -r --arg s "$slug" \
+     '.tasks[] | select(.slug == $s) | .qa_result // "null"' "$QUEUE_FILE")
+   if [[ "$current_qa_result" != "null" ]]; then
+     release_lock
+     echo "ERROR: $slug already has qa_result=$current_qa_result. Use 'retry' to reset before re-QA." >&2
+     exit 14
+   fi

    local updated
    ...
```

#### cmd_done へのガード追加

```diff
  cmd_done() {
    local slug=${1:?slug required}
    local agent=${2:?agent required}
    local msg=${3:-"完了"}
    acquire_lock
    require_queue
    require_slug_exists "$slug"

+   # 状態ガード: 既に DONE なら重複完了を拒否
+   local current_status
+   current_status=$(jq -r --arg s "$slug" \
+     '.tasks[] | select(.slug == $s) | .status' "$QUEUE_FILE")
+   if [[ "$current_status" == "DONE" ]]; then
+     release_lock
+     echo "ERROR: $slug is already DONE. Duplicate 'done' call detected." >&2
+     exit 15
+   fi

    local updated
    ...
```

### 4.4 終了コード体系

既存の終了コードと衝突しないよう、ガード追加分を 11〜15 に割り当てる。

| 終了コード | 意味 |
|-----------|------|
| 11 | start: タスクは既に IN_PROGRESS |
| 12 | start: タスクは既に DONE |
| 13 | start: タスクは BLOCKED |
| 14 | qa: qa_result が既に設定済み |
| 15 | done: タスクは既に DONE |

既存コード（参考）:
- 2: ロック取得失敗
- 3: queue ファイル不在
- 4: JSON 不正
- 5: 生成 JSON 不正
- 6: slug 不在
- 7: qa result 不正値
- 8: retry 上限超過
- 9: depends_on 未解決
- 10: complexity 不正値

---

## 5. 実装で注意すること（Riku へ）

### 5.1 ロックの取得タイミング

ガードチェックは必ず `acquire_lock` の後で実行すること。ロック取得前にチェックすると TOCTOU（チェックと更新の間の競合）が発生する可能性がある。現在の実装もロック後にチェックしているので、その構造を維持する。

### 5.2 エラー時は必ず release_lock を呼ぶ

既存コードのパターンを踏襲し、早期リターン前に必ず `release_lock` を呼び出す。呼び忘れるとロックが残りっぱなしになり、30秒後のスタールロック検出まで他のコマンドがブロックされる。

### 5.3 エラーメッセージは STDERR へ

`exit 11〜15` の前のメッセージはすべて `>&2` に出力する（既存パターンと同様）。STDOUT はスクリプトの呼び出し元がパースするため、エラーメッセージを混入させない。

### 5.4 retry コマンドによる qa_result リセットの確認

`cmd_retry` は `qa_result = null` にリセットしている（459行目: `.qa_result = null`）。これにより、`retry` 後は再度 `qa` を受け付けるようになる。この連携が正しく機能することをテストで確認すること。

### 5.5 テストシナリオ

以下のシナリオが全て想定通りに動作することを確認する：

1. `start` → `start`（2回目）→ exit 11 でエラー終了
2. `start` → `done` → `done`（2回目）→ exit 15 でエラー終了
3. `start` → `qa APPROVED` → `qa APPROVED`（2回目）→ exit 14 でエラー終了
4. `start` → `qa CHANGES_REQUESTED` → `retry` → `qa APPROVED`（正常フロー）→ 成功

---

## 6. 対象外の変更

以下は今回スコープ外とする：

- **`handoff` コマンドのガード**: 現状 `status` を上書きするため、`DONE` 後の再ハンドオフも起きうるが、Sora の重複問題とは直接関係しない。別 Issue で対応する。
- **エージェント側（qa.md / architect.md）の修正**: 案2（queue.sh 側ガード）で十分。エージェントプロンプトの改訂は今回行わない。
- **subagent_stop.sh の変更**: Sora の重複起動はエージェントプロセスレベルの問題であり、hook スクリプトでの対応は複雑性を増すのみ。ガードは queue.sh 側で一元管理する。

---

## 7. 完了条件（Riku 向け DoD）

- [ ] `cmd_start` に状態ガードが追加されている（exit 11/12/13）
- [ ] `cmd_qa` に冪等性ガードが追加されている（exit 14）
- [ ] `cmd_done` に状態ガードが追加されている（exit 15）
- [ ] 上記4シナリオのテストが通ることを手動または自動テストで確認している
- [ ] `retry` 後に `qa` が再実行可能であることを確認している
- [ ] `docs/spec/fix-sora-dup-design.md`（本ドキュメント）と実装の差異がない
