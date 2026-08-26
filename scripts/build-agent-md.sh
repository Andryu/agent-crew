#!/bin/bash
# scripts/build-agent-md.sh — ハーネス非依存のペルソナ本体と Claude Code 用メタデータから
# .claude/agents/<role>.md を再生成する。
#
# 正本は2つに分かれている:
#   personas/<role>.md                     ペルソナ本体（ハーネス非依存。Codex 等でもそのまま使う）
#   .claude/agents/<role>.frontmatter.yaml Claude Code 固有メタデータ（tools/model 等）
#
# 使い方: scripts/build-agent-md.sh <role> [<role> ...]
#         scripts/build-agent-md.sh --all
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

build_one() {
  local role="$1"
  local persona="$ROOT/personas/$role.md"
  local meta="$ROOT/.claude/agents/$role.frontmatter.yaml"
  local out="$ROOT/.claude/agents/$role.md"

  [[ -f "$persona" ]] || { echo "ERROR: not found: $persona" >&2; return 1; }
  [[ -f "$meta" ]] || { echo "ERROR: not found: $meta" >&2; return 1; }

  {
    echo "---"
    cat "$meta"
    echo "---"
    echo
    cat "$persona"
  } > "$out"
  echo "OK: built $out"
}

if [[ "${1:-}" == "--all" ]]; then
  for meta in "$ROOT"/.claude/agents/*.frontmatter.yaml; do
    [[ -f "$meta" ]] || continue
    build_one "$(basename "$meta" .frontmatter.yaml)"
  done
else
  [[ $# -ge 1 ]] || { echo "usage: $0 <role> [<role> ...] | --all" >&2; exit 1; }
  for role in "$@"; do
    build_one "$role"
  done
fi
