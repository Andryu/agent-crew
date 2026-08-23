#!/bin/bash
# description に依頼例と対象領域の語がそろっていること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_check description_positive

echo "PASS"
