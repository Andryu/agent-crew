#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物・固定値）:
#   未コミット差分のあるリポジトリのキューで done すると stderr に警告が出るか。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
UV="${BENCH_UV:-$HOME/.local/bin/uv}"
[[ -x "$UV" ]] || UV=$(command -v uv)

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
R="$TMP/repo"
mkdir -p "$R/.claude"
git -C "$R" init -q
git -C "$R" config user.email smoke@example.invalid
git -C "$R" config user.name smoke
printf '.claude/\n' > "$R/.gitignore"
printf 'v1\n' > "$R/a.txt"
git -C "$R" add -A && git -C "$R" commit -qm init
cat > "$R/.claude/_queue.json" <<'EOF'
{"sprint":"smoke","tasks":[{"slug":"smoke-task","title":"T","status":"IN_PROGRESS",
"assigned_to":"Riku","complexity":"S","risk_level":"low","parallel_group":null,
"depends_on":[],"qa_mode":null,"created_at":"2026-01-01","updated_at":"2026-01-01",
"notes":"","retry_count":0,"qa_result":null,"summary":null,"events":[]}]}
EOF
printf 'v2\n' > "$R/a.txt"

ERR="$TMP/err.txt"
( cd "$R" && QUEUE_FILE="$R/.claude/_queue.json" \
   "$UV" run --no-project --script "$WORK/scripts/queue.py" done smoke-task Riku 完了 ) \
  > "$TMP/out.txt" 2> "$ERR"

grep -q '"status": *"DONE"' "$R/.claude/_queue.json" \
  || { echo "NG: DONE になっていない" >&2; exit 1; }
[[ -s "$ERR" ]] || { echo "NG: 未コミット差分があるのに警告が出ていない" >&2; exit 1; }

echo "visible smoke: OK"
