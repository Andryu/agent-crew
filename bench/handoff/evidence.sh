#!/bin/bash
# handoff/evidence.sh — 引き継ぎパケットの「7. Evidence」節を機械的に生成する
#
# 使い方:
#   handoff/evidence.sh <workdir> [--test "<検証コマンド>"] >> docs/handoff/handoff.md
#
# 設計意図:
#   Evidence は「機械的に検証可能な情報」なので、LLM に書かせない（書かせた時点で
#   機械的でなくなる）。1〜6節は LLM が書き、7節はこのスクリプトが書く。
#   食い違ったら 7節を信じる、という原則を PACKET.md に置いている。
set -uo pipefail
W="${1:-.}"; shift || true
TEST_CMD=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --test) TEST_CMD="$2"; shift 2 ;;
    *) shift ;;
  esac
done
cd "$W" || { echo "workdir が見つからない: $W" >&2; exit 2; }

echo "## 7. Evidence（自動生成 — handoff/evidence.sh）"
echo
echo "- generated_at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "- workdir: \`$(pwd)\`"

if git rev-parse --git-dir >/dev/null 2>&1; then
  head_sha=$(git rev-parse --short HEAD 2>/dev/null || echo "(コミットなし)")
  if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then state="dirty"; else state="clean"; fi
  echo "- HEAD: \`$head_sha\` ($state)"
  echo
  echo "### git status --porcelain"
  echo '```'
  git status --porcelain 2>/dev/null | head -50
  [[ $(git status --porcelain 2>/dev/null | wc -l) -gt 50 ]] && echo "... (50件で打ち切り)"
  echo '```'
  echo
  echo "### git diff --stat"
  echo '```'
  git diff --stat 2>/dev/null | tail -30
  echo '```'
  echo
  echo "### 変更ファイル（追加/削除行）"
  echo '```'
  git diff --numstat 2>/dev/null | awk '{printf "%s  +%s/-%s\n", $3, $1, $2}' | head -30
  git ls-files --others --exclude-standard 2>/dev/null \
    | grep -vE '^(TASK\.md|visible_test/|docs/handoff/)' \
    | while IFS= read -r f; do [[ -f "$f" ]] && printf "%s  (新規 %s 行)\n" "$f" "$(wc -l < "$f" | tr -d ' ')"; done | head -20
  echo '```'
else
  echo "- HEAD: (git リポジトリではない)"
fi

echo
echo "### テスト"
if [[ -n "$TEST_CMD" ]]; then
  echo "実行: \`$TEST_CMD\`"
  echo '```'
  out=$(eval "$TEST_CMD" 2>&1); rc=$?
  echo "$out" | tail -20
  echo "exit=$rc"
  echo '```'
else
  echo "（`--test "<コマンド>"` が指定されていないため未実行）"
fi

echo
echo "### 関連"
# ADR と、明示的に issue/PR と書かれた参照のみを拾う（配列添字や行番号の #N を除く）
refs=$(grep -rhoE '(ADR-[0-9]{3,4}|(Issue|issue|PR|pull)[ /#-]*#?[0-9]{2,5})' \
  --include='*.md' --include='*.yaml' . 2>/dev/null \
  | sort -u | head -10 | tr '\n' ' ')
echo "- 検出した参照: ${refs:-なし}"
echo "- ※ 自動抽出のため取りこぼし・誤検出があり得る。確実な参照は 1〜6節に書くこと"
