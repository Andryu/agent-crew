#!/bin/bash
# bench/run_task.sh — 1タスクの実行フロー
#
# 使い方:
#   run_task.sh <task-dir>                      # setup + prompt 表示（解答フェーズへ）
#   run_task.sh <task-dir> --score              # 採点（解答後に実行）
#   run_task.sh <task-dir> --work <dir>         # 作業ディレクトリ指定
#                                                 (default: /tmp/bench-work/<task名>)
#   run_task.sh <task-dir> --seed <n>           # 採点シード固定（再現用）
#   run_task.sh <task-dir> --score --json <f>   # 結果JSONも書き出す
#
# 流れ: setup（親SHAスナップショット展開）→ prompt を表示 →（手動/ハーネスが
# 作業ディレクトリで解く）→ --score で holdout 採点。
set -euo pipefail

BENCH_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

usage() {
  sed -n '2,15p' "${BASH_SOURCE[0]}" >&2
  exit 1
}

TASK_DIR="${1:-}"
[[ -n "$TASK_DIR" && "$TASK_DIR" != -* ]] || usage
shift
TASK_DIR=$(cd "$TASK_DIR" && pwd)
TASK_NAME=$(basename "$TASK_DIR")

# v4.1: split: hidden のタスクは実験終了後の最終評価でのみ実行する（事故防止）
if [[ -f "$BENCH_ROOT/lib/select.sh" ]]; then
  # shellcheck source=lib/select.sh
  BENCH_ROOT="$BENCH_ROOT" source "$BENCH_ROOT/lib/select.sh"
  bench_assert_not_hidden "$TASK_DIR" || exit 3
fi

MODE=setup
WORK_DIR="/tmp/bench-work/$TASK_NAME"
SEED=""
JSON_OUT=""
VERBOSE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --score)   MODE=score; shift ;;
    --work)    WORK_DIR="$2"; shift 2 ;;
    --seed)    SEED="$2"; shift 2 ;;
    --json)    JSON_OUT="$2"; shift 2 ;;
    --verbose) VERBOSE=1; shift ;;
    *) usage ;;
  esac
done

if [[ "$MODE" == "setup" ]]; then
  bash "$TASK_DIR/setup.sh" "$WORK_DIR"
  echo
  echo "================ PROMPT ($TASK_NAME) ================"
  cat "$TASK_DIR/prompt.md"
  echo "====================================================="
  echo
  echo "次の手順:"
  echo "  1. $WORK_DIR で上記タスクを解く（手動またはハーネス）"
  echo "  2. 採点: $BENCH_ROOT/run_task.sh $TASK_DIR --score --work $WORK_DIR"
else
  ARGS=(--task "$TASK_DIR" --work "$WORK_DIR")
  [[ -n "$SEED" ]] && ARGS+=(--seed "$SEED")
  [[ -n "$JSON_OUT" ]] && ARGS+=(--json "$JSON_OUT")
  [[ -n "$VERBOSE" ]] && ARGS+=(--verbose)
  exec python3 "$BENCH_ROOT/score.py" "${ARGS[@]}"
fi
