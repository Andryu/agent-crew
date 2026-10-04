#!/bin/bash
# gh コマンドが無い環境でも done が正常終了すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# 前提確認: 機能が存在すること（gh があれば呼ばれる）
make_gh_stub 0
make_queue "GitHub Issue #${ISSUE_NUM}"
PATH="$STUB_DIR:$PATH" run_done >/dev/null || fail "前提: gh ありの done が失敗した"
grep -q "close" "$GH_LOG" || fail "前提: Issue クローズ機能が実装されていない"

# 本題: gh が無い環境でも done は正常終了する
make_queue "GitHub Issue #${ISSUE_NUM}"
FARM=$(make_restricted_path gh)

(
  cd "$BENCH_WORK_DIR" &&
  env PATH="$FARM" QUEUE_FILE="$QUEUE_FILE" QUEUE_LOCK="$QUEUE_LOCK" \
    /bin/bash scripts/queue.sh done "$SLUG" "$AGENT" "$MSG"
) || fail "gh が無い環境で done が非ゼロで終了した"

[[ "$(task_field '.status')" == "DONE" ]] || fail "status が DONE になっていない"

echo "PASS"
