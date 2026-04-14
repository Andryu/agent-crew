#!/bin/bash
# queue.sh — agent-crew タスクキュー操作ヘルパー
#
# エージェントが _queue.json を直接編集せず、このスクリプトを呼び出すことで
# アトミック更新・schema検証・履歴追跡を保証する。
#
# 使い方:
#   queue.sh start <slug>                           # タスクを IN_PROGRESS へ
#   queue.sh done <slug> <agent> "<summary>"        # タスクを DONE へ + events追記
#   queue.sh handoff <slug> <next-agent>            # 次のタスクを READY_FOR_<agent> へ解放
#   queue.sh qa <slug> <APPROVED|CHANGES_REQUESTED> "<summary>"  # qa_result を記録
#   queue.sh block <slug> <agent> "<reason>"        # BLOCKED に遷移
#   queue.sh retry <slug>                           # retry_count++ し READY_FOR_RIKU へ戻す
#   queue.sh show [<slug>]                          # 状態を表示
#   queue.sh next                                   # 次に実行可能な READY_FOR_* タスク1件
#
# 環境変数:
#   QUEUE_FILE   キューファイルパス (default: .claude/_queue.json)
#   QUEUE_LOCK   ロックディレクトリ (default: .claude/.queue.lock)
#   MAX_RETRY    リトライ上限 (default: 3)

set -euo pipefail

QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"
QUEUE_LOCK="${QUEUE_LOCK:-.claude/.queue.lock}"
MAX_RETRY="${MAX_RETRY:-3}"

# ---------- ロック（mkdirはPOSIXでアトミック） ----------
acquire_lock() {
  local tries=0
  while ! mkdir "$QUEUE_LOCK" 2>/dev/null; do
    tries=$((tries + 1))
    if [[ $tries -gt 50 ]]; then
      echo "ERROR: failed to acquire lock $QUEUE_LOCK after 5s" >&2
      exit 2
    fi
    sleep 0.1
  done
  trap 'rmdir "$QUEUE_LOCK" 2>/dev/null || true' EXIT INT TERM
}

release_lock() {
  rmdir "$QUEUE_LOCK" 2>/dev/null || true
  trap - EXIT INT TERM
}

# ---------- 共通ヘルパー ----------
require_queue() {
  if [[ ! -f "$QUEUE_FILE" ]]; then
    echo "ERROR: queue file not found: $QUEUE_FILE" >&2
    exit 3
  fi
  if ! jq empty "$QUEUE_FILE" 2>/dev/null; then
    echo "ERROR: queue file is not valid JSON: $QUEUE_FILE" >&2
    exit 4
  fi
}

today() { date +%Y-%m-%d; }
now_iso() { date +"%Y-%m-%dT%H:%M:%S%z"; }

atomic_write() {
  local new_content="$1"
  local tmp
  tmp=$(mktemp "${QUEUE_FILE}.XXXXXX")
  printf '%s\n' "$new_content" > "$tmp"
  if ! jq empty "$tmp" 2>/dev/null; then
    echo "ERROR: generated JSON is invalid, aborting write" >&2
    rm -f "$tmp"
    exit 5
  fi
  mv "$tmp" "$QUEUE_FILE"
}

require_slug_exists() {
  local slug=$1
  local found
  found=$(jq -r --arg s "$slug" '.tasks[] | select(.slug == $s) | .slug' "$QUEUE_FILE")
  if [[ -z "$found" ]]; then
    echo "ERROR: slug not found: $slug" >&2
    exit 6
  fi
}

# events 配列が無ければ初期化するためのフィルタ
normalize_events_filter='
  .tasks |= map(
    if has("events") then . else . + {events: []} end
    | if has("retry_count") then . else . + {retry_count: 0} end
    | if has("qa_result") then . else . + {qa_result: null} end
  )
'

append_event() {
  local slug=$1 agent=$2 action=$3 msg=$4
  local ts
  ts=$(now_iso)
  jq --arg s "$slug" --arg a "$agent" --arg act "$action" --arg m "$msg" --arg ts "$ts" \
    "$normalize_events_filter |
     .tasks |= map(
       if .slug == \$s then
         .events += [{ts: \$ts, agent: \$a, action: \$act, msg: \$m}]
       else . end
     )" "$QUEUE_FILE"
}

# ---------- コマンド: start ----------
cmd_start() {
  local slug=${1:?slug required}
  acquire_lock
  require_queue
  require_slug_exists "$slug"
  local updated
  updated=$(jq --arg s "$slug" --arg d "$(today)" \
    "$normalize_events_filter |
     .tasks |= map(
       if .slug == \$s then .status = \"IN_PROGRESS\" | .updated_at = \$d
       else . end
     )" "$QUEUE_FILE")
  updated=$(printf '%s' "$updated" | jq --arg s "$slug" --arg ts "$(now_iso)" \
    '.tasks |= map(
       if .slug == $s then
         .events += [{ts: $ts, agent: (.assigned_to // "system"), action: "start", msg: "着手"}]
       else . end
     )')
  atomic_write "$updated"
  release_lock
  echo "OK: $slug → IN_PROGRESS"
}

# ---------- コマンド: done ----------
cmd_done() {
  local slug=${1:?slug required}
  local agent=${2:?agent required}
  local msg=${3:-"完了"}
  acquire_lock
  require_queue
  require_slug_exists "$slug"
  local updated
  updated=$(jq --arg s "$slug" --arg d "$(today)" --arg a "$agent" --arg m "$msg" --arg ts "$(now_iso)" \
    "$normalize_events_filter |
     .tasks |= map(
       if .slug == \$s then
         .status = \"DONE\"
         | .updated_at = \$d
         | .summary = \$m
         | .events += [{ts: \$ts, agent: \$a, action: \"done\", msg: \$m}]
       else . end
     )" "$QUEUE_FILE")
  atomic_write "$updated"
  release_lock
  echo "OK: $slug → DONE"
}

# ---------- コマンド: handoff ----------
# 次タスクのstatusを READY_FOR_<AGENT大文字> に変更
cmd_handoff() {
  local slug=${1:?slug required}
  local next_agent=${2:?next-agent required}
  local upper
  upper=$(printf '%s' "$next_agent" | tr '[:lower:]' '[:upper:]')
  acquire_lock
  require_queue
  require_slug_exists "$slug"
  local updated
  updated=$(jq --arg s "$slug" --arg st "READY_FOR_$upper" --arg d "$(today)" --arg ts "$(now_iso)" --arg a "$next_agent" \
    "$normalize_events_filter |
     .tasks |= map(
       if .slug == \$s then
         .status = \$st
         | .updated_at = \$d
         | .events += [{ts: \$ts, agent: \$a, action: \"handoff\", msg: (\"next: \" + \$st)}]
       else . end
     )" "$QUEUE_FILE")
  atomic_write "$updated"
  release_lock
  echo "OK: $slug → READY_FOR_$upper"
}

# ---------- コマンド: qa ----------
cmd_qa() {
  local slug=${1:?slug required}
  local result=${2:?result required (APPROVED|CHANGES_REQUESTED)}
  local msg=${3:-""}
  case "$result" in
    APPROVED|CHANGES_REQUESTED) ;;
    *) echo "ERROR: result must be APPROVED or CHANGES_REQUESTED" >&2; exit 7 ;;
  esac
  acquire_lock
  require_queue
  require_slug_exists "$slug"
  local updated
  updated=$(jq --arg s "$slug" --arg r "$result" --arg m "$msg" --arg ts "$(now_iso)" --arg d "$(today)" \
    "$normalize_events_filter |
     .tasks |= map(
       if .slug == \$s then
         .qa_result = \$r
         | .updated_at = \$d
         | .events += [{ts: \$ts, agent: \"Sora\", action: \"qa\", msg: (\$r + \": \" + \$m)}]
       else . end
     )" "$QUEUE_FILE")
  atomic_write "$updated"
  release_lock
  echo "OK: $slug qa_result = $result"
}

# ---------- コマンド: block ----------
cmd_block() {
  local slug=${1:?slug required}
  local agent=${2:?agent required}
  local reason=${3:?reason required}
  acquire_lock
  require_queue
  require_slug_exists "$slug"
  local updated
  updated=$(jq --arg s "$slug" --arg a "$agent" --arg r "$reason" --arg ts "$(now_iso)" --arg d "$(today)" \
    "$normalize_events_filter |
     .tasks |= map(
       if .slug == \$s then
         .status = \"BLOCKED\"
         | .updated_at = \$d
         | .events += [{ts: \$ts, agent: \$a, action: \"block\", msg: \$r}]
       else . end
     )" "$QUEUE_FILE")
  atomic_write "$updated"
  release_lock
  echo "BLOCKED: $slug ($reason)"
}

# ---------- コマンド: retry ----------
# Sora が CHANGES_REQUESTED を返したあと、該当タスクを READY_FOR_RIKU に戻す
cmd_retry() {
  local slug=${1:?slug required}
  acquire_lock
  require_queue
  require_slug_exists "$slug"
  local current_retry
  current_retry=$(jq -r --arg s "$slug" '.tasks[] | select(.slug == $s) | .retry_count // 0' "$QUEUE_FILE")
  local next_retry=$((current_retry + 1))
  if [[ $next_retry -gt $MAX_RETRY ]]; then
    local updated
    updated=$(jq --arg s "$slug" --arg ts "$(now_iso)" --arg d "$(today)" --arg max "$MAX_RETRY" \
      "$normalize_events_filter |
       .tasks |= map(
         if .slug == \$s then
           .status = \"BLOCKED\"
           | .updated_at = \$d
           | .events += [{ts: \$ts, agent: \"system\", action: \"block\", msg: (\"retry limit exceeded (max=\" + \$max + \")\")}]
         else . end
       )" "$QUEUE_FILE")
    atomic_write "$updated"
    release_lock
    echo "BLOCKED: $slug retry limit exceeded ($MAX_RETRY)"
    exit 8
  fi
  local updated
  updated=$(jq --arg s "$slug" --arg rc "$next_retry" --arg ts "$(now_iso)" --arg d "$(today)" \
    "$normalize_events_filter |
     .tasks |= map(
       if .slug == \$s then
         .status = \"READY_FOR_RIKU\"
         | .retry_count = (\$rc | tonumber)
         | .qa_result = null
         | .updated_at = \$d
         | .events += [{ts: \$ts, agent: \"system\", action: \"retry\", msg: (\"retry \" + \$rc)}]
       else . end
     )" "$QUEUE_FILE")
  atomic_write "$updated"
  release_lock
  echo "OK: $slug retry $next_retry/$MAX_RETRY → READY_FOR_RIKU"
}

# ---------- コマンド: show ----------
cmd_show() {
  require_queue
  local slug=${1:-}
  if [[ -n "$slug" ]]; then
    jq --arg s "$slug" '.tasks[] | select(.slug == $s)' "$QUEUE_FILE"
  else
    jq '.tasks | map({slug, status, assigned_to, qa_result: (.qa_result // null), retry_count: (.retry_count // 0)})' "$QUEUE_FILE"
  fi
}

# ---------- コマンド: next ----------
# 次に着手可能な READY_FOR_* タスクを1件返す
cmd_next() {
  require_queue
  jq -r '
    .tasks[]
    | select(.status | startswith("READY_FOR_"))
    | .slug + "|" + (.status | sub("READY_FOR_"; "") | ascii_downcase) + "|" + .title
  ' "$QUEUE_FILE" | head -1
}

# ---------- ディスパッチ ----------
cmd=${1:-}
shift || true
case "$cmd" in
  start)   cmd_start "$@" ;;
  done)    cmd_done "$@" ;;
  handoff) cmd_handoff "$@" ;;
  qa)      cmd_qa "$@" ;;
  block)   cmd_block "$@" ;;
  retry)   cmd_retry "$@" ;;
  show)    cmd_show "$@" ;;
  next)    cmd_next "$@" ;;
  ""|help|-h|--help)
    sed -n '2,25p' "$0"
    ;;
  *)
    echo "ERROR: unknown command: $cmd" >&2
    exit 1
    ;;
esac
