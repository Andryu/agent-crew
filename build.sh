#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="$SCRIPT_DIR/vendor/agency-agents"
OVERLAYS_DIR="$SCRIPT_DIR/overlays"
AGENTS_DIR="$SCRIPT_DIR/agents"

# vendorファイルからfrontmatter(最初の---...---ブロック)を除去して本文だけ返す
strip_frontmatter() {
  awk 'BEGIN{n=0} /^---$/{n++; next} n>=2{print}' "$1"
}

build_agent() {
  local role=$1
  local vendor_file=$2
  local header="$OVERLAYS_DIR/${role}.header.md"
  local footer="$OVERLAYS_DIR/${role}.footer.md"
  local output="$AGENTS_DIR/${role}.md"
  local vendor_path="$VENDOR_DIR/$vendor_file"

  if [[ ! -f "$vendor_path" ]]; then
    echo "  [SKIP] vendor not found: $vendor_file"
    return 1
  fi
  if [[ ! -f "$header" ]]; then
    echo "  [SKIP] header not found: $header"
    return 1
  fi

  # header + vendor本文 + footer + 共通キュープロトコル → 出力
  cat "$header" > "$output"
  echo "" >> "$output"
  strip_frontmatter "$vendor_path" >> "$output"
  if [[ -f "$footer" ]]; then
    echo "" >> "$output"
    cat "$footer" >> "$output"
  fi
  if [[ -f "$OVERLAYS_DIR/_queue_protocol.md" ]]; then
    cat "$OVERLAYS_DIR/_queue_protocol.md" >> "$output"
  fi

  echo "  [OK] $role → $output"
}

# pm, engineer-go はvendorを使わないので、共通キュープロトコルだけ追記
append_queue_protocol_to_native() {
  local role=$1
  local file="$AGENTS_DIR/${role}.md"
  if [[ ! -f "$file" ]]; then
    echo "  [SKIP] native agent not found: $file"
    return
  fi
  if grep -q "タスクキュー更新プロトコル（全エージェント共通）" "$file"; then
    echo "  [SKIP] $role already has queue protocol"
    return
  fi
  cat "$OVERLAYS_DIR/_queue_protocol.md" >> "$file"
  echo "  [OK] $role: 共通キュープロトコルを追記"
}

echo "=== agent-crew build ==="
echo ""

build_agent architect   "engineering/engineering-software-architect.md" || true
build_agent qa          "engineering/engineering-code-reviewer.md"         || true
build_agent ux-designer "design/design-ux-architect.md"                    || true

# vendor合成なしのエージェント（独自定義または未overlay）にはキュープロトコルだけ追記
append_queue_protocol_to_native pm
append_queue_protocol_to_native engineer-go
append_queue_protocol_to_native qa
append_queue_protocol_to_native ux-designer

# .claude/agents/ にデプロイ
if [[ -d "$SCRIPT_DIR/.claude/agents" ]]; then
  cp "$AGENTS_DIR"/*.md "$SCRIPT_DIR/.claude/agents/"
  echo "  [DEPLOY] .claude/agents/ に反映"
fi

echo ""
echo "=== done ==="
