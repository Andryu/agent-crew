#!/bin/bash
# 00-queue-done-issue-close: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 4efcf85ed6297d7ca2243da6bd3104aed68272c2 \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
