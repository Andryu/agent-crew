#!/bin/bash
# 回帰: 既存スキル life-planner のファイルが1つも変わっていないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check regression

echo "PASS"
