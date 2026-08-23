#!/bin/bash
# スキルのファイルに個人情報が書かれていないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check no_pii

echo "PASS"
