#!/bin/bash
# キューが git 管理外にあっても done は成功し、警告も出さないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# 前提確認（空虚な合格の防止）: git 管理下の汚れたリポジトリでは警告が出る
T="$BENCH_TMP/t-guarded"
mk_target_repo "$T"; make_dirty "$T"
run_done "$T" "$T/.claude/_queue.json"
assert_done_ok "$T/.claude/_queue.json"
assert_warned

# 本題: git 管理外のキュー（CWD は汚れた別リポジトリ）
DECOY_DIRTY="$BENCH_TMP/decoy-dirty2"
mk_decoy_repo "$DECOY_DIRTY" 1
PLAIN="$BENCH_TMP/plain"
rm -rf "$PLAIN"; mkdir -p "$PLAIN/.claude"
write_queue "$PLAIN/.claude/_queue.json"

run_done "$DECOY_DIRTY" "$PLAIN/.claude/_queue.json"
assert_done_ok "$PLAIN/.claude/_queue.json"
assert_not_warned

echo "PASS"
