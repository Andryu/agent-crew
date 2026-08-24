#!/bin/bash
# add 省略時の status が proposed になること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

run_add || fail "add が非ゼロで終了した"
[[ "$(added_record | jq -r '.status')" == "proposed" ]] \
  || fail "status の既定値が proposed になっていない"

echo "PASS"
