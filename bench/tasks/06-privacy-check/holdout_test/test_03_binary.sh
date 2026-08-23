#!/bin/bash
# バイナリファイルが混ざっても壊れないこと（中身を垂れ流さない・テキストの検出は続く）
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

mk_repo
reset_repo

# バイナリ（NUL を含む）と、同時に変更されたテキストファイル
printf 'BENCHBIN\000\001\002%s\000\377\376junk\000' "$FAKE_ANTHROPIC" > "$REPO/assets/blob.bin"
put_line "src/app.txt" "$LN_PHONE" "tel: $FAKE_PHONE"

run_scan
assert_exit0

# テキスト側の検出は行われる
assert_reported "src/app.txt" "$LN_PHONE"

# バイナリの中身を stderr に垂れ流していない（NUL バイトが出ていない）
RAW=$(wc -c < "$ERR" | tr -d ' ')
NONUL=$(LC_ALL=C tr -d '\000' < "$ERR" | wc -c | tr -d ' ')
[[ "$RAW" == "$NONUL" ]] || fail "stderr にバイナリ（NUL バイト）が出力されている"
NONPRINT=$(LC_ALL=C tr -d '\11\12\15\40-\176\200-\377' < "$ERR" | wc -c | tr -d ' ')
[[ "${NONPRINT:-0}" -eq 0 ]] || fail "stderr に制御文字が ${NONPRINT} バイト混ざっている"

echo "PASS"
