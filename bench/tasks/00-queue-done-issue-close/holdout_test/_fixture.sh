#!/bin/bash
# 00 共通 fixture: キュー生成・gh スタブ・done 実行ヘルパー
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

ISSUE_NUM=$(( 100 + $(t_rand 1 900) ))     # 3桁
OTHER_NUM=$(( 10000 + $(t_rand 2 9000) ))  # 5桁（3〜4桁の他の値と部分一致しない）
SLUG="bench-task-$(t_rand 3 10000)"
AGENT="Riku"
MSG="bench-done-$(t_rand 4 10000)"
QUEUE_FILE="$BENCH_TMP/_queue.json"
QUEUE_LOCK="$BENCH_TMP/.queue.lock"
GH_LOG="$BENCH_TMP/gh.log"
STUB_DIR="$BENCH_TMP/stub"

# $1: notes 文字列
make_queue() {
  jq -n --arg slug "$SLUG" --arg notes "$1" '{
    sprint: "sprint-99",
    tasks: [{
      slug: $slug, title: "bench task", status: "IN_PROGRESS",
      assigned_to: "Riku", created_at: "2026-01-01", updated_at: "2026-01-01",
      notes: $notes, events: [], retry_count: 0, qa_result: null, summary: null
    }]
  }' > "$QUEUE_FILE"
}

# gh 呼び出しを記録するスタブを作る。$1: スタブの exit code（省略時 0）
make_gh_stub() {
  mkdir -p "$STUB_DIR"
  cat > "$STUB_DIR/gh" <<STUB
#!/bin/bash
printf '%s\n' "\$*" >> "$GH_LOG"
exit ${1:-0}
STUB
  chmod +x "$STUB_DIR/gh"
}

run_done() {
  (
    cd "$BENCH_WORK_DIR" &&
    QUEUE_FILE="$QUEUE_FILE" QUEUE_LOCK="$QUEUE_LOCK" \
      bash scripts/queue.sh done "$SLUG" "$AGENT" "$MSG"
  )
}

task_field() {  # $1: jq フィルタ（タスク1件に対する）
  jq -r --arg s "$SLUG" ".tasks[] | select(.slug == \$s) | $1" "$QUEUE_FILE"
}
