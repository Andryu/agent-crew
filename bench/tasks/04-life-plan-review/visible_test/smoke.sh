#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物）:
#   SKILL.md が所定の場所にあり、name がディレクトリ名と一致するか。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
D="$WORK/.claude/skills/life-plan-review"

[[ -f "$D/SKILL.md" ]] || { echo "NG: $D/SKILL.md が無い" >&2; exit 1; }
head -1 "$D/SKILL.md" | grep -q '^---$' || { echo "NG: 先頭が frontmatter でない" >&2; exit 1; }
grep -qE '^name:[[:space:]]*life-plan-review[[:space:]]*$' "$D/SKILL.md" \
  || { echo "NG: name がディレクトリ名と一致しない" >&2; exit 1; }
[[ -d "$D/references" ]] || { echo "NG: references/ が無い" >&2; exit 1; }

echo "visible smoke: OK"
