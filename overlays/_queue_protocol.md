
---

## タスクキュー更新プロトコル（全エージェント共通）

### キューファイル: `.claude/_queue.json`

### ステータス遷移

| ステータス | 意味 |
|-----------|------|
| `TODO` | 未着手（Yukiがタスク分解時に設定） |
| `READY_FOR_ALEX` | Alexの作業待ち |
| `READY_FOR_MINA` | Minaの作業待ち |
| `READY_FOR_RIKU` | Rikuの作業待ち |
| `READY_FOR_SORA` | Soraの作業待ち |
| `IN_PROGRESS` | 誰かが作業中 |
| `DONE` | 完了 |
| `BLOCKED` | ブロック中（notes に理由） |

### 作業開始時の手順

1. `.claude/_queue.json` を Read で読む
2. 指示された slug のタスクを見つける
3. そのタスクの `status` を `IN_PROGRESS` に更新
4. `updated_at` を今日の日付（YYYY-MM-DD）に更新
5. ファイルを Write で保存

### 作業完了時の手順

1. `.claude/_queue.json` を Read で読む
2. 自分のタスクの `status` を `DONE` に更新
3. `notes` に完了サマリーを1行追記（例: "設計完了。ADR 5件作成"）
4. **次に動かせるタスクを探して `READY_FOR_[担当]` に更新**
   - 依存（notes の "依存: xxx"）が全て DONE になっているタスクを見つける
   - そのタスクの `assigned_to` を見て、`READY_FOR_ALEX` / `READY_FOR_MINA` / `READY_FOR_RIKU` / `READY_FOR_SORA` に設定
   - 複数同時に動かせる場合は全部更新してOK（並列実行可）
5. ファイルを Write で保存

### ブロック時

`status` を `BLOCKED` に更新し、`notes` にブロック理由を記載。Yukiへの報告を別途行う。

### 注意

- キュー更新は**必ず作業の最後に行う**（作業成果物の作成後）
- 他のタスクのステータスを勝手に書き換えない（自分のタスクと、自分が解放する次タスクのみ）
- JSON形式が壊れないように Write 前に読み直してから編集する
