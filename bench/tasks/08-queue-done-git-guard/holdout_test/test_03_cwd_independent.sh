#!/bin/bash
# 判定はキューファイルの位置から解決すること（カレントディレクトリに依存しない）
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

DECOY_CLEAN="$BENCH_TMP/decoy-clean"
DECOY_DIRTY="$BENCH_TMP/decoy-dirty"
OUTSIDE="$BENCH_TMP/outside"
mk_decoy_repo "$DECOY_CLEAN" 0
mk_decoy_repo "$DECOY_DIRTY" 1
rm -rf "$OUTSIDE"; mkdir -p "$OUTSIDE"

# A) 対象が汚れている / CWD はクリーンな別リポジトリ → 警告が出る
T="$BENCH_TMP/t-a"
mk_target_repo "$T"; make_dirty "$T"
run_done "$DECOY_CLEAN" "$T/.claude/_queue.json"
assert_done_ok "$T/.claude/_queue.json"
assert_warned

# B) 対象が汚れている / CWD は git 管理外 → 警告が出る
T="$BENCH_TMP/t-b"
mk_target_repo "$T"; make_dirty "$T"
run_done "$OUTSIDE" "$T/.claude/_queue.json"
assert_done_ok "$T/.claude/_queue.json"
assert_warned

# C) 対象はクリーン / CWD は汚れた別リポジトリ → 警告を出してはいけない
T="$BENCH_TMP/t-c"
mk_target_repo "$T"
run_done "$DECOY_DIRTY" "$T/.claude/_queue.json"
assert_done_ok "$T/.claude/_queue.json"
assert_not_warned

# D) 相対パスでキューを渡しても（CWD が対象リポジトリ内なら）判定は同じ
T="$BENCH_TMP/t-d"
mk_target_repo "$T"; make_dirty "$T"
run_done "$T" ".claude/_queue.json"
assert_done_ok "$T/.claude/_queue.json"
assert_warned

echo "PASS"
