#!/bin/bash
# 回帰: 既存のエージェント定義が1つも変更・削除されていないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check regression

echo "PASS"
