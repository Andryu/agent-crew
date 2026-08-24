#!/bin/bash
# sprint フィルタ: 既定の MIN_SPRINT=24 では sprint-23 は転記されず、24以降は転記される
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_lessons
run_vault || fail "スクリプトが非ゼロで終了した"

[[ ! -e "$VAULT_DIR/inbox/agent-crew-lessons-sprint-23.md" ]] \
  || fail "sprint-23 が転記されている（MIN_SPRINT 既定値で除外されるべき）"
[[ -f "$VAULT_DIR/inbox/agent-crew-lessons-sprint-24.md" ]] \
  || fail "sprint-24 が転記されていない"
HI_OUT="$VAULT_DIR/inbox/agent-crew-lessons-${HI_SPRINT}.md"
[[ -f "$HI_OUT" ]] || fail "$HI_SPRINT が転記されていない"
grep -Fq "$ID_HI" "$HI_OUT" || fail "$HI_SPRINT の教訓 id が入っていない"

echo "PASS"
