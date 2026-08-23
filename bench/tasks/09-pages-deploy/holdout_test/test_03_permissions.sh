#!/bin/bash
# Pages デプロイに必要な権限が与えられていること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check permissions

echo "PASS"
