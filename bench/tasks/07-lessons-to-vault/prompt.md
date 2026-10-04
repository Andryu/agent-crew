# タスク: 高優先度の教訓を知識vaultへ転記するスクリプトを作る

教訓は $HOME/.claude/_lessons.json に貯まっていく（環境変数 LESSONS_FILE で
差し替え可）。このうち優先度の高いものを Obsidian vault の inbox に Markdown
として書き出す scripts/lessons-to-vault.sh を新しく作ってほしい。

## 動き

- priority_score が MIN_PRIORITY（環境変数、省略時 4）以上の教訓だけを対象に
  する。ちょうど MIN_PRIORITY のものも含む。
- 対象の教訓を sprint ごとにまとめ、
  $VAULT_DIR/inbox/agent-crew-lessons-<sprint>.md に書き出す。
  各教訓の id・description・action が読める形で入っていること。
  VAULT_DIR は環境変数（省略時 $HOME/Workspace/Obsidian）。
- sprint 名の末尾の数字が MIN_SPRINT（環境変数、省略時 24）より小さい sprint は
  書き出さない（古い教訓は別ファイルに整理済みのため）。

## 受け入れ基準

- しきい値ちょうどの教訓は転記され、しきい値未満の教訓は転記されない。
- 省略時の設定では sprint-23 の教訓は転記されず、sprint-24 以降は転記される。
- すでに出力ファイルがある sprint には触らない。2回続けて実行しても、
  vault の中身は1回目とまったく同じままになる。
- jq が無い・LESSONS_FILE が無い・VAULT_DIR が無い場合は、何も書かずに
  終了コード 0 で終わる（フックから呼ばれても他の処理を止めないため）。
- 教訓ファイル自体は書き換えない（読み取りのみ）。
