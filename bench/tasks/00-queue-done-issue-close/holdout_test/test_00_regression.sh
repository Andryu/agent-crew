#!/bin/bash
# 回帰: done の既存の動き（DONE遷移・summary更新・events追記）が壊れていないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_queue "GitHub Issue #${ISSUE_NUM}"
make_gh_stub 0
PATH="$STUB_DIR:$PATH" run_done || fail "done が非ゼロで終了した"

[[ "$(task_field '.status')" == "DONE" ]] || fail "status が DONE になっていない"
[[ "$(task_field '.summary')" == "$MSG" ]] || fail "summary が完了メッセージになっていない"
[[ "$(task_field '.events | last | .action')" == "done" ]] || fail "events に done が追記されていない"
[[ "$(task_field '.events | last | .agent')" == "$AGENT" ]] || fail "events の agent が違う"

echo "PASS"
