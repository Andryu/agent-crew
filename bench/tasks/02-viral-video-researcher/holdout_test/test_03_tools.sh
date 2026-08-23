#!/bin/bash
# 調査用の道具はあり、編集・実行系の道具は含まれないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check tools

echo "PASS"
