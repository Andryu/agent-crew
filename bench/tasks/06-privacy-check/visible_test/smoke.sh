#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物・固定値）:
#   メールアドレスを含む変更ファイルが、ファイル名＋行番号つきで stderr に出るか。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
SCRIPT="$WORK/scripts/privacy-check.sh"
[[ -f "$SCRIPT" ]] || { echo "NG: scripts/privacy-check.sh が無い" >&2; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/repo"
cd "$TMP/repo"
git init -q .
git config user.email smoke@example.invalid
git config user.name smoke
printf 'placeholder\n' > memo.txt
git add -A && git commit -qm init
printf 'line1\nline2\ncontact: smoke.user@example.invalid\n' > memo.txt

set +e
ERR=$(bash "$SCRIPT" 2>&1 >/dev/null)
RC=$?
set -e

[[ "$RC" -eq 0 ]] || { echo "NG: 終了コードが 0 でない ($RC)" >&2; exit 1; }
echo "$ERR" | grep -q 'memo.txt' || { echo "NG: ファイル名が出ていない" >&2; exit 1; }
echo "$ERR" | grep -qE '(^|[^0-9])3:' || { echo "NG: 行番号が出ていない" >&2; exit 1; }

echo "visible smoke: OK"
