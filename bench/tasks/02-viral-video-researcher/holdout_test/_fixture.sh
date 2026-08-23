#!/bin/bash
# 02 共通 fixture: python 製チェッカーの呼び出しヘルパー
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

PYBIN="${BENCH_PYTHON:-python3}"
command -v "$PYBIN" >/dev/null 2>&1 || fail "python3 が見つからない"

run_check() {
  "$PYBIN" "$BENCH_TASK_DIR/holdout_test/_check.py" "$1" || fail "check '$1' が失敗"
}
