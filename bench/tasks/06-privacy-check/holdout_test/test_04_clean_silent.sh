#!/bin/bash
# 変更が無ければ何も出力しないこと（前提: 変更があれば出力する）
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

mk_repo

# 前提確認（空虚な合格の防止）: 変更があるときは報告される
reset_repo
put_line "src/app.txt" "$LN_GHP" "token: $FAKE_GHP"
run_scan
assert_exit0
assert_reported "src/app.txt" "$LN_GHP"

# 本題: クリーンな作業ツリーでは無出力
reset_repo
run_scan
assert_exit0
[[ ! -s "$OUT" ]] || fail "クリーンなのに stdout に出力: $(cat "$OUT")"
[[ ! -s "$ERR" ]] || fail "クリーンなのに stderr に出力: $(cat "$ERR")"

# 個人情報を含まない変更だけのときも無出力
put_line "src/app.txt" 3 "ただのメモ。特に秘密は無い。"
run_scan
assert_exit0
[[ ! -s "$OUT" ]] || fail "無害な変更で stdout に出力: $(cat "$OUT")"
[[ ! -s "$ERR" ]] || fail "無害な変更で stderr に出力: $(cat "$ERR")"

echo "PASS"
