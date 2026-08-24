#!/usr/bin/env python3
"""metrics/summarize.py — metrics.jsonl を主要指標3つに集計する

使い方: python3 metrics/summarize.py [--prices prices.json]

主要指標（v4.1）:
  1. $ / solved task   … 満点で解けた1問あたりのコスト
  2. wall-clock / task … 1問あたりの実時間
  3. 人間の介入回数     … 手で記録した値の合計（null は未記録）

token/request は記録するが指標にしない（「同じ枠で何回回せるか」に翻訳して初めて意味を持つ）。
"""
import json, sys, os, collections

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MET = os.path.join(BENCH, "results", "metrics.jsonl")

# $/1M tokens: (input, cached_read, output)。cache 比率が不明な行は input 単価で概算する
PRICES = {
    "gpt-5.6-sol":   (5.00, 0.50, 30.00),
    "gpt-5.6-luna":  (0.20, 0.02, 1.20),
    "sonnet":        (2.00, 0.20, 10.00),
    "opus":          (5.00, 0.50, 25.00),
    "gemma4-64k":    (0.0, 0.0, 0.0),      # ローカルは電気代のみ
}

def cost(row):
    p = PRICES.get(row.get("model") or "")
    if not p: return None
    pi, pc, po = p
    ti, to, tt = row.get("tokens_in"), row.get("tokens_out"), row.get("tokens_total")
    if ti is not None and to is not None:
        # 実測の内訳が不明なので入力はすべて cache_read 相当として概算（実測で96%が cache_read）
        return (ti * pc + to * po) / 1e6
    if tt is not None:
        return (tt * pc) / 1e6      # 総数しか無い場合は cache 単価で概算
    return None

def main():
    if not os.path.exists(MET):
        print("metrics.jsonl がありません"); return
    rows = [json.loads(l) for l in open(MET, encoding="utf-8") if l.strip()]
    by = collections.defaultdict(list)
    for r in rows: by[(r["lane"], r.get("model") or "-")].append(r)

    print(f"{'lane/model':28s} {'解けた/実行':>11s} {'$/solved':>10s} {'秒/問':>7s} {'介入':>5s}")
    print("-" * 66)
    for (lane, model), rs in sorted(by.items()):
        n = len(rs); solved = sum(r["solved"] for r in rs)
        costs = [c for c in (cost(r) for r in rs) if c is not None]
        secs = [r["seconds"] for r in rs if r.get("seconds")]
        ivs = [r["human_interventions"] for r in rs if r.get("human_interventions") is not None]
        cps = f"${sum(costs)/solved:.3f}" if costs and solved else "—"
        sps = f"{sum(secs)/n:.0f}" if secs else "—"
        ivt = str(sum(ivs)) if ivs else "未記録"
        print(f"{lane+'/'+model:28s} {f'{solved}/{n}':>11s} {cps:>10s} {sps:>7s} {ivt:>5s}")
    print()
    print("注: $ は cache_read 単価での概算（実測で入力の96%が cache_read のため）。")
    print("    人間の介入回数は手で記録する（自動計測しない）。未記録は評価に使わない。")

if __name__ == "__main__":
    main()
