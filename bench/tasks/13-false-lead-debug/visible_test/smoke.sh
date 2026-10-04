#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物）:
#   同梱の entries.jsonl（小さめ・重複なし）に対して report.py がエラーなく走り、
#   出力フォーマット（"部門: 金額" 各行 + "TOTAL: 金額"）が壊れていないことを確かめる。
#   この fixture では症状が再現しないことに注意（大きい入力でのみ再現する）。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
OUT=$(cd "$WORK" && python3 report.py entries.jsonl)

echo "$OUT" | grep -qE '^TOTAL: [0-9]+$' || { echo "NG: TOTAL 行の形式が壊れている" >&2; exit 1; }
echo "$OUT" | grep -qE '^[^:]+: [0-9]+$' || { echo "NG: 部門行の形式が壊れている" >&2; exit 1; }

echo "visible smoke: OK"
