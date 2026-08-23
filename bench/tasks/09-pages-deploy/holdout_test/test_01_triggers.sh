#!/bin/bash
# push トリガーの対象ブランチに両方が入っていること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check triggers

echo "PASS"
