#!/bin/bash
# harness アダプタ: Hermes Agent（ローカル or OpenCode Go 等）
# 使い方: hermes.sh <workdir> <prompt-file> [provider:model]
# 例: hermes.sh /work /prompt.md custom:gemma4-64k
#     hermes.sh /work /prompt.md opencode-go:mimo-v2.5
set -euo pipefail
W="$1"; P="$2"; SPEC="${3:-custom:gemma4-64k}"
PROVIDER="${SPEC%%:*}"; MODEL="${SPEC#*:}"
: "${HERMES_BIN:=hermes}"
cd "$W"
timeout "${HARNESS_TIMEOUT:-900}" "$HERMES_BIN" chat \
  --provider "$PROVIDER" --model "$MODEL" --no-interactive "$(cat "$P")"
