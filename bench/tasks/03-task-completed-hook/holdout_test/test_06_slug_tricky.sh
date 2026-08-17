#!/bin/bash
# slug に空白・日本語・引用符が含まれても、追記行が正しい JSON であること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

TRICKY_SLUG="sprint 検証 \"引用\" タスク $(t_rand 6 10000)"
make_queue "IN_PROGRESS" "DONE" "$TRICKY_SLUG"

run_hook || fail "フックが非ゼロで終了した"

[[ "$(signal_count)" == "1" ]] || fail "1行だけ追記されるべきところ $(signal_count) 行"
LINE=$(tail -1 "$SIGNALS_FILE")
jq -e . >/dev/null <<< "$LINE" || fail "追記行が JSON として不正: $LINE"
[[ "$(jq -r '.slug' <<< "$LINE")" == "$TRICKY_SLUG" ]] || fail "slug が元の文字列と一致しない"

echo "PASS"
