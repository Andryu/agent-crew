#!/bin/bash
# 回帰: 既存 workflow とダッシュボードの元ファイルが壊れていないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check regression

echo "PASS"
