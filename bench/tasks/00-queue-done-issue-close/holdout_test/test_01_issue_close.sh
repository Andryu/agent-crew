#!/bin/bash
# notes の最初の #番号 だけが gh でクローズされ、コメントに agent と完了メッセージが入ること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_queue "GitHub Issue #${ISSUE_NUM} と #${OTHER_NUM} に関連"
make_gh_stub 0
PATH="$STUB_DIR:$PATH" run_done || fail "done が非ゼロで終了した"

[[ -f "$GH_LOG" ]] || fail "gh が呼ばれていない"
grep -q "close" "$GH_LOG" || fail "gh の呼び出しに close が含まれない"
grep -q "$ISSUE_NUM" "$GH_LOG" || fail "最初の Issue 番号 ($ISSUE_NUM) が gh に渡っていない"
if grep -q "$OTHER_NUM" "$GH_LOG"; then
  fail "2番目の Issue 番号 ($OTHER_NUM) まで閉じようとしている"
fi
grep -q "$AGENT" "$GH_LOG" || fail "コメントにエージェント名が含まれない"
grep -q "$MSG" "$GH_LOG" || fail "コメントに完了メッセージが含まれない"

echo "PASS"
