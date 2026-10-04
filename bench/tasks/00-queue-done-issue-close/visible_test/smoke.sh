#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物・固定値）:
#   notes に #12 があるタスクを done すると gh スタブが呼ばれることを確かめる。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

jq -n '{
  sprint: "sprint-99",
  tasks: [{
    slug: "smoke-task", title: "smoke", status: "IN_PROGRESS",
    assigned_to: "Riku", created_at: "2026-01-01", updated_at: "2026-01-01",
    notes: "GitHub Issue #12", events: [], retry_count: 0,
    qa_result: null, summary: null
  }]
}' > "$TMP/_queue.json"

mkdir -p "$TMP/stub"
cat > "$TMP/stub/gh" <<STUB
#!/bin/bash
printf '%s\n' "\$*" >> "$TMP/gh.log"
exit 0
STUB
chmod +x "$TMP/stub/gh"

(
  cd "$WORK" &&
  PATH="$TMP/stub:$PATH" QUEUE_FILE="$TMP/_queue.json" QUEUE_LOCK="$TMP/.lock" \
    bash scripts/queue.sh done smoke-task Riku "スモーク完了"
)

grep -q "12" "$TMP/gh.log" || { echo "NG: gh に Issue 番号が渡っていない" >&2; exit 1; }
echo "visible smoke: OK"
