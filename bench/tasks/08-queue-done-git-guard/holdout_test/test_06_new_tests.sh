#!/bin/bash
# 追加したテストが実在し、実行して通ること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

ROOT=$(git -C "$BENCH_WORK_DIR" rev-list --max-parents=0 HEAD | tail -1)
[[ -n "$ROOT" ]] || fail "初期コミットが見つからない"

BASE_LIST="$BENCH_TMP/base_tests.txt"
CUR_LIST="$BENCH_TMP/cur_tests.txt"
git -C "$BENCH_WORK_DIR" ls-tree -r --name-only "$ROOT" tests/ | grep -E '\.py$' | sort > "$BASE_LIST" || true
( cd "$BENCH_WORK_DIR" && find tests -name 'test_*.py' -type f | sort ) > "$CUR_LIST"

NEW_FILES=$(comm -13 "$BASE_LIST" "$CUR_LIST")
[[ -n "$NEW_FILES" ]] || fail "tests/ に新しいテストが追加されていない"

# 追加テストを実行して通ること（1件以上収集されること）
LOG="$BENCH_TMP/newtests.log"
set -- $NEW_FILES
if ! ( cd "$BENCH_WORK_DIR" && "$UV" run --no-project --python 3.12 --with pytest \
        pytest -q -p no:cacheprovider "$@" ) > "$LOG" 2>&1; then
  fail "追加されたテストが通らない
$(tail -40 "$LOG")"
fi
grep -qE '[0-9]+ passed' "$LOG" || fail "追加されたテストが1件も実行されていない
$(tail -20 "$LOG")"

echo "PASS"
