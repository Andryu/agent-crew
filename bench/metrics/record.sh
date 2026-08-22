#!/bin/bash
# metrics/record.sh — レーン実行の指標を1行 JSON で追記する
#
# 使い方:
#   metrics/record.sh --lane codex --model gpt-5.6-sol --task 05-lessons-set-status \
#     --score 9 --max 9 --penalty 0 --seconds 412 --log <harness-log> [--interventions N]
#
# 出力: bench/results/metrics.jsonl（1行1実行）
#
# 指標の考え方（v4.1）:
#   主要指標は「$ / solved task」「wall-clock / task」「人間の介入回数」の3つ。
#   token/request は記録するが指標にはしない（「同じ枠で何回回せるか」に翻訳して初めて意味を持つ）。
#   人間の介入時間は自動計測しない（計測の仕組み自体が運用の重荷になるため回数のみ）。
set -uo pipefail
BENCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$BENCH_ROOT/results/metrics.jsonl"
lane=""; model=""; task=""; score=0; max=0; penalty=0; seconds=0; logf=""; interventions=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --lane) lane="$2"; shift 2;; --model) model="$2"; shift 2;;
    --task) task="$2"; shift 2;; --score) score="$2"; shift 2;;
    --max) max="$2"; shift 2;; --penalty) penalty="$2"; shift 2;;
    --seconds) seconds="$2"; shift 2;; --log) logf="$2"; shift 2;;
    --interventions) interventions="$2"; shift 2;;
    *) shift;;
  esac
done

# ハーネスのログからトークン数を拾う（取れなければ null）
tok_in=null; tok_out=null; tok_total=null
if [[ -n "$logf" && -f "$logf" ]]; then
  # Codex: "tokens used\n123,456"
  t=$(grep -A1 -i '^tokens used' "$logf" 2>/dev/null | tail -1 | tr -d ', ' | grep -E '^[0-9]+$' | tail -1)
  [[ -n "${t:-}" ]] && tok_total="$t"
  # Claude Code --output-format json: {"usage":{"input_tokens":N,...}}
  if command -v python3 >/dev/null 2>&1; then
    read -r i o < <(python3 - "$logf" <<'PY' 2>/dev/null || echo ""
import json,sys,re
try: s=open(sys.argv[1],encoding='utf-8',errors='ignore').read()
except Exception: sys.exit()
m=re.findall(r'"usage"\s*:\s*\{[^}]*\}', s)
ti=to=0
for x in m:
    try:
        u=json.loads("{"+x+"}")["usage"]
        ti+=u.get("input_tokens",0)+u.get("cache_creation_input_tokens",0)+u.get("cache_read_input_tokens",0)
        to+=u.get("output_tokens",0)
    except Exception: pass
if ti or to: print(ti,to)
PY
)
    [[ -n "${i:-}" ]] && { tok_in="$i"; tok_out="$o"; }
  fi
fi

solved=0
[[ "$max" -gt 0 && "$score" -eq "$max" ]] && solved=1
iv="null"; [[ -n "$interventions" ]] && iv="$interventions"

mkdir -p "$(dirname "$OUT")"
printf '{"at":"%s","lane":"%s","model":"%s","task":"%s","score":%s,"max":%s,"solved":%s,"quality_penalty":%s,"seconds":%s,"tokens_in":%s,"tokens_out":%s,"tokens_total":%s,"human_interventions":%s}\n' \
  "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$lane" "$model" "$task" "$score" "$max" "$solved" "$penalty" "$seconds" "$tok_in" "$tok_out" "$tok_total" "$iv" >> "$OUT"
echo "recorded: $lane/$task $score/$max (solved=$solved, ${seconds}s)"
