# handoff: 07-lessons-to-vault
- from: claude-code/sonnet-5
- at: 2026-08-18T13:40:00Z
- reason: quota（作業時間上限のため中断）

## 1. 目的
`scripts/lessons-to-vault.sh` を新規作成する。`$LESSONS_FILE`（既定
`$HOME/.claude/_lessons.json`）の教訓のうち `priority_score >= MIN_PRIORITY`
（既定4、以上=境界含む）かつ sprint 末尾番号 `>= MIN_SPRINT`（既定24）のものを
sprint ごとに `$VAULT_DIR/inbox/agent-crew-lessons-<sprint>.md` へ Markdown 転記する。
詳細仕様は `../../TASK.md` （= 課題の prompt.md と同一内容）を参照。

## 2. 現在地
- HEAD: 24ff52f（未コミット、実装はワークツリー上のみ）
- 変更済み/新規ファイル:
  - `scripts/lessons-to-vault.sh` — 実装完了・実行権限付与済み（chmod +x 済み）
- 動作確認済みのこと（すべて手動実行しPASS済み、実装後に自動コミットはしていない）:
  - `bash visible_test/smoke.sh` → `visible smoke: OK`
  - priority_score が閾値ちょうど(4)のものは転記され、閾値未満(3)のものは転記されない
  - sprint-23（MIN_SPRINT=24未満）は出力されず、sprint-24/sprint-25は出力される
  - 2回連続実行しても出力ファイルの md5 が変化しない（既存ファイルはスキップする仕様通り）
  - `LESSONS_FILE` が存在しない場合 → exit 0、何も書かない
  - `VAULT_DIR` が存在しない場合 → exit 0、何も書かない
  - `jq` が PATH に無い場合（PATH からjq以外のみのシンボリックリンクで再現） → exit 0、何も書かない
  - `$HOME/.claude/_lessons.json`（実ファイル）は一切書き換えていない（読み取りのみ）

## 3. 次の一手
1. 実装内容をレビューする: `cat scripts/lessons-to-vault.sh`
2. holdout_test は絶対に開かないこと（指示済みの制約）。追加検証したい場合は
   visible_test/smoke.sh 相当の自作テストケースを一時ディレクトリ (`mktemp -d`) で
   行うこと（本物の `$HOME/.claude/_lessons.json` や実 vault には触れない）。
3. 特に念入りに見るべき箇所:
   - sprint 名の末尾数字抽出は `grep -oE '[0-9]+$'`。もし数字が取れない特殊な
     sprint 名（例: "sprint-final" のような命名）がテストで使われた場合、現状は
     「数字が取れなければ MIN_SPRINT 判定をスキップしてそのまま転記する」実装になっている。
     これが要件と合っているか要確認（未決事項参照）。
   - Markdown 出力の具体的な書式（見出しレベルや箇条書きの形）は仕様上自由度があるため、
     テスト側が特定の正規表現/文字列を期待していないか visible_test 以外のヒントがあれば確認。
4. 問題なければ `git add scripts/lessons-to-vault.sh` してコミット（ユーザーの明示指示があれば）。

## 4. 未決事項
- sprint 名が "sprint-<数字>" 以外の形式（数字が末尾に無い）だった場合の扱いは
  課題文に明記がなく、現状は「除外しない」寄りの実装にしてある。holdout側でこのケースを
  問われたら要件を再確認して調整すること。人間確認が必要なら止めて聞くこと。

## 5. 検証方法
```bash
cd <このリポジトリ>
bash visible_test/smoke.sh   # "visible smoke: OK" が出ればOK
```
追加で境界値・冪等性・欠如系のケースを検証したい場合は、`mktemp -d` で作った
一時ディレクトリに `_lessons.json` と `vault/` を用意し、
`env HOME=... VAULT_DIR=... LESSONS_FILE=... bash scripts/lessons-to-vault.sh`
の形で実行して確認する（実ホームディレクトリには絶対に影響を与えないこと）。

## 6. 落とし穴
- jq 不在ケースを `PATH=/nonexistent` でテストすると `bash` 自体も見つからず
  `env` が失敗して誤った exit code (127) が返る。jq だけを除いた PATH
  （他の必要コマンドへのシンボリックリンクを張った一時ディレクトリ）を作ってテストすること。
- `set -uo pipefail` を使っており `set -e` は入れていない（`||`
  を使ったフォールバックを随所に書いているため、`-e` を足すと意図と衝突する箇所がある。
  安易に `set -euo pipefail` に変更しないこと）。
- 出力は `.tmp` ファイルに書いてから `mv` している（部分書き込みで既存ファイル判定を
  汚さないため）。書き込みロジックを変更する際もこのアトミック性は維持すること。
