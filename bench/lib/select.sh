#!/bin/bash
# lib/select.sh — track / split でタスクを選ぶ
#
# 使い方:
#   source lib/select.sh
#   bench_tasks split=dev              # dev のタスクディレクトリを1行1件で出力
#   bench_tasks split=hidden --unseal  # hidden は --unseal なしでは出力しない（事故防止）
#   bench_tasks track=adversarial
#
# 設計意図: hidden は「3週間の実験が終わった後に1回だけ」開封する。
# 途中で accept/reject に使うと、その判断を通じて hidden にも overfit するため、
# 明示的な --unseal なしには選択できないようにしてある。
bench_tasks() {
  local bench_root filter_key filter_val unseal=0
  # BENCH_ROOT が設定されていればそれを使う。無ければこのファイルの親（= bench/）
  # ※ zsh から source すると BASH_SOURCE が空になるため、環境変数を優先する
  bench_root="${BENCH_ROOT:-}"
  if [[ -z "$bench_root" ]]; then
    bench_root="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")/.." 2>/dev/null && pwd)"
  fi
  [[ -d "$bench_root/tasks" ]] || { echo "bench root が見つからない: $bench_root (BENCH_ROOT を設定してください)" >&2; return 2; }
  for a in "$@"; do
    case "$a" in
      --unseal) unseal=1 ;;
      *=*) filter_key="${a%%=*}"; filter_val="${a#*=}" ;;
    esac
  done
  [[ -n "${filter_key:-}" ]] || { echo "usage: bench_tasks track=X|split=Y [--unseal]" >&2; return 2; }
  if [[ "$filter_key" == "split" && "$filter_val" == "hidden" && "$unseal" -ne 1 ]]; then
    echo "refusing: split=hidden は --unseal が必要（実験終了後の最終評価でのみ開封する）" >&2
    return 3
  fi
  local d v
  for d in "$bench_root"/tasks/*/; do
    [[ -d "$d" && -f "$d/meta.yaml" ]] || continue
    v=$(grep -E "^${filter_key}:" "$d/meta.yaml" 2>/dev/null | head -1 | awk '{print $2}')
    [[ "$v" == "$filter_val" ]] && echo "${d%/}"
  done
}

# hidden を誤って実行していないか確認する（ランナーから呼ぶ）
bench_assert_not_hidden() {
  local task_dir="$1" v
  v=$(grep -E '^split:' "$task_dir/meta.yaml" 2>/dev/null | head -1 | awk '{print $2}')
  if [[ "$v" == "hidden" && "${BENCH_UNSEAL_HIDDEN:-}" != "1" ]]; then
    echo "ERROR: $(basename "$task_dir") は split: hidden。実験終了後の最終評価でのみ実行する。" >&2
    echo "  どうしても実行するなら BENCH_UNSEAL_HIDDEN=1 を明示すること。" >&2
    return 3
  fi
  return 0
}
