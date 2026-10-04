# handoff: lessons-set-status
- from: codex/gpt-5
- at: 2026-08-18T12:42:52Z
- reason: handover

## 1. 目的
`scripts/lessons.sh` の lesson に5値の `status` を追加し、`add` で設定可能にする。さらに `set-status <id> <status>` で対象 lesson の `status` と `updated_at` だけを原子的に更新できるようにする。

## 2. 現在地
- HEAD: `cf21f7555b06167f673108fb3f8bdc1ae63e4e13`（未コミット変更あり）
- 変更済みファイル: `scripts/lessons.sh` — `add --status` のヘルプ、既定値 `proposed`、5値の検証、JSONレコードへの保存を追加。
- 変更済みファイル: `docs/handoff/handoff.md` — この引き継ぎ書を追加。
- 動作確認済みのこと: `bash -n scripts/lessons.sh` は成功。手動実行で status 省略時 `proposed`、明示時 `implemented`、`priority_score` 維持を確認。不正 status は終了コード1で、`cmp` によりファイル非変更を確認。
- 動作確認済みのこと: `bash visible_test/smoke.sh` は `ERROR: unknown command: 'set-status'` で終了コード1。これは残作業どおりの想定失敗。
- 作業開始時から `TASK.md` と `visible_test/` は未追跡。変更していない。

## 3. 次の一手
1. `scripts/lessons.sh` の `CMD` 分岐を `add` / `set-status` 対応にし、`set-status` は位置引数が厳密に2個であることと status の5値を、書き込み前に検証する。
2. ロック内でファイルを読み、`jq -e --arg id "$id" '.lessons | any(.id == $id)'` 相当でID存在確認後、対象だけを `status` と UTC の `updated_at` に更新する。既存の一時ファイル＋`mv` を共用し、エラー時は一時ファイルを作らない。
3. `usage` に `set-status <id> <status>` を追記する。必要なら `docs/spec/lessons-json-schema.md` に status enum と更新用途を反映する。
4. `bash visible_test/smoke.sh` を実行し、その後、不正status・不存在IDでファイルが完全一致する手動テストを追加実行する。

## 4. 未決事項
なし。

## 5. 検証方法
リポジトリ直下で `bash -n scripts/lessons.sh && bash visible_test/smoke.sh` を実行する。加えて一時 lessons JSON に複数レコードを用意し、`set-status` 前後を `jq` で比較して、対象の `status` と `updated_at` 以外が同一、他レコードが同一、不正status・不存在IDでは `cmp` が成功することを確認する。

## 6. 落とし穴
- `holdout_test/` は絶対に開かない。`/Users/ando_shunsuke/Workspace/agent-crew` と GitHub も参照禁止。
- この環境には `flock` がなく、実行時は既存の非ロック fallback と警告が使われる。`flock` 分岐と fallback の両方で新コマンドを呼べる構造にする。
- `set-status` の不正入力・不存在ID判定は、一時ファイル作成や `mv` より前に行う。対象の `description` 等を再構築せず、jq の `map(if .id == $id then ... else . end)` で2フィールドだけ変更する。
