#!/bin/bash
# キューファイル不在: 何も追記せず exit 0 で終わること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

QUEUE_FILE="$BENCH_TMP/no-such-queue.json"  # 作らない

run_hook || fail "キューファイルが無いときに非ゼロで終了した"

[[ "$(signal_count)" == "0" ]] || fail "キューファイルが無いのにシグナルが追記された"

echo "PASS"
