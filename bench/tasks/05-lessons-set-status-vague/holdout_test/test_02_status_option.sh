#!/bin/bash
# add --status で5種類のどれかを指定するとその値が保存されること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

STATUSES=(proposed issue_created implemented verified dismissed)
PICK="${STATUSES[$(t_rand 6 5)]}"

run_add --status "$PICK" || fail "add --status $PICK が非ゼロで終了した"
[[ "$(added_record | jq -r '.status')" == "$PICK" ]] \
  || fail "--status $PICK が保存されていない（実際: $(added_record | jq -r '.status')）"

echo "PASS"
