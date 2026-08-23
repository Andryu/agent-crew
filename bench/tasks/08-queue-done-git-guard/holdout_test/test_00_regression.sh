#!/bin/bash
# 回帰: 既存の queue.py テストがすべて通り、done 本体の動きが変わっていないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

[[ -f "$BENCH_WORK_DIR/tests/test_queue_py.py" ]] || fail "既存テストが見つからない"

if ! ( cd "$BENCH_WORK_DIR" && "$UV" run --no-project --python 3.12 --with pytest \
        pytest -q -p no:cacheprovider tests/test_queue_py.py ) \
        > "$BENCH_TMP/pytest.log" 2>&1; then
  fail "既存の tests/test_queue_py.py が通らない
$(tail -40 "$BENCH_TMP/pytest.log")"
fi

# done 本体（DONE 遷移・終了コード・stdout）が壊れていないこと
TARGET="$BENCH_TMP/target"
mk_target_repo "$TARGET"
run_done "$TARGET" "$TARGET/.claude/_queue.json"
assert_done_ok "$TARGET/.claude/_queue.json"
grep -q "$SLUG" "$OUT" || fail "done の stdout に完了報告が出ていない: $(cat "$OUT")"

echo "PASS"
