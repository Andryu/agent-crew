#!/bin/bash
# 03 共通 fixture: キュー生成とフック実行ヘルパー
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

SPRINT="sprint-$(( 30 + $(t_rand 1 60) ))"
SLUG_A="hook-task-a-$(t_rand 2 10000)"
SLUG_B="hook-task-b-$(t_rand 3 10000)"
AGENT_A="Agent$(t_rand 4 100)"
TID="toolu_bench_$(t_rand 5 100000)"
QUEUE_FILE="$BENCH_TMP/_queue.json"
SIGNALS_FILE="$BENCH_TMP/_signals.jsonl"
HOOK="$BENCH_WORK_DIR/.claude/hooks/task_completed.sh"

[[ -f "$HOOK" ]] || fail ".claude/hooks/task_completed.sh が作られていない"

# $1: タスクAの status  $2: タスクBの status  [$3: タスクAの slug（省略時 SLUG_A）]
make_queue() {
  local slug_a="${3:-$SLUG_A}"
  jq -n --arg sprint "$SPRINT" \
        --arg sa "$slug_a" --arg sb "$SLUG_B" \
        --arg st_a "$1" --arg st_b "$2" \
        --arg agent_a "$AGENT_A" '{
    sprint: $sprint,
    tasks: [
      {slug: $sa, title: "task A", status: $st_a, assigned_to: $agent_a,
       created_at: "2026-01-01", updated_at: "2026-01-01", notes: "",
       events: [], retry_count: 0, qa_result: null, summary: null},
      {slug: $sb, title: "task B", status: $st_b, assigned_to: "Sora",
       created_at: "2026-01-01", updated_at: "2026-01-01", notes: "",
       events: [], retry_count: 0, qa_result: null, summary: null}
    ]
  }' > "$QUEUE_FILE"
}

run_hook() {
  (
    cd "$BENCH_WORK_DIR" &&
    env QUEUE_FILE="$QUEUE_FILE" SIGNALS_FILE="$SIGNALS_FILE" \
        CLAUDE_TOOL_USE_ID="$TID" \
      bash "$HOOK"
  )
}

signal_count() {
  if [[ -f "$SIGNALS_FILE" ]]; then
    wc -l < "$SIGNALS_FILE" | tr -d ' '
  else
    echo 0
  fi
}
