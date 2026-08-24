#!/bin/bash
# jq 不在: exit 0 で終わり、何も追記しないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_queue "IN_PROGRESS" "DONE"
FARM=$(make_restricted_path jq)

(
  cd "$BENCH_WORK_DIR" &&
  env PATH="$FARM" QUEUE_FILE="$QUEUE_FILE" SIGNALS_FILE="$SIGNALS_FILE" \
      CLAUDE_TOOL_USE_ID="$TID" \
    /bin/bash "$HOOK"
) || fail "jq が無い環境で非ゼロで終了した"

[[ "$(signal_count)" == "0" ]] || fail "jq が無いのにシグナルが追記された"

echo "PASS"
