#!/bin/bash
# git コマンドが使えない環境でも done は成功すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# 前提確認（空虚な合格の防止）: 通常環境では警告が出る
T="$BENCH_TMP/t-withgit"
mk_target_repo "$T"; make_dirty "$T"
run_done "$T" "$T/.claude/_queue.json"
assert_done_ok "$T/.claude/_queue.json"
assert_warned

# 本題: PATH から git を外す
T2="$BENCH_TMP/t-nogit"
mk_target_repo "$T2"; make_dirty "$T2"
FARM=$(make_nogit_path)
run_done "$T2" "$T2/.claude/_queue.json" PATH="$FARM"
assert_done_ok "$T2/.claude/_queue.json"

echo "PASS"
