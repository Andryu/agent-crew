#!/bin/bash
# 2ブランチをそれぞれ別の場所に取得していること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check dual_checkout

echo "PASS"
