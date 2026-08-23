#!/bin/bash
# SKILL.md の name がディレクトリ名と一致すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check name

echo "PASS"
