# handoff: 12-rule-candidates
- from: claude-code/sonnet-5
- at: 2026-08-18T13:33:00Z
- reason: handover（意図的な途中打ち切り。指示による）

## 1. 目的
scripts/lessons.sh にルール書き出し対象を判定する唯一の実装
`list-rule-candidates` を追加し、scripts/propose-lesson-rules.sh の
抽出条件をそこに一本化する。詳細は
bench/tasks/12-rule-candidates/prompt.md を参照。

## 2. 現在地
- HEAD: 未コミット（作業ツリーに変更あり、コミットしていない）
- 変更済みファイル:
  - scripts/lessons.sh — `list-rule-candidates` サブコマンドを追加済み。
    - `--min-priority N`（省略時3、整数以外はエラー終了）
    - `--excluded`（信頼境界のみで除外された教訓だけを出す）
    - 判定ロジックは `_do_list_rule_candidates()` 関数（ファイル末尾、
      `# ---------- コマンド実行 ----------` の直前）に集約。
    - 信頼境界: source_repo を jq 内 `normalize_repo()` で正規化
      （SSH形式/末尾.gitを吸収、既存 bash 側 `normalize_source_repo()` と同等ロジック）
      し、自分の origin（`git remote get-url origin`、無ければ "local"）と比較。
      一致 or source_repo 未設定(null) or owner_approved==true なら対象。
    - CMD 検証リスト（145行目付近）・usage テキスト・引数パース分岐
      （157行目付近の elif チェーン）・実行ディスパッチ（末尾の if/elif チェーン）
      にそれぞれ list-rule-candidates 用の分岐を追加済み。
  - まだ手を付けていない項目（未実装）:
    - `add` に `--owner-approved` フラグを追加し、レコードに真偽値で保存する
      （現状 `_do_add` は owner_approved フィールドを一切書き込まない。
      jq が `.owner_approved` を参照した際 null 扱いになるだけで、動作はするが
      フラグとして明示的にセットする経路がまだ無い）
    - `add` の `--supersedes` に、存在しない教訓IDを渡したときのエラー終了
      （現状 SUPERSEDES はバリデーションなしでそのまま書き込まれる。
      `_do_add` 実行前、ロック内で対象IDの存在チェックを入れる必要あり）
    - `propose-lesson-rules.sh` の抽出処理（86-98行目の jq 直書き）を
      `scripts/lessons.sh list-rule-candidates --min-priority "$MIN_PRIORITY"`
      の呼び出しに置き換える（未着手）
- 動作確認済みのこと:
  - `bash -n scripts/lessons.sh` で構文OK
  - `bash visible_test/smoke.sh` → `visible smoke: OK`
  - 手動テスト（優先度不足/enforcement=code/status=dismissed の除外、
    owner_approved=true と source_repo未設定の許可、外部リポジトリかつ
    未承認のものが `--excluded` にのみ出ることを確認、
    `--min-priority foo` がエラー終了することを確認）済み。テストスクリプトは
    実行後に破棄したので再現するならこの節の手順を再実行してください。

## 3. 次の一手
1. `scripts/lessons.sh` の `add` サブコマンド周りに `--owner-approved` を追加する。
   - 引数パース（198行目付近の `while` ループ、CMD=="add" 内）に
     `--owner-approved) OWNER_APPROVED=true; shift ;;` を追加
     （デフォルト変数 `OWNER_APPROVED=false` を他の add 用変数と並べて宣言）
   - `_do_add()` の `jq -n` 呼び出し（426行目付近）に
     `--argjson owner_approved "$OWNER_APPROVED"` を渡し、出力オブジェクトに
     `owner_approved: $owner_approved` を追加する
2. `add` の `--supersedes` 存在チェックを追加する。
   - `_do_add()` の冒頭（`existing=$(cat "$LESSONS_FILE")` の直後）で、
     `SUPERSEDES` が `"null"` でなければ
     `jq -e --argjson id "$SUPERSEDES" '.lessons[] | select(.id == $id)' <<< "$existing" > /dev/null`
     のようなチェックを行い、無ければ `die` する（ロック内で die すれば
     何も書き込まれずに終了することを確認する）
3. `scripts/propose-lesson-rules.sh` の 86-98行目（LESSONS_JSON=... の jq 直書き）を
   `scripts/lessons.sh list-rule-candidates --min-priority "$MIN_PRIORITY"` の
   呼び出し結果（1行1JSON、既存の `LESSONS_JSON` 変数と同じ形式）に置き換える。
   `LESSON_COUNT` の算出（105行目）はそのまま流用できるはず。

## 4. 未決事項
なし。prompt.md の要件に曖昧な点はなかった。

## 5. 検証方法
- `bash visible_test/smoke.sh` が `visible smoke: OK` で終了すること
- `bash -n scripts/lessons.sh` が構文エラーなく通ること
- 追加実装後、`scripts/lessons.sh add ... --owner-approved` で作成した
  レコードに `"owner_approved": true` が入ることを jq で確認する
- `scripts/lessons.sh add ... --supersedes does-not-exist` がエラー終了し、
  LESSONS_FILE が変更されていないこと（`git diff` や `diff` で書き込み前後を比較）
- `scripts/propose-lesson-rules.sh --dry-run` の提案対象IDの集合が
  `scripts/lessons.sh list-rule-candidates` の出力IDの集合と完全一致すること
  （手で `jq -r .id` して `sort` し `diff` する等）

## 6. 落とし穴
- `_do_add` 内の `die` はロック用サブシェル内で発火するため、呼び出し側で
  `|| exit $?` を必ず明示すること（このファイル内の既存コメント参照、
  596行目付近に同様の注意書きあり）。--supersedes チェックもこの節の中で
  行う必要がある。
- jq の正規表現は oniguruma。bash 側 `normalize_source_repo()` の正規表現
  （BASH_REMATCH使用）とロジックをずらさないよう、今回 jq 側に同じロジックを
  複製した（`_do_list_rule_candidates` 内の `normalize_repo()`）。将来 bash 側の
  正規化ルールを変えるときはこの jq 側にも反映すること（二重管理になっている
  点は本タスクのスコープ外として許容した）。
- `list-rule-candidates` は読み取り専用なのでロック（flock/mkdir lock）を
  取っていない。書き込み系コマンドと同じ関数構造（`_do_*`）には合わせたが
  `execute_with_lock` は経由させていない。
