#!/bin/bash
# しきい値境界: priority_score == MIN_PRIORITY は転記、MIN_PRIORITY-1 は転記しない
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_lessons
run_vault || fail "スクリプトが非ゼロで終了した"

OUT="$VAULT_DIR/inbox/agent-crew-lessons-sprint-24.md"
[[ -f "$OUT" ]] || fail "sprint-24 の出力ファイルが無い: $OUT"
grep -Fq "$ID_BOUND" "$OUT" || fail "しきい値ちょうどの教訓 id が入っていない"
grep -Fq "$DESC_BOUND" "$OUT" || fail "教訓の description が入っていない"
grep -Fq "$ACTION_BOUND" "$OUT" || fail "教訓の action が入っていない"
if grep -Fq "$ID_LOW" "$OUT"; then
  fail "しきい値未満の教訓まで転記されている"
fi

echo "PASS"
