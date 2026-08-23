#!/bin/bash
# 08-queue-done-git-guard: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 6ce4a804939345d6dbee6df9b48efa4357321507 \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
