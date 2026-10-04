#!/bin/bash
# harness アダプタ: Hermes Agent
# 使い方: hermes.sh <workdir> <prompt-file> [provider:model]
#   例: hermes.sh /work /prompt.md custom:gemma4-64k
#       hermes.sh /work /prompt.md opencode-go:mimo-v2.5
# 非対話は `hermes chat -q`。--yolo で承認プロンプトを出さず、--in で作業ディレクトリを渡す。
set -euo pipefail
W="$1"; P="$2"; SPEC="${3:-custom:gemma4-64k}"
PROVIDER="${SPEC%%:*}"; MODEL="${SPEC#*:}"
: "${HERMES_BIN:=hermes}"
cd "$W"
timeout "${HARNESS_TIMEOUT:-1200}" "$HERMES_BIN" chat \
  -q "$(cat "$P")" \
  --provider "custom:local" --model "$MODEL" \
  --in "$W" --yolo --cli \
  --max-turns "${HERMES_MAX_TURNS:-60}" \
  --ignore-user-config
