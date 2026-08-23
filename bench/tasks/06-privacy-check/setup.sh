#!/bin/bash
# 06-privacy-check: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 736b325821395ad5a63a1720b36b2c45e28bb562 \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
