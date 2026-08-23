#!/bin/bash
# SKILL.md 本文が手順として成立していること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check body

echo "PASS"
