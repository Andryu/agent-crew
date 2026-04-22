#!/bin/bash
# queue.sh — agent-crew タスクキュー操作ヘルパー
#
# エージェントが _queue.json を直接編集せず、このスクリプトを呼び出すことで
# アトミック更新・schema検証・履歴追跡を保証する。
#
# 使い方:
#   queue.sh start <slug>                                        # タスクを IN_PROGRESS へ（depends_on 全 DONE チェックあり）
#   queue.sh done <slug> <agent> "<summary>"                     # タスクを DONE へ + events追記
#   queue.sh handoff <slug> <next-agent>                         # 次のタスクを READY_FOR_<agent> へ解放
#   queue.sh parallel-handoff <slug1>:<agent1> <slug2>:<agent2>  # 複数タスクを単一ロック内で一括ハンドオフ
#   queue.sh qa <slug> <APPROVED|CHANGES_REQUESTED> "<summary>"  # qa_result を記録
#   queue.sh block <slug> <agent> "<reason>"                     # BLOCKED に遷移
#   queue.sh retry <slug>                                        # retry_count++ し READY_FOR_RIKU へ戻す
#   queue.sh show [<slug>]                                       # 状態を表示
#   queue.sh next                                                # 次に実行可能な READY_FOR_* タスク1件
#   queue.sh graph [--save]                                      # Mermaid依存グラフを出力
#   queue.sh retro [--save] [--decisions]                        # リトロスペクティブ集計
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
LOCK_STALE_SECS=30

acquire_lock() {
  local tries=0
  while ! mkdir "$QUEUE_LOCK" 2>/dev/null; do
    # スタールロック検出: mtime が LOCK_STALE_SECS 秒以上古ければ強制削除
    if [[ -d "$QUEUE_LOCK" ]]; then
      local lock_mtime now age
      lock_mtime=$(stat -f %m "$QUEUE_LOCK" 2>/dev/null || stat -c %Y "$QUEUE_LOCK" 2>/dev/null || echo 0)
      now=$(date +%s)
      age=$((now - lock_mtime))
      if [[ $age -ge $LOCK_STALE_SECS ]]; then
        echo "WARN: stale lock detected (${age}s old), removing $QUEUE_LOCK" >&2
        rmdir "$QUEUE_LOCK" 2>/dev/null || true
        continue
      fi
    fi
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
    | if has("complexity") then . else . + {complexity: null} end
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

# ---------- リスクスコア計算（start 時に呼び出す・読み取り専用） ----------
calculate_risk() {
  local slug=$1

  # risk_level・complexity・retry_count を取得
  local task_info
  task_info=$(jq -r --arg s "$slug" '
    .tasks[] | select(.slug == $s) |
    (.risk_level // "low") + "|" + (.complexity // "S") + "|" + ((.retry_count // 0) | tostring)
  ' "$QUEUE_FILE")

  local risk_level complexity retry_count
  risk_level=$(echo "$task_info" | cut -d'|' -f1)
  complexity=$(echo "$task_info" | cut -d'|' -f2)
  retry_count=$(echo "$task_info" | cut -d'|' -f3)

  # risk_level が未設定の場合は complexity から推論
  if [[ "$risk_level" == "low" || -z "$risk_level" ]]; then
    case "$complexity" in
      L) risk_level="high" ;;
      M) risk_level="medium" ;;
      *) risk_level="low" ;;
    esac
  fi

  # 同一エージェントの過去ブロック回数を集計
  local assigned_to agent_block_count
  assigned_to=$(jq -r --arg s "$slug" '.tasks[] | select(.slug == $s) | .assigned_to // "unknown"' "$QUEUE_FILE")
  agent_block_count=$(jq -r --arg agent "$assigned_to" '
    [.tasks[] | select(.assigned_to == $agent) |
      (.events // [])[] | select(.action == "block")] | length
  ' "$QUEUE_FILE")

  # 警告レベルの判定
  local warn_level=""
  local recommend=""

  if [[ "$risk_level" == "high" ]]; then
    warn_level="WARNING: HIGH RISK"
    recommend="オーナーに事前確認してから着手してください"
  elif [[ "$risk_level" == "medium" && "$complexity" == "L" ]]; then
    warn_level="WARNING: HIGH RISK"
    recommend="オーナーに事前確認してから着手してください"
  elif [[ "$risk_level" == "medium" && "$retry_count" -gt 0 ]]; then
    warn_level="NOTICE: ELEVATED"
    recommend="前回リトライが発生しています。設計を再確認してください"
  elif [[ "$risk_level" == "low" && "$complexity" == "L" && "$retry_count" -gt 0 ]]; then
    warn_level="NOTICE: ELEVATED"
    recommend="L タスクでリトライ履歴があります。慎重に進めてください"
  else
    warn_level="INFO: LOW RISK"
    recommend=""
  fi

  # STDERR に出力（正常フローを邪魔しない）
  echo "RISK: $slug — $warn_level" >&2
  echo "  risk_level: $risk_level" >&2
  echo "  complexity: $complexity" >&2
  echo "  retry_count: $retry_count" >&2
  echo "  agent block history: $assigned_to ${agent_block_count}件" >&2
  if [[ -n "$recommend" ]]; then
    echo "  推奨: $recommend" >&2
  fi
}

# ---------- コマンド: start ----------
cmd_start() {
  local slug=${1:?slug required}
  acquire_lock
  require_queue
  require_slug_exists "$slug"

  # 状態ガード: 既に IN_PROGRESS / DONE / BLOCKED なら重複実行を拒否
  local current_status
  current_status=$(jq -r --arg s "$slug" \
    '.tasks[] | select(.slug == $s) | .status' "$QUEUE_FILE")
  case "$current_status" in
    IN_PROGRESS)
      release_lock
      echo "ERROR: $slug is already IN_PROGRESS. 'start' is idempotent-safe; skip if already started." >&2
      exit 11
      ;;
    DONE)
      release_lock
      echo "ERROR: $slug is already DONE. Cannot re-start a completed task." >&2
      exit 12
      ;;
    BLOCKED)
      release_lock
      echo "ERROR: $slug is BLOCKED. Resolve the block before restarting." >&2
      exit 13
      ;;
  esac

  # depends_on の全タスクが DONE かチェック
  local unresolved
  unresolved=$(jq -r --arg s "$slug" '
    .tasks as $all |
    .tasks[] | select(.slug == $s) |
    (.depends_on // [])[] as $dep |
    ($all[] | select(.slug == $dep) | select(.status != "DONE") | .slug)
  ' "$QUEUE_FILE")
  if [[ -n "$unresolved" ]]; then
    release_lock
    echo "ERROR: depends_on not satisfied for $slug. Unresolved: $(printf '%s ' $unresolved)" >&2
    exit 9
  fi

  # complexity バリデーション（S/M/L のいずれかであること）
  local complexity
  complexity=$(jq -r --arg s "$slug" '.tasks[] | select(.slug == $s) | .complexity // "null"' "$QUEUE_FILE")
  case "$complexity" in
    S|M|L) ;;
    *)
      release_lock
      echo "ERROR: complexity must be S, M, or L for $slug (got: $complexity)" >&2
      exit 10
      ;;
  esac

  # リスク予測（読み取り専用・キュー状態を変更しない）
  calculate_risk "$slug"

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

  # notes から GitHub Issue 番号を抽出して自動クローズ
  if command -v gh >/dev/null 2>&1; then
    local issue_num
    issue_num=$(jq -r --arg s "$slug" '.tasks[] | select(.slug == $s) | .notes // ""' "$QUEUE_FILE" \
      | grep -oE '#[0-9]+' | head -1 | tr -d '#')
    if [[ -n "$issue_num" ]]; then
      gh issue close "$issue_num" --comment "✅ ${agent}: ${slug} 完了 — ${msg}" 2>/dev/null && \
        echo "OK: Issue #$issue_num closed" || \
        echo "WARN: Issue #$issue_num close failed (ignored)" >&2
    fi
  fi
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

# ---------- コマンド: parallel-handoff ----------
# 複数タスクを単一ロック取得内で一括ハンドオフ
# 引数: <slug1>:<agent1> <slug2>:<agent2> ...
cmd_parallel_handoff() {
  if [[ $# -eq 0 ]]; then
    echo "ERROR: parallel-handoff requires at least one slug:agent argument" >&2
    exit 1
  fi

  # 引数フォーマット検証: 全て slug:agent 形式であること
  local pair
  for pair in "$@"; do
    if [[ "$pair" != *:* ]]; then
      echo "ERROR: argument must be in slug:agent format, got: $pair" >&2
      exit 1
    fi
  done

  acquire_lock
  require_queue

  local updated
  updated=$(cat "$QUEUE_FILE")

  local ts
  ts=$(now_iso)
  local d
  d=$(today)

  for pair in "$@"; do
    local slug="${pair%%:*}"
    local next_agent="${pair#*:}"
    local upper
    upper=$(printf '%s' "$next_agent" | tr '[:lower:]' '[:upper:]')

    # slug 存在確認（ロック内で直接チェック）
    local found
    found=$(printf '%s' "$updated" | jq -r --arg s "$slug" '.tasks[] | select(.slug == $s) | .slug')
    if [[ -z "$found" ]]; then
      release_lock
      echo "ERROR: slug not found: $slug" >&2
      exit 6
    fi

    updated=$(printf '%s' "$updated" | jq \
      --arg s "$slug" --arg st "READY_FOR_$upper" --arg d "$d" --arg ts "$ts" --arg a "$next_agent" \
      "$normalize_events_filter |
       .tasks |= map(
         if .slug == \$s then
           .status = \$st
           | .updated_at = \$d
           | .events += [{ts: \$ts, agent: \$a, action: \"handoff\", msg: (\"parallel-handoff: \" + \$st)}]
         else . end
       )")
  done

  atomic_write "$updated"
  release_lock

  for pair in "$@"; do
    local slug="${pair%%:*}"
    local next_agent="${pair#*:}"
    local upper
    upper=$(printf '%s' "$next_agent" | tr '[:lower:]' '[:upper:]')
    echo "OK: $slug → READY_FOR_$upper"
  done
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

  # 冪等性ガード: qa_result が既に設定済みなら重複送信を拒否
  local current_qa_result
  current_qa_result=$(jq -r --arg s "$slug" \
    '.tasks[] | select(.slug == $s) | .qa_result // "null"' "$QUEUE_FILE")
  if [[ "$current_qa_result" != "null" ]]; then
    release_lock
    echo "ERROR: $slug already has qa_result=$current_qa_result. Use 'retry' to reset before re-QA." >&2
    exit 14
  fi

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
    jq '.tasks | map({slug, status, assigned_to, complexity: (.complexity // null), qa_result: (.qa_result // null), retry_count: (.retry_count // 0)})' "$QUEUE_FILE"
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

# ---------- コマンド: graph ----------
# _queue.json のタスク依存関係を Mermaid flowchart LR 形式で出力する
# --save フラグで docs/graphs/<sprint>.md に保存する
cmd_graph() {
  require_queue

  local save_flag=false
  local arg
  for arg in "$@"; do
    [[ "$arg" == "--save" ]] && save_flag=true
  done

  local sprint
  sprint=$(jq -r '.sprint // "sprint"' "$QUEUE_FILE")

  # ノード定義を生成
  local node_lines
  node_lines=$(jq -r '.tasks[] |
    .slug as $s |
    (.status |
      if startswith("READY_FOR_") then "ready"
      elif . == "IN_PROGRESS" then "in_progress"
      elif . == "DONE" then "done"
      elif . == "BLOCKED" then "blocked"
      else "todo"
      end
    ) as $cls |
    "  " + $s + "[\"" + $s + "\\n(" + (.assigned_to // "?") + " · " + .status + ")\"]:::" + $cls
  ' "$QUEUE_FILE")

  # エッジ定義を生成
  local edge_lines
  edge_lines=$(jq -r '.tasks[] |
    .slug as $s |
    (.depends_on // [])[] as $dep |
    "  " + $dep + " --> " + $s
  ' "$QUEUE_FILE")

  # Mermaid ブロック出力
  printf '```mermaid\n'
  echo 'flowchart LR'
  echo "$node_lines"
  echo ""
  echo "$edge_lines"
  echo ""
  echo "  classDef done fill:#22c55e,color:#fff"
  echo "  classDef in_progress fill:#f59e0b,color:#fff"
  echo "  classDef blocked fill:#ef4444,color:#fff"
  echo "  classDef ready fill:#3b82f6,color:#fff"
  echo "  classDef todo fill:#e5e7eb,color:#374151"
  printf '```\n'

  if [[ "$save_flag" == "true" ]]; then
    local queue_abs
    queue_abs=$(cd "$(dirname "$QUEUE_FILE")" && pwd)
    local project_root
    project_root=$(dirname "$queue_abs")
    local graphs_dir="${project_root}/docs/graphs"
    mkdir -p "$graphs_dir"
    local out_file="${graphs_dir}/${sprint}.md"
    {
      printf '# %s — Mermaid依存グラフ\n\n' "$sprint"
      printf '```mermaid\n'
      echo 'flowchart LR'
      echo "$node_lines"
      echo ""
      echo "$edge_lines"
      echo ""
      echo "  classDef done fill:#22c55e,color:#fff"
      echo "  classDef in_progress fill:#f59e0b,color:#fff"
      echo "  classDef blocked fill:#ef4444,color:#fff"
      echo "  classDef ready fill:#3b82f6,color:#fff"
      echo "  classDef todo fill:#e5e7eb,color:#374151"
      printf '```\n'
    } > "$out_file"
    echo "OK: graph saved to $out_file" >&2
  fi
}

# ---------- コマンド: retro ----------
# スプリント完了時のメトリクスを集計して STDOUT に出力する
# --save フラグで docs/retro/<sprint>-retro.md に保存する
# --decisions フラグで docs/DECISIONS.md に追記する
cmd_retro() {
  require_queue

  local save_flag=false
  local decisions_flag=false
  local arg
  for arg in "$@"; do
    case "$arg" in
      --save)       save_flag=true ;;
      --decisions)  decisions_flag=true ;;
    esac
  done

  local sprint
  sprint=$(jq -r '.sprint // "sprint"' "$QUEUE_FILE")

  local today_date
  today_date=$(today)

  # ---------- 基本集計 ----------
  local total_tasks done_tasks blocked_tasks total_retry
  total_tasks=$(jq '[.tasks[]] | length' "$QUEUE_FILE")
  done_tasks=$(jq '[.tasks[] | select(.status == "DONE")] | length' "$QUEUE_FILE")
  blocked_tasks=$(jq '[.tasks[] | select(.status == "BLOCKED")] | length' "$QUEUE_FILE")
  total_retry=$(jq '[.tasks[].retry_count // 0] | add // 0' "$QUEUE_FILE")

  # QA差し戻し率
  local qa_total qa_changes qa_rate
  qa_total=$(jq '[.tasks[] | select(.assigned_to == "Sora")] | length' "$QUEUE_FILE")
  qa_changes=$(jq '[.tasks[] | select(.assigned_to == "Sora") | select(.qa_result == "CHANGES_REQUESTED")] | length' "$QUEUE_FILE")
  if [[ "$qa_total" -gt 0 ]]; then
    qa_rate=$(( (qa_changes * 100) / qa_total ))
  else
    qa_rate=0
  fi

  # ブロックされたスラッグ一覧
  local blocked_slugs
  blocked_slugs=$(jq -r '[.tasks[] | select(.status == "BLOCKED") | .slug] | join(", ")' "$QUEUE_FILE")
  [[ -z "$blocked_slugs" ]] && blocked_slugs="なし"

  # ボトルネック: 最もリトライが多かったタスク
  local max_retry_slug max_retry_count
  max_retry_slug=$(jq -r '[.tasks[] | {slug, rc: (.retry_count // 0)}] | max_by(.rc) | .slug' "$QUEUE_FILE")
  max_retry_count=$(jq -r '[.tasks[] | {slug, rc: (.retry_count // 0)}] | max_by(.rc) | .rc' "$QUEUE_FILE")

  # ---------- 実行時間計算ヘルパー ----------
  # ISO8601 タイムスタンプを epoch 秒に変換（macOS/Linux 両対応）
  ts_to_epoch() {
    local ts="$1"
    # +09:00 → +0900 に正規化（macOS date -j は %z でコロンなしを期待）
    local ts_norm
    ts_norm=$(echo "$ts" | sed 's/\([+-][0-9][0-9]\):\([0-9][0-9]\)$/\1\2/')
    # macOS: date -j
    if date -j -f "%Y-%m-%dT%H:%M:%S%z" "$ts_norm" +%s 2>/dev/null; then
      return
    fi
    # Linux fallback
    date -d "$ts" +%s 2>/dev/null || echo 0
  }

  # タスクごとの実行時間（分）を計算
  local task_durations
  task_durations=$(jq -r '.tasks[] |
    .slug + "|" + (.assigned_to // "?") + "|" + (.complexity // "?") + "|" +
    ((.retry_count // 0) | tostring) + "|" + (.qa_result // "-") + "|" +
    ((.events // []) | map(select(.action == "start")) | last | .ts // "") + "|" +
    ((.events // []) | map(select(.action == "done"))  | last | .ts // "")
  ' "$QUEUE_FILE")

  # ---------- タスクテーブルと complexity 集計 ----------
  local task_table=""
  local s_count=0 m_count=0 l_count=0
  local s_total=0 m_total=0 l_total=0
  local longest_slug="" longest_mins=0

  while IFS='|' read -r slug assigned comp rc qr start_ts done_ts; do
    [[ -z "$slug" ]] && continue

    # 実行時間計算
    local dur_mins="-"
    if [[ -n "$start_ts" && -n "$done_ts" ]]; then
      local ep_start ep_done
      ep_start=$(ts_to_epoch "$start_ts")
      ep_done=$(ts_to_epoch "$done_ts")
      if [[ "$ep_start" != "0" && "$ep_done" != "0" && "$ep_done" -ge "$ep_start" ]]; then
        dur_mins=$(( (ep_done - ep_start) / 60 ))
        if [[ "$dur_mins" -gt "$longest_mins" ]]; then
          longest_mins=$dur_mins
          longest_slug=$slug
        fi
      fi
    fi

    # complexity 別集計
    case "$comp" in
      S)
        s_count=$((s_count + 1))
        [[ "$dur_mins" != "-" ]] && s_total=$((s_total + dur_mins))
        ;;
      M)
        m_count=$((m_count + 1))
        [[ "$dur_mins" != "-" ]] && m_total=$((m_total + dur_mins))
        ;;
      L)
        l_count=$((l_count + 1))
        [[ "$dur_mins" != "-" ]] && l_total=$((l_total + dur_mins))
        ;;
    esac

    task_table="${task_table}| ${slug} | ${assigned} | ${comp} | ${dur_mins}分 | ${rc} | ${qr} |\n"
  done <<< "$task_durations"

  # complexity 別平均
  local s_avg="-" m_avg="-" l_avg="-"
  [[ "$s_count" -gt 0 ]] && s_avg=$(( s_total / s_count ))
  [[ "$m_count" -gt 0 ]] && m_avg=$(( m_total / m_count ))
  [[ "$l_count" -gt 0 ]] && l_avg=$(( l_total / l_count ))

  # L の平均が S の平均の10倍を超えるか
  local l_vs_s_ratio=0
  if [[ "$s_avg" != "-" && "$s_avg" -gt 0 && "$l_avg" != "-" ]]; then
    l_vs_s_ratio=$(( l_avg / s_avg ))
  fi

  # ---------- 推奨アクション自動生成 ----------
  local recommendations=""
  if [[ "$qa_rate" -gt 30 ]]; then
    recommendations="${recommendations}- 実装前の設計レビューを強化してください（QA差し戻し率 ${qa_rate}%）\n"
  fi
  if [[ "$blocked_tasks" -gt 2 ]]; then
    recommendations="${recommendations}- 次スプリント計画時にリスクの高いタスクを先頭に置いてください（ブロック ${blocked_tasks}件）\n"
  fi
  if [[ "$l_vs_s_ratio" -gt 10 ]]; then
    recommendations="${recommendations}- L タスクをさらに分割することを検討してください（L平均 ${l_avg}分 / S平均 ${s_avg}分）\n"
  fi
  if [[ "$total_tasks" -gt 0 ]]; then
    local retry_threshold=$(( (total_tasks * 50) / 100 ))
    if [[ "$total_retry" -gt "$retry_threshold" ]]; then
      recommendations="${recommendations}- 受け入れ基準をタスク分解時に明文化してください（総リトライ ${total_retry}回）\n"
    fi
  fi
  [[ -z "$recommendations" ]] && recommendations="- 特記事項なし\n"

  # ---------- DECISIONS.md 用データ ----------
  # アーキテクチャ判断（Alex 担当タスクの summary）
  local arch_decisions
  arch_decisions=$(jq -r '
    [.tasks[] | select(.assigned_to == "Alex" and .summary != null and .summary != "") |
      "- " + .slug + ": " + .summary] | join("\n")
  ' "$QUEUE_FILE")
  [[ -z "$arch_decisions" ]] && arch_decisions="- なし"

  # 失敗パターン（BLOCKED または retry_count > 0）
  local failure_patterns
  failure_patterns=$(jq -r '
    [.tasks[] | select(.status == "BLOCKED" or (.retry_count // 0) > 0) |
      "- " + .slug + " (retry=" + ((.retry_count // 0) | tostring) + "): " +
      ((.events // []) | map(select(.action == "block" or .action == "retry")) | last | .msg // "詳細不明")] |
    join("\n")
  ' "$QUEUE_FILE")
  [[ -z "$failure_patterns" ]] && failure_patterns="- なし"

  # 学び（QA CHANGES_REQUESTED が出たタスクの qa イベントメッセージ）
  local learnings
  learnings=$(jq -r '
    [.tasks[] | select((.events // []) | map(select(.action == "qa" and (.msg | startswith("CHANGES_REQUESTED")))) | length > 0) |
      "- " + .slug + ": " +
      ((.events // []) | map(select(.action == "qa" and (.msg | startswith("CHANGES_REQUESTED")))) | last | .msg // "詳細不明")] |
    join("\n")
  ' "$QUEUE_FILE")
  [[ -z "$learnings" ]] && learnings="- なし"

  # 次スプリントへの推奨（ON_HOLD タスクの notes）
  local on_hold_recs
  on_hold_recs=$(jq -r '
    [.tasks[] | select(.status == "ON_HOLD" and .notes != null and .notes != "") |
      "- " + .slug + ": " + .notes] | join("\n")
  ' "$QUEUE_FILE")
  [[ -z "$on_hold_recs" ]] && on_hold_recs="- なし"

  # ---------- retro 出力本体 ----------
  local retro_body
  retro_body="## スプリント: ${sprint}

### タスク完了サマリー
| タスク | 担当 | complexity | 実行時間 | retry_count | qa_result |
|--------|------|-----------|---------|-------------|-----------|
$(printf '%b' "$task_table")
### 集計
- 完了タスク数: ${done_tasks}
- ブロック発生: ${blocked_tasks}件（${blocked_slugs}）
- 総リトライ回数: ${total_retry}
- QA差し戻し率: ${qa_rate}%（CHANGES_REQUESTED ${qa_changes}件 / QAタスク ${qa_total}件）

### Complexity 精度評価
| complexity | タスク数 | 平均実行時間 |
|-----------|---------|------------|
| S         | ${s_count}       | ${s_avg}分       |
| M         | ${m_count}       | ${m_avg}分       |
| L         | ${l_count}       | ${l_avg}分       |

> 実行時間は start → done イベント間の diff から算出

### ボトルネック
- 最もリトライが多かったタスク: ${max_retry_slug} (${max_retry_count}回)
- 最も長かったタスク: ${longest_slug:-なし} (${longest_mins}分)

### 次スプリントへの推奨アクション
$(printf '%b' "$recommendations")"

  echo "$retro_body"

  # --save: docs/retro/<sprint>-retro.md に保存
  if [[ "$save_flag" == "true" ]]; then
    local queue_abs
    queue_abs=$(cd "$(dirname "$QUEUE_FILE")" && pwd)
    local project_root
    project_root=$(dirname "$queue_abs")
    local retro_dir="${project_root}/docs/retro"
    mkdir -p "$retro_dir"
    local out_file="${retro_dir}/${sprint}-retro.md"
    {
      printf '# リトロスペクティブ — %s\n\n生成日: %s\n\n' "$sprint" "$today_date"
      echo "$retro_body"
    } > "$out_file"
    echo "OK: retro saved to $out_file" >&2
  fi

  # --decisions: docs/DECISIONS.md に追記（同一スプリントの重複追記を防ぐ）
  if [[ "$decisions_flag" == "true" ]]; then
    local queue_abs
    queue_abs=$(cd "$(dirname "$QUEUE_FILE")" && pwd)
    local project_root
    project_root=$(dirname "$queue_abs")
    local decisions_file="${project_root}/docs/DECISIONS.md"

    # 初回作成（ファイルが存在しない場合）
    if [[ ! -f "$decisions_file" ]]; then
      cat > "$decisions_file" << 'DECISIONS_HEADER'
# DECISIONS — agent-crew

スプリント完了時に自動追記される判断・学習・失敗パターンの記録。
次スプリント計画時に Yuki が参照する。

---
DECISIONS_HEADER
    fi

    # 同一スプリントの重複追記を防ぐ
    if grep -q "## ${sprint} —" "$decisions_file" 2>/dev/null; then
      echo "WARN: DECISIONS.md に ${sprint} のエントリが既に存在します。追記をスキップします。" >&2
    else
      {
        echo ""
        echo "## ${sprint} — ${today_date}"
        echo ""
        echo "### アーキテクチャ判断"
        echo "$arch_decisions"
        echo ""
        echo "### 学び"
        echo "$learnings"
        echo ""
        echo "### 失敗パターン"
        echo "$failure_patterns"
        echo ""
        echo "### 次スプリントへの推奨"
        echo "$on_hold_recs"
        printf '%b' "$recommendations"
        echo ""
        echo "---"
      } >> "$decisions_file"
      echo "OK: DECISIONS.md updated ($decisions_file)" >&2
    fi
  fi
}

# ---------- ディスパッチ ----------
cmd=${1:-}
shift || true
case "$cmd" in
  start)            cmd_start "$@" ;;
  done)             cmd_done "$@" ;;
  handoff)          cmd_handoff "$@" ;;
  parallel-handoff) cmd_parallel_handoff "$@" ;;
  qa)               cmd_qa "$@" ;;
  block)            cmd_block "$@" ;;
  retry)            cmd_retry "$@" ;;
  show)             cmd_show "$@" ;;
  next)             cmd_next "$@" ;;
  graph)            cmd_graph "$@" ;;
  retro)            cmd_retro "$@" ;;
  ""|help|-h|--help)
    sed -n '2,28p' "$0"
    ;;
  *)
    echo "ERROR: unknown command: $cmd" >&2
    exit 1
    ;;
esac
