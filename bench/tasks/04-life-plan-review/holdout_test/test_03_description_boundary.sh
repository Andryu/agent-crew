#!/bin/bash
# description に初回作成は既存スキルの担当である旨があること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check description_boundary

echo "PASS"
