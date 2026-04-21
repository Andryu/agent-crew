#!/bin/bash
# lessons_init.sh — _lessons.json 初期化スクリプト
#
# ~/.claude/_lessons.json が存在しない場合のみ templates/_lessons.json をコピーする。
# すでに存在する場合は何もしない（上書きしない）。
#
# 使い方:
#   lessons_init.sh [--templates-dir <path>]
#
# 環境変数:
#   LESSONS_FILE    lessons ファイルパス (default: ~/.claude/_lessons.json)
#   TEMPLATES_DIR   templates ディレクトリパス (default: このスクリプトの ../templates)

set -euo pipefail

LESSONS_FILE="${LESSONS_FILE:-$HOME/.claude/_lessons.json}"

# templates ディレクトリをスクリプトの相対位置から解決
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_TEMPLATES_DIR="$(cd "$SCRIPT_DIR/../templates" && pwd)"
TEMPLATES_DIR="${TEMPLATES_DIR:-$DEFAULT_TEMPLATES_DIR}"

TEMPLATE_SRC="$TEMPLATES_DIR/_lessons.json"

# ---------- 引数パース ----------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --templates-dir) TEMPLATES_DIR="$2"; TEMPLATE_SRC="$TEMPLATES_DIR/_lessons.json"; shift 2 ;;
    --help|-h)
      echo "Usage: lessons_init.sh [--templates-dir <path>]"
      echo ""
      echo "Initialize ~/.claude/_lessons.json from template if it does not exist."
      echo ""
      echo "Environment variables:"
      echo "  LESSONS_FILE   target path (default: ~/.claude/_lessons.json)"
      echo "  TEMPLATES_DIR  template directory (default: <repo>/templates)"
      exit 0
      ;;
    *) echo "ERROR: unknown option: '$1'" >&2; exit 1 ;;
  esac
done

# ---------- jq 確認 ----------

command -v jq >/dev/null 2>&1 \
  || { echo "ERROR: jq is not installed. Please install jq." >&2; exit 1; }

# ---------- テンプレート存在確認 ----------

[[ -f "$TEMPLATE_SRC" ]] \
  || { echo "ERROR: template not found: $TEMPLATE_SRC" >&2; exit 1; }

# ---------- 初期化 ----------

if [[ -f "$LESSONS_FILE" ]]; then
  echo "INFO: $LESSONS_FILE already exists. Skipping initialization."
  exit 0
fi

# 親ディレクトリ作成（~/.claude/ が無い場合）
mkdir -p "$(dirname "$LESSONS_FILE")"

cp "$TEMPLATE_SRC" "$LESSONS_FILE"
echo "INFO: Initialized $LESSONS_FILE from $TEMPLATE_SRC"
