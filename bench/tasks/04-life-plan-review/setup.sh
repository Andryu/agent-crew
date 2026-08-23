#!/bin/bash
# 04-life-plan-review: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 5463bd38116fd1550567313610ff3b49e5f802d9 \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
