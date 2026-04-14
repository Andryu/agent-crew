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
# idempotent: 古いプロトコル以降をstripしてから再追記する
append_queue_protocol_to_native() {
  local role=$1
  local file="$AGENTS_DIR/${role}.md"
  if [[ ! -f "$file" ]]; then
    echo "  [SKIP] native agent not found: $file"
    return
  fi
  # 既存プロトコルをstrip（マーカー行以降を削除、末尾の空行と --- も掃除）
  if grep -q "タスクキュー更新プロトコル（全エージェント共通）" "$file"; then
    awk '/^## タスクキュー更新プロトコル（全エージェント共通）/{exit} {print}' "$file" > "$file.tmp"
    # 末尾の空行と "---" 区切り線を連続で削除
    awk '
      { lines[NR] = $0 }
      END {
        last = NR
        while (last > 0 && (lines[last] == "" || lines[last] == "---")) last--
        for (i = 1; i <= last; i++) print lines[i]
      }
    ' "$file.tmp" > "$file.tmp2"
    mv "$file.tmp2" "$file"
    rm -f "$file.tmp"
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

# preflightチェックを Riku と Sora に追加（環境依存ツールを使うエージェント）
append_preflight() {
  local role=$1
  local file="$AGENTS_DIR/${role}.md"
  if [[ ! -f "$file" ]]; then return; fi
  # idempotent
  if grep -q "環境チェック（preflight）" "$file"; then
    awk '/^## 環境チェック（preflight）/{exit} {print}' "$file" > "$file.tmp"
    awk '
      { lines[NR] = $0 }
      END {
        last = NR
        while (last > 0 && (lines[last] == "" || lines[last] == "---")) last--
        for (i = 1; i <= last; i++) print lines[i]
      }
    ' "$file.tmp" > "$file.tmp2"
    mv "$file.tmp2" "$file"
    rm -f "$file.tmp"
  fi
  cat "$OVERLAYS_DIR/_preflight.md" >> "$file"
  echo "  [OK] $role: preflight を追記"
}
append_preflight engineer-go
append_preflight qa

# .claude/agents/ にデプロイ
if [[ -d "$SCRIPT_DIR/.claude/agents" ]]; then
  cp "$AGENTS_DIR"/*.md "$SCRIPT_DIR/.claude/agents/"
  echo "  [DEPLOY] .claude/agents/ に反映"
fi

echo ""
echo "=== done ==="
