#!/bin/bash
# model が既存定義に存在する値であること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check model

echo "PASS"
