#!/bin/bash
# 07-lessons-to-vault: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup c97fcf1b61019be080493bb1ac65e35419bb3524 \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
