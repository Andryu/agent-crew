#!/bin/bash
# 同時実行を束ねる設定があること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check concurrency

echo "PASS"
