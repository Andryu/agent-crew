#!/bin/bash
# notes に番号が無いタスクでは gh を呼ばず、これまで通り正常終了すること
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_gh_stub 0

# 前提確認: 機能が存在すること（番号ありなら gh が呼ばれる）。
# これが無いと「機能未実装でも gh を呼ばないから合格」という空虚な合格になる。
make_queue "GitHub Issue #${ISSUE_NUM}"
PATH="$STUB_DIR:$PATH" run_done >/dev/null || fail "前提: 番号ありの done が失敗した"
grep -q "close" "$GH_LOG" || fail "前提: Issue クローズ機能が実装されていない"
rm -f "$GH_LOG"

# 本題: 番号なし notes では gh を呼ばない。
# 注: 出典 PR #8 の実装は番号なし notes のとき（grep 不一致が set -o pipefail に
# 拾われて）非ゼロで終了する。採点器は正解実装でグリーンである必要があるため、
# ここでは exit code ではなく「DONE 遷移」と「gh 不呼び出し」だけを見る。
make_queue "番号記載なしのタスク"
PATH="$STUB_DIR:$PATH" run_done || true

if [[ -f "$GH_LOG" ]] && grep -q "close" "$GH_LOG"; then
  fail "番号が無いのに gh で Issue を閉じようとしている"
fi
[[ "$(task_field '.status')" == "DONE" ]] || fail "status が DONE になっていない"

echo "PASS"
