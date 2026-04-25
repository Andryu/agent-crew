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
#   queue.sh detect-stale [--threshold <min>]                    # 中断タスク（IN_PROGRESS >= N分）を検出
#   queue.sh retro [--save] [--decisions]                        # リトロスペクティブ集計
#
# 環境変数:
#   QUEUE_FILE   キューファイルパス (default: .claude/_queue.json)
#   QUEUE_LOCK   ロックディレクトリ (default: .claude/.queue.lock)
#   MAX_RETRY    リトライ上限 (default: 3)

set -euo pipefail

QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"
MAX_RETRY="${MAX_RETRY:-3}"

# ---------- ヘルパー: Python が使用可能かチェック ----------
_check_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. agent-crew requires Python 3.12+." >&2
    echo "  Install: https://python.org/downloads/" >&2
    exit 99
  fi
  local ver
  ver=$(python3 -c "import sys; print(sys.version_info >= (3, 12))" 2>/dev/null || echo "False")
  if [[ "$ver" != "True" ]]; then
    echo "WARN: Python 3.12+ recommended. queue.py may not function correctly." >&2
  fi
}

# ---------- コマンド: parallel-handoff ----------
# 複数タスクを queue.py handoff への連続呼び出しでハンドオフ
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

  _check_python

  for pair in "$@"; do
    local slug="${pair%%:*}"
    local next_agent="${pair#*:}"
    python3 "$(dirname "$0")/queue.py" handoff "$slug" "$next_agent"
  done
}

# ---------- コマンド: retro ----------
# スプリント完了時のメトリクスを集計して STDOUT に出力する
# --save フラグで docs/retro/<sprint>-retro.md に保存する
# --decisions フラグで docs/DECISIONS.md に追記する
cmd_retro() {
  if [[ ! -f "$QUEUE_FILE" ]] || ! jq empty "$QUEUE_FILE" 2>/dev/null; then
    echo "ERROR: queue file not found or invalid: $QUEUE_FILE" >&2
    exit 3
  fi

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
  today_date=$(date -u +%Y-%m-%d)

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

  # ---------- _signals.jsonl 集計（ファイルが存在する場合のみ追加） ----------
  local signals_file
  signals_file="$(dirname "$QUEUE_FILE")/_signals.jsonl"
  local signals_section=""
  if [[ -f "$signals_file" ]]; then
    local sig_total sig_done sig_approved sig_changes sig_retry sig_blocked
    sig_total=$(wc -l < "$signals_file" | tr -d ' ')
    sig_done=$(grep -c '"type":"task.done"' "$signals_file" 2>/dev/null || echo 0)
    sig_approved=$(grep -c '"type":"qa.approved"' "$signals_file" 2>/dev/null || echo 0)
    sig_changes=$(grep -c '"type":"qa.changes_requested"' "$signals_file" 2>/dev/null || echo 0)
    sig_retry=$(grep -c '"type":"task.retry"' "$signals_file" 2>/dev/null || echo 0)
    sig_blocked=$(grep -c '"type":"task.blocked"' "$signals_file" 2>/dev/null || echo 0)
    signals_section="
## シグナル集計（_signals.jsonl）
- 記録イベント数: ${sig_total}件
- task.done: ${sig_done}件
- qa.approved: ${sig_approved}件 / qa.changes_requested: ${sig_changes}件
- task.retry: ${sig_retry}件
- task.blocked: ${sig_blocked}件"
  fi

  echo "$retro_body"
  [[ -n "$signals_section" ]] && echo "$signals_section"

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
      [[ -n "$signals_section" ]] && echo "$signals_section"
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
# Python委譲コマンドリスト（start/done/handoff/qa/block/retry/show/next/detect-stale/graph）
_PY_COMMANDS="start done handoff qa block retry show next detect-stale graph"

cmd=${1:-}
shift || true
case "$cmd" in
  parallel-handoff)
    cmd_parallel_handoff "$@"
    ;;
  retro)
    cmd_retro "$@"
    ;;
  ""|help|-h|--help)
    sed -n '2,28p' "$0"
    ;;
  *)
    # Python委譲コマンドかチェック
    if printf '%s\n' $_PY_COMMANDS | grep -qx "$cmd"; then
      _check_python
      exec python3 "$(dirname "$0")/queue.py" "$cmd" "$@"
    fi
    echo "ERROR: unknown command: $cmd" >&2
    exit 1
    ;;
esac
