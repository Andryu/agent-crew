#!/bin/bash
# 公開されるダッシュボードからデモ版への導線があること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check demo_link

echo "PASS"
