#!/bin/bash
# 09-pages-deploy: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup dad13b93373804513e935fde5f933b0e741580e1 \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
