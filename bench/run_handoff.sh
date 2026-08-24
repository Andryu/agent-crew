#!/bin/bash
# run_handoff.sh — 途中でハーネスを交代し、引き継ぎパケットだけで再開できるかを測る
#
# 使い方:
#   run_handoff.sh <task-dir> --first <harness:model> --second <harness:model> [--work <dir>] [--budget-min N]
#
# 流れ:
#   1) setup（親SHAスナップショット）
#   2) 前半ハーネスに「途中まで解き、時間が来たら docs/handoff/ にパケットを書いて終了」と指示
#   3) 会話履歴は一切渡さず、後半ハーネスにパケット＋リポジトリの現状だけ渡す
#   4) holdout で採点。単独実行時のスコアと比較して「引き継ぎで失った点」を測る
set -euo pipefail
BENCH=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TASK="$1"; shift
TASK=$(cd "$TASK" && pwd); NAME=$(basename "$TASK")
FIRST=""; SECOND=""; WORK="/tmp/bench-handoff/$NAME"; BUDGET=6
while [[ $# -gt 0 ]]; do
  case "$1" in
    --first) FIRST="$2"; shift 2;;
    --second) SECOND="$2"; shift 2;;
    --work) WORK="$2"; shift 2;;
    --budget-min) BUDGET="$2"; shift 2;;
    *) echo "unknown: $1" >&2; exit 2;;
  esac
done
[[ -n "$FIRST" && -n "$SECOND" ]] || { echo "--first と --second は必須" >&2; exit 2; }
h_of(){ echo "${1%%:*}"; }; m_of(){ local s="${1#*:}"; [[ "$s" == "$1" ]] && echo "" || echo "$s"; }

rm -rf "$WORK"; "$BENCH/run_task.sh" "$TASK" --work "$WORK" >/dev/null 2>&1
mkdir -p "$WORK/docs/handoff"
PDIR=$(mktemp -d)

# ---- 前半: 途中で止めてパケットを書かせる ----
cat > "$PDIR/first.md" <<EOF
課題を解いてください。課題文: $TASK/prompt.md を読む。
カレントディレクトリが作業ディレクトリで、この中の既存ソースを編集して解きます。
見てよいテスト: $TASK/visible_test/ 。$TASK/holdout_test/ は絶対に開かない。
/Users/ando_shunsuke/Workspace/agent-crew や GitHub は参照しない。

**重要な制約: あなたは最後まで解ききれません。**
**必ず途中で止めること。** 課題の要件が複数あるなら、そのうち**半分だけ**を実装した時点で
（全要件を満たす前に、かつ全テストが通る前に）作業を打ち切ります。「あと少しで終わる」と
思っても続けてはいけません。目安 $BUDGET 分。打ち切ったら、
別のAIエージェントが**あなたの会話を一切見ずに**続きを引き継げるよう、引き継ぎ書を
docs/handoff/handoff.md に作成して終了してください。書式は $BENCH/handoff/PACKET.md の
6節（目的／現在地／次の一手／未決事項／検証方法／落とし穴）に厳密に従うこと。
引き継ぎ書は2000トークン以内。会話の要約ではなく「作業状態」を書くこと。
**7節「Evidence」は書かなくてよい**（git status / diff / テスト結果はスクリプトが自動で
追記する）。あなたが書くのは「なぜ・次に何を・どこに罠があるか」であって、現在地の証拠ではない。
EOF

echo "== 前半: $FIRST =="
"$BENCH/harness/$(h_of "$FIRST").sh" "$WORK" "$PDIR/first.md" "$(m_of "$FIRST")" > "$WORK/../${NAME}.first.log" 2>&1 || echo "(前半 exit=$?)"
if [[ -f "$WORK/docs/handoff/handoff.md" ]]; then
  # 7節 Evidence はスクリプトが追記する（LLM には書かせない）
  "$BENCH/handoff/evidence.sh" "$WORK" >> "$WORK/docs/handoff/handoff.md" 2>/dev/null || true
  echo "  パケット生成: $(wc -l < "$WORK/docs/handoff/handoff.md") 行 / $(wc -c < "$WORK/docs/handoff/handoff.md") bytes（Evidence 付き）"
else
  echo "  !! パケットが作られなかった（引き継ぎ失敗の主要因として記録）"
fi
echo "  中間スコア:"; { "$BENCH/run_task.sh" "$TASK" --score --work "$WORK" --seed 7 2>&1 || true; } | grep -E "スコア" | sed 's/^/    /'

# ---- 後半: パケットだけ渡して再開 ----
cat > "$PDIR/second.md" <<EOF
別のAIエージェントが途中まで進めた作業を引き継いで完成させてください。
**会話履歴は渡されません。** 手がかりは次の2つだけです:
  1. 引き継ぎ書: $WORK/docs/handoff/handoff.md（まずこれを読む）
  2. 作業ディレクトリの現状（カレントディレクトリ。git status / git diff で差分を確認できる）
元の課題文も参照してよい: $TASK/prompt.md
見てよいテスト: $TASK/visible_test/ 。$TASK/holdout_test/ は絶対に開かない。
/Users/ando_shunsuke/Workspace/agent-crew や GitHub は参照しない。

引き継ぎ書の「未決事項」に挙がっている論点には手を出さないこと。
引き継ぎ書とリポジトリの実態が食い違う場合は実態を優先し、その旨を作業ログに書くこと。
完成したら「検証方法」に書かれたコマンドで確認してから終了してください。
EOF

echo "== 後半: $SECOND =="
"$BENCH/harness/$(h_of "$SECOND").sh" "$WORK" "$PDIR/second.md" "$(m_of "$SECOND")" > "$WORK/../${NAME}.second.log" 2>&1 || echo "(後半 exit=$?)"

echo "== 最終スコア（引き継ぎ後） =="
for s in 7 88 20260817; do { "$BENCH/run_task.sh" "$TASK" --score --work "$WORK" --seed $s 2>&1 || true; } | grep -E 'スコア' | sed 's/^/  /'; done
echo "  work: $WORK"
