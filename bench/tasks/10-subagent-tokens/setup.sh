#!/bin/bash
# 10-subagent-tokens: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 8961c6af98e9a5593ebf0e2684cd49816ca4c2ff \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
