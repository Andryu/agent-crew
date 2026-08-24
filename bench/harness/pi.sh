#!/bin/bash
# harness アダプタ: pi（earendil-works/pi coding agent）
# 使い方: pi.sh <workdir> <prompt-file> [provider/model]
#   例: pi.sh /work /prompt.md openai-codex/gpt-5.6-sol
# 非対話は -p。システムプロンプト＋ツール定義が軽い（read/write/edit/bash の4つ）のが特徴。
# 認証は事前に対話モードで `/login` → ChatGPT Plus/Pro (Codex)。~/.pi/agent/auth.json に保存される。
set -euo pipefail
W="$1"; P="$2"; SPEC="${3:-}"
: "${PI_BIN:=pi}"
cd "$W"
ARGS=(-p)
if [[ -n "$SPEC" ]]; then
  if [[ "$SPEC" == */* ]]; then
    ARGS+=(--provider "${SPEC%%/*}" --model "${SPEC#*/}")
  else
    ARGS+=(--model "$SPEC")
  fi
fi
timeout "${HARNESS_TIMEOUT:-700}" "$PI_BIN" "${ARGS[@]}" "$(cat "$P")"
