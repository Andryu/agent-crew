# PLAN: privacy-check.sh の bash 3.2 互換化

## SPEC

**再記述**: `declare -A` を使わない形に書き換え、macOS 標準 `/bin/bash` (3.2.57) で Stop フックの個人情報スキャンを実際に機能させる。検出ロジック・パターン・出力書式は変えない。

**暗黙の前提**: (1) フックは非対話で走り失敗が見えない、(2) 検出パターン文字列は資産であり無改変で移送する、(3) 環境に bash 4+ を追加導入しない。

**テーゼ**: フックスクリプトの機能要件は「環境で最も貧弱なインタプリタで確実に動くこと」であり、シェルの表現力より可搬性が優先する。

## 根本原因

- `scripts/privacy-check.sh:28` の `declare -A PATTERNS` は bash 4 以降の機能。`/bin/bash` は 3.2.57(1) (arm64-apple-darwin25)。
- 6行目の `set -euo pipefail` により、失敗した時点で即 `exit 2`。以降のスキャンは一切走らない。
- 再現（リポジトリ直下、差分あり状態）: `/bin/bash scripts/privacy-check.sh` → `line 28: declare: -A: invalid option` / `exit=2`。本 worktree で再現しないのは 14行目の早期 exit（差分ゼロ）に到達するため。

## 影響範囲

| 呼び出し元 | 実体 | 影響 |
|---|---|---|
| Stop フック | `.claude/settings.json:54` `bash scripts/privacy-check.sh 2>/dev/null \|\| true` | stderr も exit 2 も握り潰され、**スキャンが一度も動いていない**（サイレント無効化）。最大の被害はここ |
| 手動 | `.claude/skills/privacy-audit/SKILL.md:28` | 同じく即失敗（こちらはエラーが見える） |
| 許可設定 | `.claude/settings.json:124` `Bash(scripts/privacy-check.sh *)` | 直接実行経路も存在（shebang 依存） |
| 既知記載 | `docs/plans/2026-08-15-opus-fable-parity.md:97` | 「範囲外の既存不具合」と明記済み。修正時に更新が要る |

他の bash 4 依存: `.sh` 24本を `declare -A` / `local -A` / `mapfile` / `readarray` / `${v^^}` / `${v,,}` / `coproc` で走査 → **該当は当該1行のみ**。`<<<`・`[[ ]]`・添字配列は 3.2 で可。

## 代替案

- **A. 連想配列を廃し「ラベル<TAB>パターン」の添字配列＋パラメータ展開**: 複雑度 低／変更範囲 1ファイル約12行／リスク 低。テーゼ適合。
- **B. shebang を `#!/usr/bin/env bash` に変更**: **却下**。フックは `bash <file>` と明示呼び出しするため shebang は読まれず直らない。加えて `/opt/homebrew/bin/bash`・`/usr/local/bin/bash` とも不在で bash 4+ が環境に無く、可搬性を下げるためテーゼ不適合（足切り）。
- **C. `BASH_VERSINFO` で分岐**: **却下**。静的な7パターンの表のために同一ロジックを2系統保守する。3.2 側は結局 A が必要で、bash4 側は死にコード。
- **D. python3 / awk へ移植**: **却下**。全面書き換えで正規表現方言が変わり、検出挙動の回帰リスクを負う。フック起動コストも増える。

## ミニADR

- **背景**: Stop フックの個人情報ゲートが bash 4 依存により全環境で無効化されている。
- **決定**: A を採用。連想配列をタブ区切りの添字配列に置換する。
- **理由**: 唯一の bash 4 依存が1行に閉じており、パターン文字列を無改変のまま移送できる。実行系（`bash <file>` 明示呼び出し）を前提にしても確実に直る唯一の案。
- **却下案**: B（shebang は読まれず、bash 4+ 自体が不在）／C（死にコードと二重保守）／D（回帰リスクに見合わない）。

## マイクロタスク

### T3-1 連想配列の除去

- **complexity**: S ／ **risk_level**: medium（セキュリティゲートの挙動に直結）
- **目的**: `declare -A` を排し、`/bin/bash` 3.2 で7パターン全てが検出動作すること。
- **対象ファイル**: `/Users/ando_shunsuke/Workspace/agent-crew/.claude/worktrees/opus-fable-parity/scripts/privacy-check.sh`
- **変更内容**:
  1. 28〜35行目を、`TAB=$'\t'` を定義し `PATTERNS=( "メールアドレス${TAB}"'<元のパターン>' … )` の形の添字配列に置換する。ラベルは二重引用符、パターン部は**元の単一引用符文字列をそのままコピー**する（`$'…'` に入れない。バックスラッシュの再解釈を避けるため）。順序と7ラベルは維持。
  2. 56〜57行目の `for label in "${!PATTERNS[@]}"` を `for entry in "${PATTERNS[@]}"` に変更し、ループ先頭で `label="${entry%%$TAB*}"` / `pattern="${entry#*$TAB}"` を取り出す。以降の `grep -nE "$pattern"` 以下は無改変。
- **してはいけないこと**: 正規表現パターン文字列の中身を1文字も変えない／`EXCLUDE_PATTERNS` を増減しない／出力書式（`⚠️  WARNING [ラベル] ファイル`）を変えない／区切りに `|` を使わない（電話番号パターン 35行目が `|` を含むため必ず壊れる）／`.claude/settings.json` を触らない（`2>/dev/null || true` の除去は本タスク範囲外）。
- **検証コマンドと期待出力**:
  - `/bin/bash -n scripts/privacy-check.sh` → 出力なし・exit 0
  - リポジトリ直下に7種のダミー値（実在しない値）を書いた一時ファイルを置き `git add -N <file>` した上で `/bin/bash scripts/privacy-check.sh` → 7ラベル全ての `WARNING` 行が出力され、`echo $?` が **0**（`declare` エラー行が出ないこと）。確認後は一時ファイルと intent-to-add を戻す。
  - 差分ゼロの worktree で実行 → 出力なし・exit 0（早期 exit の回帰なし）

### T3-2 既知不具合記載の更新

- **complexity**: S ／ **risk_level**: low ／ T3-1 に依存（直列）
- **目的**: 修正済みの事実をドキュメントに反映する。
- **対象ファイル**: `/Users/ando_shunsuke/Workspace/agent-crew/.claude/worktrees/opus-fable-parity/docs/plans/2026-08-15-opus-fable-parity.md`
- **変更内容**: 97行目の「既知の未対応」記述を、修正済みである旨（bash 3.2 互換化により Stop フックのスキャンが実働化した）に書き換える。
- **してはいけないこと**: 他節の追記・整形をしない。
- **検証**: `grep -n "privacy-check" docs/plans/2026-08-15-opus-fable-parity.md` → 「未対応」の語が消えている。

## DoD

1. `/bin/bash -n` が通る。
2. `/bin/bash` 3.2 で7ラベル全てが検出され、exit 0（エビデンス: 実行ログ）。
3. 差分ゼロ時の早期 exit に回帰なし。
4. `declare -A` 等の bash 4 構文がリポジトリ全 `.sh` に残っていない（`grep -rn 'declare -A\|mapfile\|readarray' --include='*.sh' .` が空）。
5. パターン文字列が `git diff` 上で無改変（差分がラベル・区切り・ループ構文に限定される）。
6. `docs/plans/2026-08-15-opus-fable-parity.md` 更新済み。

## 付随発見（本タスク範囲外・要 Issue 化）

1. **エラー隠蔽**: Stop フックの `2>/dev/null || true` がこの不具合を気づかせなかった真因。フックのブロックは避けつつ stderr は残す（`|| true` のみ）検討が要る。
2. **未追跡ファイルが対象外**: 11行目の `git diff --name-only HEAD` は untracked を含まないため、**新規作成ファイルは staged にしない限りスキャンされない**。個人情報が最も混入しやすい経路が抜けている。
3. 電話番号パターン（35行目）の後半 `0[0-9]{1,4}[-\s]?…` は日付や連番に誤検知しやすい。実働化により警告ノイズが顕在化する見込み。
