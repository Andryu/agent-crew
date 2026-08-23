#!/bin/bash
# 除外対象（.env* / *.lock / node_modules/ / settings.local.json）を誤検出しないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

mk_repo

# 前提確認（空虚な合格の防止）: 普通のファイルなら同じ内容がきちんと報告される
reset_repo
put_line "src/app.txt" "$LN_EMAIL" "owner: $FAKE_EMAIL"
run_scan
assert_exit0
assert_reported "src/app.txt" "$LN_EMAIL"

# 本題: 除外対象は同じ内容でも報告しない
reset_repo
put_line ".env"                         "$LN_EMAIL" "OWNER=$FAKE_EMAIL"
put_line ".env.local"                   "$LN_PATH"  "HOME_DIR=$FAKE_PATH"
put_line "vendor/deps.lock"             "$LN_GHP"   "sig = $FAKE_GHP"
put_line "node_modules/pkg/index.js"    "$LN_PHONE" "// tel: $FAKE_PHONE"
put_line ".claude/settings.local.json"  "$LN_SLACK" "{\"hook\": \"$FAKE_SLACK\"}"
run_scan
assert_exit0
assert_not_reported ".env"
assert_not_reported ".env.local"
assert_not_reported "vendor/deps.lock"
assert_not_reported "node_modules/pkg/index.js"
assert_not_reported ".claude/settings.local.json"

echo "PASS"
