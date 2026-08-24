#!/bin/bash
# 05-lessons-set-status: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup e2bdf9b7e19f39571666632cbe74427de86f00cb \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
