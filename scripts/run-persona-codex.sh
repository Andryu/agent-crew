#!/bin/bash
# scripts/run-persona-codex.sh — personas/<role>.md をシステムプロンプトとして
# codex exec に注入し、非対話でタスクを実行する。
#
# 使い方: scripts/run-persona-codex.sh <role> "<task>" [-- codex exec への追加オプション]
#   例: scripts/run-persona-codex.sh pm "現在のスプリント状況を要約して" -- -s read-only
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

ROLE="${1:?usage: run-persona-codex.sh <role> <task> [-- codex exec オプション]}"
TASK="${2:?usage: run-persona-codex.sh <role> <task> [-- codex exec オプション]}"
shift 2
[[ "${1:-}" == "--" ]] && shift

PERSONA="$ROOT/personas/$ROLE.md"
[[ -f "$PERSONA" ]] || { echo "ERROR: persona not found: $PERSONA" >&2; exit 1; }

PROMPT="$(cat "$PERSONA")

---

## 今回のタスク（Codex 経由での非対話実行）

$TASK"

exec codex exec -C "$ROOT" -m gpt-5.6-sol -c model_reasoning_effort=medium "$@" "$PROMPT"
