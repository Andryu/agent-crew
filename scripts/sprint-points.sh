#!/bin/bash
# sprint-points.sh — _queue.json のタスクをS=1/M=3/L=5換算で機械集計する (Issue #135)
#
# 目的:
#   スプリント計画書のポイント集計・負荷分散スコアの手計算ミスを防ぐため、
#   pm-estimation.md の複雑度ポイント表（S=1 / M=3 / L=5）と同一の換算規則で
#   .claude/_queue.json を集計するツール。
#
# 使い方:
#   scripts/sprint-points.sh          # JSON形式で集計結果を出力
#   scripts/sprint-points.sh --md     # 上記に加え、計画書へ転記しやすいMarkdown断片も出力
#
# 環境変数:
#   QUEUE_FILE   キューファイルパス (default: .claude/_queue.json)
#
# 出力（JSON）:
#   total_points          : 全タスクの合計ポイント
#   by_complexity         : complexity別内訳（件数×換算）
#   by_agent              : 担当者別タスク数・ポイント（ポイント降順）
#   load_balance          : 負荷分散スコア（タスク数ベース／ポイントベースの両方）
#     by_task_count.score    : 最多担当タスク数 ÷ 平均タスク数（補助指標。official: false）
#     by_points.score        : 最多担当ポイント ÷ 平均ポイント（公式指標。official: true。
#                              Sprint-25レトロで公式化、pm-estimation.md参照。基準 <= 2.0）

set -euo pipefail

QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"
OUTPUT_MD=0

for arg in "$@"; do
  case "$arg" in
    --md)
      OUTPUT_MD=1
      ;;
    *)
      echo "ERROR: unknown option: $arg" >&2
      echo "usage: $0 [--md]" >&2
      exit 1
      ;;
  esac
done

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq が見つかりません" >&2
  exit 1
fi

if [[ ! -f "$QUEUE_FILE" ]]; then
  echo "ERROR: queue file not found: $QUEUE_FILE" >&2
  exit 1
fi

if ! jq empty "$QUEUE_FILE" 2>/dev/null; then
  echo "ERROR: queue file not found or invalid JSON: $QUEUE_FILE" >&2
  exit 1
fi

# complexity => ポイント の換算は pm-estimation.md 準拠 (S=1 / M=3 / L=5)
JQ_FILTER='
def cpx_order: if . == "S" then 0 elif . == "M" then 1 elif . == "L" then 2 else 3 end;
def cpx_points:
  if . == "S" then 1
  elif . == "M" then 3
  elif . == "L" then 5
  else error("unknown complexity value: " + (. // "null"))
  end;

.tasks as $tasks
| ($tasks | map(. + {points: (.complexity | cpx_points)})) as $enriched
| ($enriched | map(.points) | add // 0) as $total_points
| ($enriched | length) as $total_tasks
| ($enriched
    | group_by(.complexity)
    | map({
        complexity: .[0].complexity,
        count: length,
        points: (length * (.[0].complexity | cpx_points))
      })
    | sort_by(.complexity | cpx_order)
  ) as $by_complexity
| ($enriched
    | group_by(.assigned_to)
    | map({
        assigned_to: .[0].assigned_to,
        count: length,
        points: (map(.points) | add)
      })
    | sort_by([-.points, -.count, .assigned_to])
  ) as $by_agent
| ($by_agent | length) as $distinct_agents
| ($by_agent | map(.count) | max) as $max_task_count
| ($by_agent | map(.points) | max) as $max_agent_points
| ((($total_tasks / $distinct_agents) * 100 | round) / 100) as $avg_task_count
| ((($total_points / $distinct_agents) * 100 | round) / 100) as $avg_agent_points
| ((($max_task_count / ($total_tasks / $distinct_agents)) * 100 | round) / 100) as $score_by_count
| ((($max_agent_points / ($total_points / $distinct_agents)) * 100 | round) / 100) as $score_by_points
| {
    sprint: (.sprint // "unknown"),
    total_tasks: $total_tasks,
    total_points: $total_points,
    by_complexity: $by_complexity,
    by_agent: $by_agent,
    load_balance: {
      distinct_agents: $distinct_agents,
      by_task_count: {
        max: $max_task_count,
        avg: $avg_task_count,
        score: $score_by_count,
        official: false
      },
      by_points: {
        max: $max_agent_points,
        avg: $avg_agent_points,
        score: $score_by_points,
        official: true
      }
    }
  }
'

if ! RESULT_JSON=$(jq "$JQ_FILTER" "$QUEUE_FILE"); then
  echo "ERROR: jq による集計に失敗しました（complexity値の異常などを確認してください）" >&2
  exit 1
fi

echo "$RESULT_JSON"

if [[ "$OUTPUT_MD" -eq 1 ]]; then
  echo
  echo "---"
  echo
  if ! jq -r '
    "> **合計ポイント: " + (.total_points | tostring) + " pt**（" +
    ([.by_complexity[] | (.complexity + "×" + (.count|tostring) + "件=" + (.points|tostring) + "pt")] | join(" + ")) +
    " = **" + (.total_points|tostring) + "pt**）\n\n" +
    "### 担当者別ポイント（負荷分散）\n\n" +
    "| 担当 | タスク数 | ポイント |\n" +
    "|------|---------|---------|\n" +
    ([.by_agent[] | "| " + .assigned_to + " | " + (.count|tostring) + " | " + (.points|tostring) + " |"] | join("\n")) +
    "\n\n総タスク数=" + (.total_tasks|tostring) + "、稼働担当数=" + (.load_balance.distinct_agents|tostring) +
    "、平均タスク数=" + (.load_balance.by_task_count.avg|tostring) +
    "、最多担当タスク数=" + (.load_balance.by_task_count.max|tostring) + "。\n" +
    "**負荷分散スコア（タスク数ベース・補助）= " + (.load_balance.by_task_count.max|tostring) + " / " + (.load_balance.by_task_count.avg|tostring) + " = " + (.load_balance.by_task_count.score|tostring) + "**\n\n" +
    "平均ポイント=" + (.load_balance.by_points.avg|tostring) + "、最多担当ポイント=" + (.load_balance.by_points.max|tostring) + "。\n" +
    "**負荷分散スコア（ポイントベース・公式）= " + (.load_balance.by_points.max|tostring) + " / " + (.load_balance.by_points.avg|tostring) + " = " + (.load_balance.by_points.score|tostring) + "**（基準 <= 2.0）"
  ' <<< "$RESULT_JSON"; then
    echo "ERROR: Markdown断片の生成に失敗しました" >&2
    exit 1
  fi
fi
