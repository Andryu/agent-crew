#!/bin/bash
# 13 共通 fixture: BENCH_SEED から大きめ入力（重複あり）を決定的に生成し report.py を実行する
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

COUNT=$(( 300 + $(t_rand 1 200) ))  # 300〜499件
DUP_PCT=$(( 2 + $(t_rand 2 4) ))    # 2〜5%（小さい入力では再現しにくい確率に相当）

ENTRIES_FILE="$BENCH_TMP/entries.jsonl"
python3 "$BENCH_TASK_DIR/fixture/gen_entries.py" "$BENCH_SEED" "$COUNT" "$DUP_PCT" > "$ENTRIES_FILE"

REPORT_OUT="$BENCH_TMP/report_out.txt"
REPORT_ERR="$BENCH_TMP/report_err.txt"
(cd "$BENCH_WORK_DIR" && python3 report.py "$ENTRIES_FILE") > "$REPORT_OUT" 2>"$REPORT_ERR" \
  || fail "report.py が非ゼロで終了した: $(cat "$REPORT_ERR")"

# 正解値を report.py のロジックとは独立に再計算する（部門別合計・重複除去後の全体合計）
python3 - "$ENTRIES_FILE" > "$BENCH_TMP/expected.json" <<'PYEOF'
import json, sys
seen = set()
totals = {}
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    e = json.loads(line)
    if e["id"] in seen:
        continue
    seen.add(e["id"])
    totals[e["department"]] = totals.get(e["department"], 0) + e["amount"]
json.dump({"totals": totals, "total": sum(totals.values())}, sys.stdout, ensure_ascii=False)
PYEOF
