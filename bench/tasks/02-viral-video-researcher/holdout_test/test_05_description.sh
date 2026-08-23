#!/bin/bash
# description に依頼例・呼び名・対象領域が含まれること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check description

echo "PASS"
