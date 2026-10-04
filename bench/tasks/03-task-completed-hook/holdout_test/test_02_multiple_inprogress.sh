#!/bin/bash
# IN_PROGRESS 複数: 最初の1件だけがシグナルになること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_queue "IN_PROGRESS" "IN_PROGRESS"

run_hook || fail "フックが非ゼロで終了した"

[[ "$(signal_count)" == "1" ]] || fail "1行だけ追記されるべきところ $(signal_count) 行"
LINE=$(tail -1 "$SIGNALS_FILE")
[[ "$(jq -r '.slug' <<< "$LINE")" == "$SLUG_A" ]] || fail "最初の IN_PROGRESS タスクが選ばれていない"

echo "PASS"
