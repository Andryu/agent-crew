#!/bin/bash
# 12-rule-candidates: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 86a481146d85c382fc1c4ffe72a856f1eda9997b \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
