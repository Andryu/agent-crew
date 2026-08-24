#!/bin/bash
# IN_PROGRESS ゼロ: 何も追記せず exit 0 で終わること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_queue "DONE" "READY_FOR_RIKU"
: > "$SIGNALS_FILE"

run_hook || fail "IN_PROGRESS が無いときに非ゼロで終了した"

[[ "$(signal_count)" == "0" ]] || fail "IN_PROGRESS が無いのにシグナルが追記された"

echo "PASS"
