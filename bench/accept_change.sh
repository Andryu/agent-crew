#!/bin/bash
# accept_change.sh — ハーネスの自己変更を採用してよいか判定する（v4.1 #7）
#
# 使い方:
#   accept_change.sh --harness <name> --before <baseline.jsonl> --after <candidate.jsonl>
#   accept_change.sh --harness hermes --round 3        # results/adaptation/ から自動で拾う
#
# 判定（すべて満たしたら accept、1つでも欠けたら reject）:
#   1. dev のスコアが下がっていない（同点は可）
#   2. regression チェックがゼロ（各タスクの regression 落ちが無い）
#   3. コスト増が +20% 以内（$/solved task）
#   4. 品質減点が増えていない
#
# **hidden は参照しない。** hidden のスコアを採否に使うと、その判断を通じて hidden にも
# overfit する（採用される変更は hidden で良かった変更だけになり、hidden が第2の dev に化ける）。
# hidden は3週間の実験が終わった後に1回だけ開封する。
set -uo pipefail
BENCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
harness=""; before=""; after=""; tol_cost=20
while [[ $# -gt 0 ]]; do
  case "$1" in
    --harness) harness="$2"; shift 2;;
    --before) before="$2"; shift 2;;
    --after) after="$2"; shift 2;;
    --cost-tolerance) tol_cost="$2"; shift 2;;
    *) shift;;
  esac
done
[[ -n "$harness" && -f "${before:-}" && -f "${after:-}" ]] || {
  echo "usage: accept_change.sh --harness <name> --before <baseline.jsonl> --after <candidate.jsonl>" >&2; exit 2; }

python3 - "$before" "$after" "$harness" "$tol_cost" <<'PY'
import json,sys,collections
before_f, after_f, harness, tol = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])

def load(p):
    rows=[json.loads(l) for l in open(p,encoding='utf-8') if l.strip()]
    # hidden は判定に使わない（split が記録されていれば除外する）
    dropped=[r for r in rows if r.get("split")=="hidden"]
    rows=[r for r in rows if r.get("split")!="hidden"]
    return rows, dropped

b,bd = load(before_f)
a,ad = load(after_f)
if bd or ad:
    print(f"  note: hidden のレコード {len(bd)+len(ad)} 件を判定から除外した（設計どおり）")

def idx(rows): return {r["task"]:r for r in rows}
B,A = idx(b), idx(a)
common = sorted(set(B) & set(A))
if not common:
    print("REJECT: 比較できるタスクが無い"); sys.exit(1)

fails=[]

# 1. dev のスコアが下がっていない
drops=[(t,B[t]["score"],A[t]["score"]) for t in common if A[t]["score"] < B[t]["score"]]
if drops:
    fails.append("スコア低下: " + ", ".join(f"{t} {x}→{y}" for t,x,y in drops))

# 2. regression ゼロ（regression 落ちはタスク0点になる仕様なので score==0 かつ before>0 で検出）
regr=[t for t in common if A[t]["score"]==0 and B[t]["score"]>0]
if regr: fails.append("regression 発生: " + ", ".join(regr))

# 3. コスト増が許容内
def total_cost(rows):
    # tokens_total か tokens_in/out があるものだけ合算（無ければ None）
    tt=[r for r in rows if r.get("tokens_total") or r.get("tokens_in")]
    if not tt: return None
    return sum((r.get("tokens_total") or 0) + (r.get("tokens_in") or 0) + (r.get("tokens_out") or 0) for r in tt)
cb, ca = total_cost([B[t] for t in common]), total_cost([A[t] for t in common])
if cb and ca:
    pct=(ca-cb)/cb*100
    if pct > tol: fails.append(f"コスト増 {pct:+.1f}%（許容 +{tol:.0f}%）")
    else: print(f"  コスト変化: {pct:+.1f}%")
else:
    print("  コスト: トークン未記録のため判定をスキップ")

# 4. 品質減点が増えていない
qb=sum(B[t].get("quality_penalty",0) for t in common)
qa=sum(A[t].get("quality_penalty",0) for t in common)
if qa > qb: fails.append(f"品質減点の増加 {qb}→{qa}")

sb=sum(B[t]["score"] for t in common); sa=sum(A[t]["score"] for t in common)
print(f"  dev スコア: {sb} → {sa}（{len(common)}タスク）")

if fails:
    print(f"REJECT [{harness}]:")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print(f"ACCEPT [{harness}]: dev 非退行・regression なし・コスト許容内・品質維持")
PY
