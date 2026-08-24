#!/bin/bash
# 03-task-completed-hook: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 26df0f50d400cb92a16bbabe2f40e5d4d03fb98c \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
