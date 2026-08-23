#!/bin/bash
# frontmatter の項目構成が既存エージェント定義と同一であること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check schema

echo "PASS"
