#!/bin/bash
# IN_PROGRESS 1件: 正しいキー/値の JSON が1行だけ追記され、既存行は保たれること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_queue "IN_PROGRESS" "DONE"
SEED_LINE='{"ts":"2026-01-01T00:00:00+0000","event":"bench_seed"}'
printf '%s\n' "$SEED_LINE" > "$SIGNALS_FILE"

run_hook || fail "フックが非ゼロで終了した"

[[ "$(signal_count)" == "2" ]] || fail "追記された行数が1行ではない（計 $(signal_count) 行）"
[[ "$(head -1 "$SIGNALS_FILE")" == "$SEED_LINE" ]] || fail "既存の行が書き換えられた"

LINE=$(tail -1 "$SIGNALS_FILE")
jq -e . >/dev/null <<< "$LINE" || fail "追記行が JSON として不正: $LINE"
[[ "$(jq -r '.slug' <<< "$LINE")" == "$SLUG_A" ]] || fail "slug が違う"
[[ "$(jq -r '.agent' <<< "$LINE")" == "$AGENT_A" ]] || fail "agent が assigned_to になっていない"
[[ "$(jq -r '.sprint' <<< "$LINE")" == "$SPRINT" ]] || fail "sprint が違う"
[[ "$(jq -r '.event' <<< "$LINE")" == "task_completed" ]] || fail "event が task_completed でない"
[[ "$(jq -r '.tool_use_id' <<< "$LINE")" == "$TID" ]] || fail "tool_use_id が CLAUDE_TOOL_USE_ID になっていない"
jq -e '.ts | strings | length > 0' >/dev/null <<< "$LINE" || fail "ts が入っていない"

echo "PASS"
