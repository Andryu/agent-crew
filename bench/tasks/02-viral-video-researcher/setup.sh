#!/bin/bash
# 02-viral-video-researcher: 親SHA時点のスナップショットを作業ディレクトリに展開する
set -euo pipefail
TASK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$TASK_DIR/../../lib/common.sh"
bench_setup 5c971e716bc8ac65ff5b93a183adcfe41b20cd23 \
  "${1:?usage: setup.sh <work_dir>}" "$TASK_DIR"
