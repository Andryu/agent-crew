#!/bin/bash
# scripts/lessons-to-vault.sh
# 教訓（~/.claude/_lessons.json）を知識vaultの inbox へ自動転記する
#
# 高優先度（priority_score >= MIN_PRIORITY）の教訓をスプリント単位でグループ化し、
# $VAULT_DIR/inbox/agent-crew-lessons-<sprint>.md として書き出す。
# 出力ファイルが既に存在するスプリントはスキップする（再実行しても重複生成しない）。
#
# 環境変数:
#   VAULT_DIR      知識vaultのルート (default: $HOME/Workspace/Obsidian)
#   LESSONS_FILE   教訓ファイルパス (default: $HOME/.claude/_lessons.json)
#   MIN_PRIORITY   転記対象の最小 priority_score (default: 4)
#
# フックチェーン（SubagentStop 等）から呼ばれても他の処理に影響しないよう、
# 前提条件が満たされない場合も含め、いかなる場合も exit 0 とする。

set -uo pipefail

VAULT_DIR="${VAULT_DIR:-$HOME/Workspace/Obsidian}"
LESSONS_FILE="${LESSONS_FILE:-$HOME/.claude/_lessons.json}"
MIN_PRIORITY="${MIN_PRIORITY:-4}"

warn() {
  echo "WARN: lessons-to-vault.sh: $*" >&2
}

# ---------- 前提チェック（満たさない場合は警告のみで exit 0） ----------

if ! command -v jq >/dev/null 2>&1; then
  warn "jq not found. スキップします。"
  exit 0
fi

if [[ ! -f "$LESSONS_FILE" ]]; then
  warn "$LESSONS_FILE が見つかりません。スキップします。"
  exit 0
fi

if [[ ! -d "$VAULT_DIR" ]]; then
  warn "vault ディレクトリ $VAULT_DIR が見つかりません。スキップします。"
  exit 0
fi

if ! [[ "$MIN_PRIORITY" =~ ^[0-9]+$ ]]; then
  warn "MIN_PRIORITY は数値で指定してください（got: '$MIN_PRIORITY'）。スキップします。"
  exit 0
fi

INBOX_DIR="$VAULT_DIR/inbox"
mkdir -p "$INBOX_DIR" 2>/dev/null || { warn "$INBOX_DIR を作成できません。スキップします。"; exit 0; }

# ---------- 対象スプリントの抽出 ----------

SPRINTS=$(jq -r --argjson mp "$MIN_PRIORITY" '
  [.lessons[]? | select((.priority_score // 0) >= $mp) | .sprint]
  | map(select(. != null and . != ""))
  | unique
  | .[]
' "$LESSONS_FILE" 2>/dev/null)

if [[ -z "$SPRINTS" ]]; then
  echo "lessons-to-vault: MIN_PRIORITY=$MIN_PRIORITY 以上の教訓が見つかりませんでした。"
  exit 0
fi

TODAY=$(date +%Y-%m-%d)
GENERATED=0
SKIPPED=0

while IFS= read -r SPRINT; do
  [[ -z "$SPRINT" ]] && continue

  OUT_FILE="$INBOX_DIR/agent-crew-lessons-${SPRINT}.md"

  # 冪等性: 既に生成済みのスプリントはスキップ
  if [[ -f "$OUT_FILE" ]]; then
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  LESSON_LINES=$(jq -c --arg sprint "$SPRINT" --argjson mp "$MIN_PRIORITY" '
    .lessons[]?
    | select(.sprint == $sprint and ((.priority_score // 0) >= $mp))
    | {id, priority_score, category, type, description, action}
  ' "$LESSONS_FILE" 2>/dev/null)

  [[ -z "$LESSON_LINES" ]] && continue

  {
    echo "---"
    echo "title: agent-crew ${SPRINT} の教訓候補"
    echo "type: inbox"
    echo "tags: [agent-crew, lessons]"
    echo "source: ~/.claude/_lessons.json から自動転記"
    echo "updated: ${TODAY}"
    echo "---"
    echo ""
    echo "# agent-crew ${SPRINT} の教訓候補"
    echo ""
  } > "$OUT_FILE"

  while IFS= read -r LESSON; do
    [[ -z "$LESSON" ]] && continue
    ID=$(jq -r '.id // "unknown"' <<< "$LESSON")
    PRIORITY=$(jq -r '.priority_score // "?"' <<< "$LESSON")
    CATEGORY=$(jq -r '.category // "unknown"' <<< "$LESSON")
    TYPE=$(jq -r '.type // "unknown"' <<< "$LESSON")
    DESCRIPTION=$(jq -r '.description // ""' <<< "$LESSON")
    ACTION=$(jq -r '.action // ""' <<< "$LESSON")

    {
      echo "## ${ID}"
      echo "- priority_score: ${PRIORITY}"
      echo "- category/type: ${CATEGORY} / ${TYPE}"
      echo "- description: ${DESCRIPTION}"
      if [[ -n "$ACTION" ]]; then
        echo "- action: ${ACTION}"
      fi
      echo ""
    } >> "$OUT_FILE"
  done <<< "$LESSON_LINES"

  GENERATED=$((GENERATED + 1))
done <<< "$SPRINTS"

echo "lessons-to-vault: 生成 ${GENERATED} 件 / スキップ（既存） ${SKIPPED} 件"

exit 0
