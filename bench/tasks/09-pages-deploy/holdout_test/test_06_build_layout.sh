#!/bin/bash
# ビルド手順を実行すると所定の配置ができあがること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check build_layout

echo "PASS"
