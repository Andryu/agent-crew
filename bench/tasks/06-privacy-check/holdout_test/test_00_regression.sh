#!/bin/bash
# 回帰: スキャンはリポジトリを一切書き換えない（読み取り専用）こと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

mk_repo
put_line "notes/email.md" "$LN_EMAIL" "contact: $FAKE_EMAIL"
put_line "notes/phone.md" "$LN_PHONE" "tel: $FAKE_PHONE"

BEFORE_STATUS=$(git -C "$REPO" status --porcelain)
BEFORE_HASH=$(cd "$REPO" && find . -path ./.git -prune -o -type f -print | sort | xargs shasum | shasum)

run_scan
assert_exit0

AFTER_STATUS=$(git -C "$REPO" status --porcelain)
AFTER_HASH=$(cd "$REPO" && find . -path ./.git -prune -o -type f -print | sort | xargs shasum | shasum)

[[ "$BEFORE_STATUS" == "$AFTER_STATUS" ]] || fail "スキャンが git の状態を変えた"
[[ "$BEFORE_HASH" == "$AFTER_HASH" ]] || fail "スキャンがファイルを書き換えた/追加した"

echo "PASS"
