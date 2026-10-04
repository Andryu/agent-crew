#!/bin/bash
# 13-false-lead-debug: 合成 fixture を新規リポジトリとして work_dir に展開する
# （source_pr が無い adversarial タスクのため bench_setup の SHA スナップショット方式は使わない）
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORK="${1:?usage: setup.sh <work_dir>}"

if [[ -e "$WORK" ]]; then
  echo "ERROR: work dir already exists: $WORK" >&2
  exit 1
fi
mkdir -p "$WORK"

cp "$TASK_DIR/fixture/report.py" "$WORK/report.py"
# 固定シード・小さい件数・重複なし: 同梱データだけを触っても症状が再現しない構成
python3 "$TASK_DIR/fixture/gen_entries.py" 42 40 0 > "$WORK/entries.jsonl"

git -C "$WORK" init --quiet
git -C "$WORK" add -A
git -C "$WORK" -c user.name=bench -c user.email=bench@example.com \
  commit --quiet -m "bench: initial snapshot"

cp "$TASK_DIR/prompt.md" "$WORK/TASK.md"
if [[ -d "$TASK_DIR/visible_test" ]]; then
  cp -R "$TASK_DIR/visible_test" "$WORK/visible_test"
fi

echo "OK: setup done"
echo "  work dir : $WORK"
echo "  task     : $WORK/TASK.md"
