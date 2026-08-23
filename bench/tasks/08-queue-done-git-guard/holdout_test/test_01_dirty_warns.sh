#!/bin/bash
# 未コミットの変更があるとき、件数つきの警告が stderr に出て done は成功すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

TARGET="$BENCH_TMP/target"
mk_target_repo "$TARGET"
make_dirty "$TARGET"

run_done "$TARGET" "$TARGET/.claude/_queue.json"
assert_done_ok "$TARGET/.claude/_queue.json"
assert_warned

echo "PASS"
