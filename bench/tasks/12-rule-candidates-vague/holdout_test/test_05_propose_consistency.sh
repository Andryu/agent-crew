#!/bin/bash
# propose-lesson-rules.sh --dry-run の提案集合が list-rule-candidates と完全一致すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_combo_lessons

# propose 実行用の cwd（origin リモート + .claude/agents を持つ）
PROP_DIR="$BENCH_TMP/prop-repo"
mkdir -p "$PROP_DIR/.claude/agents"
git -C "$PROP_DIR" init -q
git -C "$PROP_DIR" remote add origin "$OWN_SSH"
for f in pm.md engineer-go.md qa.md architect.md; do
  printf '# %s\n' "$f" > "$PROP_DIR/.claude/agents/$f"
done

WANT=$(
  cd "$PROP_DIR" &&
  env LESSONS_FILE="$LESSONS_FILE" LOCK_FILE="$LOCK_FILE" \
    bash "$BENCH_WORK_DIR/scripts/lessons.sh" list-rule-candidates \
      --min-priority "$MINP" | jq -r '.id' | sort
) || fail "list-rule-candidates の実行が失敗した"
[[ -n "$WANT" ]] || fail "前提: 抽出結果が空"

OUT=$(
  cd "$PROP_DIR" &&
  env LESSONS_FILE="$LESSONS_FILE" LOCK_FILE="$LOCK_FILE" \
    bash "$BENCH_WORK_DIR/scripts/propose-lesson-rules.sh" \
      --dry-run --min-priority "$MINP"
) || fail "propose-lesson-rules.sh --dry-run が失敗した"

GOT=$(grep '^### ' <<< "$OUT" | awk '{print $2}' | sort)

[[ "$GOT" == "$WANT" ]] || fail "propose の提案集合が list-rule-candidates と一致しない
--- list-rule-candidates ---
$WANT
--- propose --dry-run ---
$GOT"

# 信頼境界で落ちた外部由来教訓が提案に混ざっていないこと
if grep -q "^### $ID_EXT\$" <<< "$OUT"; then
  fail "信頼境界で除外されるべき教訓が提案されている"
fi

echo "PASS"
