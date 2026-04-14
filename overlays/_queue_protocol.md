
---

## タスクキュー更新プロトコル（全エージェント共通）

### キューファイル: `.claude/_queue.json`

**重要: キューファイルは必ず `scripts/queue.sh` 経由で更新してください。直接 Write してはいけません。**
アトミック更新・ロック・schema検証・イベント履歴の自動追記が queue.sh で保証されています。

### 作業開始時

```bash
scripts/queue.sh start <slug>
```

→ タスクを `IN_PROGRESS` に遷移し、`events[]` に start イベントを追記。

### 作業完了時（実装・設計エージェント: Alex / Mina / Riku）

```bash
# 1. 自分のタスクを DONE にする
scripts/queue.sh done <slug> <agent> "<完了サマリー1行>"

# 2. 依存解決された次のタスクを READY_FOR_<担当> に解放する
scripts/queue.sh handoff <next-slug> <next-agent>
```

`handoff` は**次に動かせるタスク**（依存が全て DONE になったもの）を指定します。複数ある場合は複数回呼びます。ただし**並列実行禁止のため、実際に進めるのは1タスクだけ**です（他はキュー上で READY だけにしておく）。

### 作業完了時（QAエージェント: Sora）

Sora は `done` ではなく `qa` コマンドを使ってください。

```bash
# 判定結果を記録
scripts/queue.sh qa <slug> APPROVED "<レビューサマリー>"
# または
scripts/queue.sh qa <slug> CHANGES_REQUESTED "<差し戻し理由>"
```

その後、判定に応じて:

- **APPROVED の場合**: `scripts/queue.sh done <slug> Sora "<サマリー>"`
- **CHANGES_REQUESTED の場合**: `scripts/queue.sh retry <slug>`（自動でretry_countがインクリメントされ、READY_FOR_RIKU に戻ります。3回超過で自動 BLOCKED）

### ブロック時

```bash
scripts/queue.sh block <slug> <agent> "<ブロック理由>"
```

→ `BLOCKED` に遷移。Yukiへの報告は別途。

### 状態確認

```bash
scripts/queue.sh show              # 全タスクの要約
scripts/queue.sh show <slug>       # 特定タスクの詳細（events履歴込み）
scripts/queue.sh next              # 次に実行可能な READY_FOR_* タスクを1件
```

### Quality Gate（スプリント完了判定）

スプリントは以下の両方を満たしたときに完了とみなします:

1. 全タスクの `status == "DONE"`
2. QA対象の全タスクで `qa_result == "APPROVED"`

Yuki は最終報告前に `scripts/queue.sh show` で両方を確認してください。

### リトライルール

- Sora の `qa CHANGES_REQUESTED` → `retry <slug>` で自動的に `READY_FOR_RIKU` へ戻る
- `retry_count` が `MAX_RETRY`（デフォルト3）を超えたら自動で `BLOCKED` に遷移
- `BLOCKED` になったタスクはオーナー（人間）の判断待ち
