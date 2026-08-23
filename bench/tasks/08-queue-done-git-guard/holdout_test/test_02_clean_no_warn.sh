#!/bin/bash
# クリーンな作業ツリーでは警告を出さないこと（前提: 汚れていれば警告が出る）
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# 前提確認（空虚な合格の防止）: 汚れているときは警告が出る
TARGET="$BENCH_TMP/target-dirty"
mk_target_repo "$TARGET"
make_dirty "$TARGET"
run_done "$TARGET" "$TARGET/.claude/_queue.json"
assert_done_ok "$TARGET/.claude/_queue.json"
assert_warned

# 本題: クリーンなら stderr は空
TARGET2="$BENCH_TMP/target-clean"
mk_target_repo "$TARGET2"
run_done "$TARGET2" "$TARGET2/.claude/_queue.json"
assert_done_ok "$TARGET2/.claude/_queue.json"
assert_not_warned

echo "PASS"
