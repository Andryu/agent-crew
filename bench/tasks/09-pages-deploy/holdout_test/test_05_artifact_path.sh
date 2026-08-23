#!/bin/bash
# アップロード対象のパスが _site であること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check artifact_path

echo "PASS"
