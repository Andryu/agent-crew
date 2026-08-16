# T3 修正計画: privacy-check.sh の bash 3.2 非対応（PLAN）

## SPEC
- 根本原因: `scripts/privacy-check.sh:28` の `declare -A PATTERNS`（連想配列＝bash 4.0+）。`set -euo pipefail`（:6）下で line 28 が失敗し即終了、スキャン部（:37-67）に一度も到達しない。
- 呼び出し経路: (1) Stop フック `.claude/settings.json:54` `bash -c '... && bash scripts/privacy-check.sh 2>/dev/null || true'` — shebang 無視で `bash`=/bin/bash 3.2.57 が使われ、stderr 破棄＋`|| true` で**失敗が無音化**（=フックは常に成功扱いで一度も検査していない）。(2) `.claude/skills/privacy-audit/SKILL.md:28,78` の手動実行、(3) 許可 `settings.json:124`。CI(.github)からの呼び出しなし。
- 他の bash4 依存: `scripts/ .claude/hooks/` を `declare -A|mapfile|readarray|,,|^^` で走査 → 該当は本1箇所のみ。`[[ =~ ]]`（audit-scan.sh）は 3.2 で動作。
- 環境: `which -a bash` は /bin/bash のみ（Homebrew bash 未導入）。よって shebang や PATH 依存の解決は成立しない。
- テーゼ: **「Stop フックは常に /bin/bash 3.2 で回る。スクリプトはその最小公倍数で完結し、失敗は無音にしない」**。

## PLAN — 代替案
| 案 | 内容 | 複雑度 | 変更範囲 | リスク |
|---|---|---|---|---|
| A 連想配列廃止（`ラベル\|正規表現` の通常配列） | 1ファイル内リファクタ | 低 | 1ファイル | 低（挙動同一、走査順が確定するので出力も安定） |
| B shebang を `#!/usr/bin/env bash` に変更 | — | 低 | 1 | **テーゼ違反**: 呼び出しが `bash scripts/...` で shebang 無効、かつ bash5 未導入 → 却下 |
| C 実行時に BASH_VERSINFO で分岐（4+ は連想配列、3 は代替） | 二重実装 | 中 | 1 | 中（テストされない経路が残る） |
| D フックを `zsh` 化 | 全フック改修 | 高 | settings.json＋各 sh | 高 → 却下 |

### ミニADR
- 背景: macOS 標準 bash 3.2 で連想配列不可、Stop フックが無音失敗。
- 決定: **A**。加えて `set -e` 中の致命失敗が飲まれないよう、Stop フックの検査そのものは残しつつ、スクリプト先頭で bash 3.2 でも動く自己診断（`trap 'echo "privacy-check aborted at line $LINENO" >&2' ERR`）を追加。
- 理由: 3.2 で完結、二重経路なし、diff 最小。
- 却下: B（呼び出し形態で無効・bash5 不在）、C（テストされない分岐が残り、テーゼ「最小公倍数で完結」に反する）、D（過大）。

### マイクロタスク
**MT-1** complexity S / risk_level low（フック経由・機密関連だが読み取り専用スクリプト）
- 目的: 連想配列を bash 3.2 互換の配列に置換し、Stop フックで実際に検査が走る状態にする。
- 対象: `/Users/ando_shunsuke/Workspace/agent-crew/.claude/worktrees/opus-fable-parity/scripts/privacy-check.sh`
- 変更: :28-35 を `PATTERNS=( "メールアドレス|<regex>" ... )` の通常配列に。:56-57 を `for entry in "${PATTERNS[@]}"; do label="${entry%%|*}"; pattern="${entry#*|}"` に。区切り `|` は正規表現内（電話番号 :35 に `|` あり）と衝突するため **区切りは TAB**（`$'\t'`）を使い `${entry%%$'\t'*}` / `${entry#*$'\t'}` で分割。:6 直後に上記 ERR trap を追加。正規表現・ラベル文字列・除外パターン・メッセージは一切変更しない。
- してはいけないこと: settings.json、SKILL.md、他 scripts/ を触らない。パターン追加・削除・改変禁止。`set -euo pipefail` を外さない。shebang 変更禁止。
- 検証: 
  1. `/bin/bash -n scripts/privacy-check.sh` → 出力なし exit 0
  2. `printf 'x@example.com\n090-1234-5678\n' > /tmp/pc_test.md && git add -N /tmp/pc_test.md`（※worktree 内の一時ファイルで実施し検証後 `git rm --cached` で戻す）→ `/bin/bash scripts/privacy-check.sh` → stderr に `WARNING [メールアドレス]` と `WARNING [電話番号(日本)]` の2行、exit 0
  3. `/bin/bash scripts/privacy-check.sh 2>&1 | grep -c 'declare: -A'` → `0`
  4. `grep -c 'declare -A' scripts/privacy-check.sh` → `0`

**MT-2** complexity S / risk_level low（MT-1 依存、直列）
- 目的: 回帰防止。
- 対象: 同ファイル（先頭コメント）と `.claude/skills/privacy-audit/SKILL.md`
- 変更: 先頭コメントに「bash 3.2 互換必須（連想配列・mapfile 禁止）」を1行、SKILL.md の手動実行節に同旨1行を追記。
- 検証: `grep -n 'bash 3.2' scripts/privacy-check.sh .claude/skills/privacy-audit/SKILL.md` → 各1行以上。

## DoD
- `/bin/bash scripts/privacy-check.sh` が 3.2 で exit 0 かつ検出が実際に出る（上記検証2の出力をPRに貼付）。
- `declare -A` がリポジトリの sh から消えている（grep 0件）。
- Stop フックの settings.json は無変更。
- レビュー（Sora）は実装者と別コンテキストで、検証出力を確認して承認。
