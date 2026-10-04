#!/bin/bash
# harness アダプタ: Codex CLI（ChatGPT Plus）
# 使い方: codex.sh <workdir> <prompt-file> [model]
set -euo pipefail
W="$1"; P="$2"; MODEL="${3:-gpt-5.6-sol}"
: "${CODEX_BIN:=/opt/homebrew/bin/codex}"
: "${CODEX_HOME:=$HOME/.codex}"
export CODEX_HOME
cd "$W"
timeout "${HARNESS_TIMEOUT:-700}" "$CODEX_BIN" exec \
  --sandbox workspace-write --skip-git-repo-check \
  -c model="$MODEL" -c model_reasoning_effort="${CODEX_EFFORT:-medium}" \
  "$(cat "$P")"
