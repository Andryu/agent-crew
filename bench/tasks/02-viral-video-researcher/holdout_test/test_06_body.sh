#!/bin/bash
# 本文に節構成と十分な中身があること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check body

echo "PASS"
