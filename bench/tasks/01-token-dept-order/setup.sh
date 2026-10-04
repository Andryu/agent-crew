#!/bin/bash
# 01-token-dept-order: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 2564a1d4010dda3a1539d7d08a1430814e1235c1 \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
