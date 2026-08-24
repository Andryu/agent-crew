#!/bin/bash
# harness アダプタ: Claude Code（headless）
# 使い方: claude.sh <workdir> <prompt-file> [model]
# 注意: claude -p はサブスク枠の扱いが将来変わりうる。ANTHROPIC_API_KEY は環境から外すこと。
set -euo pipefail
W="$1"; P="$2"; MODEL="${3:-sonnet}"
: "${CLAUDE_BIN:=claude}"
cd "$W"
env -u ANTHROPIC_API_KEY timeout "${HARNESS_TIMEOUT:-700}" "$CLAUDE_BIN" -p "$(cat "$P")" \
  --model "$MODEL" --permission-mode acceptEdits --allowedTools "Bash,Read,Edit,Write,Glob,Grep"
