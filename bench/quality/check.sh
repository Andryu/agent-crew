#!/bin/bash
# quality/check.sh — 「テストは通るが品質が悪い」を検出する減点チェック
#
# 使い方: check.sh <workdir> <task-dir>
# 出力  : 1行1件の "PENALTY <points> <reason>" と、最後に "QUALITY_PENALTY_TOTAL <n>"
#
# 背景: laiso の実測（2026-07-18）で Kimi K3 は ReactBench 全課題でテスト合格したが
# 静的解析では全て不合格だった。安いモデルほど「テストが通る」と「品質が保たれる」の
# 乖離が大きい。holdout（振る舞い）だけでは安いレーンを過大評価する。
set -uo pipefail
W="$1"; T="${2:-}"
total=0
pen(){ echo "PENALTY $1 $2"; total=$((total+$1)); }

# 対象は「解答者が変更した追跡対象ファイル」のみ（TASK.md と visible_test は除く）
# macOS の bash 3.2 には mapfile が無いので配列は while read で組む
changed=()
while IFS= read -r line; do
  [[ -n "$line" ]] && changed+=("$line")
done < <(git -C "$W" status --porcelain 2>/dev/null \
  | awk '{print $2}' | grep -vE '^(TASK\.md|visible_test/|docs/handoff/)' || true)

# 1) shellcheck: 変更した .sh に新規の error/warning が出ていないか
if command -v shellcheck >/dev/null 2>&1; then
  for f in "${changed[@]:-}"; do
    [[ "$f" == *.sh ]] || continue
    [[ -f "$W/$f" ]] || continue
    n=$(shellcheck -S warning -f gcc "$W/$f" 2>/dev/null | wc -l | tr -d ' ')
    if [[ "${n:-0}" -gt 0 ]]; then
      pen 1 "shellcheck: $f に warning 以上が ${n} 件"
    fi
  done
fi

# 2) python: 構文エラーと、あからさまな重複定義
if command -v python3 >/dev/null 2>&1; then
  for f in "${changed[@]:-}"; do
    [[ "$f" == *.py ]] || continue
    [[ -f "$W/$f" ]] || continue
    python3 -m py_compile "$W/$f" 2>/dev/null || pen 2 "python: $f が構文エラー"
    dup=$(grep -oE '^def [a-zA-Z_]+' "$W/$f" 2>/dev/null | sort | uniq -d | wc -l | tr -d ' ')
    [[ "${dup:-0}" -gt 0 ]] && pen 1 "python: $f に同名関数の重複定義 ${dup} 件"
  done
fi

# 3) 過剰実装: 差分が参照実装の3倍を超えていないか（meta.yaml に ref_lines があるとき）
if [[ -n "$T" && -f "$T/meta.yaml" ]]; then
  ref=$(grep -E '^ref_lines:' "$T/meta.yaml" 2>/dev/null | awk '{print $2}')
  if [[ -n "${ref:-}" ]]; then
    add=$(git -C "$W" diff --numstat 2>/dev/null | awk '{s+=$1} END{print s+0}')
    untracked=$(for f in "${changed[@]:-}"; do [[ -f "$W/$f" ]] && wc -l < "$W/$f"; done | awk '{s+=$1} END{print s+0}')
    tot=$((add+untracked))
    if [[ "$tot" -gt $((ref*3)) ]]; then
      pen 1 "過剰実装: 追加 ${tot} 行は参照実装 ${ref} 行の3倍超"
    fi
  fi
fi

echo "QUALITY_PENALTY_TOTAL $total"
