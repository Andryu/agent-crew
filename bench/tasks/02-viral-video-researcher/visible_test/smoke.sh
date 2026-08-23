#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物）:
#   追加したエージェント定義に frontmatter があり、name がファイル名と一致するか。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
F="$WORK/.claude/agents/viral-video-researcher.md"

[[ -f "$F" ]] || { echo "NG: $F が無い" >&2; exit 1; }
head -1 "$F" | grep -q '^---$' || { echo "NG: 先頭が frontmatter でない" >&2; exit 1; }
grep -qE '^name:[[:space:]]*viral-video-researcher[[:space:]]*$' "$F" \
  || { echo "NG: name がファイル名と一致しない" >&2; exit 1; }
grep -qE '^(description|tools|model):' "$F" \
  || { echo "NG: frontmatter の項目が足りない" >&2; exit 1; }

echo "visible smoke: OK"
