#!/bin/bash
# name がファイル名と一致し、既存と同じ置き場所にあること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check name

echo "PASS"
