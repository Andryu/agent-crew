#!/bin/bash
# 日付・時刻・バージョン番号を電話番号として誤検出しないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

mk_repo

# 前提確認（空虚な合格の防止）: 本物の形の電話番号はきちんと報告される
reset_repo
put_line "notes/phone.md" "$LN_PHONE" "tel: $FAKE_PHONE"
run_scan
assert_exit0
assert_reported "notes/phone.md" "$LN_PHONE"

# 本題: 日付だけのファイルは報告されない
Y=$(( 2020 + $(t_rand 41 8) ))
M=$(printf '%02d' $(( 1 + $(t_rand 42 12) )))
D=$(printf '%02d' $(( 1 + $(t_rand 43 28) )))
h=$(printf '%02d' "$(t_rand 44 24)")
mi=$(printf '%02d' "$(t_rand 45 60)")
s=$(printf '%02d' "$(t_rand 46 60)")

reset_repo
mkdir -p "$REPO/notes"
{
  echo "# 変更履歴"
  echo "released $Y-$M-$D"
  echo "also $Y/$M/$D"
  echo "jp ${Y}年${M}月${D}日"
  echo "iso $Y-$M-${D}T$h:$mi:$s+0900"
  echo "time $h:$mi:$s"
  echo "version 1.$M.$D"
} > "$REPO/notes/dates.md"

# dates.md が確かにスキャン対象（変更あり）になっていること
git -C "$REPO" status --porcelain | grep -q 'notes/dates.md' \
  || fail "fixture 不備: notes/dates.md が変更として認識されていない"

run_scan
assert_exit0
assert_not_reported "notes/dates.md"

echo "PASS"
