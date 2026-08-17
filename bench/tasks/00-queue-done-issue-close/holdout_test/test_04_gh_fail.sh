#!/bin/bash
# Issue クローズに失敗しても done 自体は成功扱いのままであること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# 前提確認: 機能が存在すること（gh 成功時は呼ばれる）
make_gh_stub 0
make_queue "GitHub Issue #${ISSUE_NUM}"
PATH="$STUB_DIR:$PATH" run_done >/dev/null || fail "前提: gh 成功時の done が失敗した"
grep -q "close" "$GH_LOG" || fail "前提: Issue クローズ機能が実装されていない"
rm -f "$GH_LOG"

# 本題: gh が失敗しても done 自体は成功のまま
make_queue "GitHub Issue #${ISSUE_NUM}"
make_gh_stub 1  # gh が常に失敗するスタブ
PATH="$STUB_DIR:$PATH" run_done || fail "gh の失敗が done の失敗として伝播している"

[[ "$(task_field '.status')" == "DONE" ]] || fail "status が DONE になっていない"

echo "PASS"
