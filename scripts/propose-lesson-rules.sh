#!/usr/bin/env bash
# propose-lesson-rules.sh — lessons -> agent .md 自動 PR 提案スクリプト
#
# 使い方:
#   scripts/propose-lesson-rules.sh [--dry-run] [--min-priority <N>]
#
# 説明:
#   ~/.claude/_lessons.json から priority_score >= MIN_PRIORITY かつ
#   status が open/proposed/issue_created の lesson を抽出し、
#   対象エージェント .md の末尾「禁止パターン」セクションへ差分を追記して
#   Draft PR を作成する。
#
#   --dry-run 時は git 操作・PR 作成を行わず差分のみ STDOUT に出力する。
#
# 環境変数:
#   LESSONS_FILE   lessons ファイルパス (default: ~/.claude/_lessons.json)

set -euo pipefail

# ---------- 設定 ----------

LESSONS_FILE="${LESSONS_FILE:-$HOME/.claude/_lessons.json}"
MIN_PRIORITY=4
DRY_RUN=false
AGENTS_DIR=".claude/agents"
TODAY=$(date +%Y-%m-%d)
BRANCH_NAME="fix/lesson-rules-$(date +%Y%m%d)"

# ---------- 引数パース ----------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --min-priority)
      MIN_PRIORITY="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--dry-run] [--min-priority <N>]" >&2
      exit 1
      ;;
  esac
done

# ---------- ユーティリティ ----------

log() { echo "[propose-lesson-rules] $*"; }
warn() { echo "[propose-lesson-rules] WARN: $*" >&2; }

# category -> エージェントファイル マッピング
agent_for_category() {
  local category="$1"
  case "$category" in
    process|planning|communication) echo "pm.md" ;;
    reliability|implementation|tooling) echo "engineer-go.md" ;;
    qa) echo "qa.md" ;;
    architecture) echo "architect.md" ;;
    *) echo "pm.md" ;;  # 不明な category は pm.md へ
  esac
}

# ---------- 前提チェック ----------

if [[ ! -f "$LESSONS_FILE" ]]; then
  log "lessons file not found: $LESSONS_FILE"
  log "No lessons to propose."
  exit 0
fi

if [[ ! -d "$AGENTS_DIR" ]]; then
  warn "agents dir not found: $AGENTS_DIR"
  exit 1
fi

# ---------- 対象 lesson 抽出 ----------

log "Extracting lessons with priority_score >= $MIN_PRIORITY ..."

LESSONS_JSON=$(jq -c --argjson min "$MIN_PRIORITY" '
  .lessons[]
  | select(
      .priority_score >= $min
      and (
        .status == null
        or .status == "open"
        or .status == "proposed"
        or .status == "issue_created"
      )
    )
' "$LESSONS_FILE" 2>/dev/null || echo "")

if [[ -z "$LESSONS_JSON" ]]; then
  log "No actionable lessons found (priority >= $MIN_PRIORITY, status open/proposed/issue_created)."
  exit 0
fi

LESSON_COUNT=$(echo "$LESSONS_JSON" | grep -c '^{' || echo 0)
log "Found $LESSON_COUNT lesson(s) to propose."

# ---------- エージェントごとに差分を生成 ----------

# エージェントファイルごとの追記内容を一時ファイルで管理
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

while IFS= read -r lesson; do
  [[ -z "$lesson" ]] && continue
  # JSON 行でなければスキップ
  [[ "$lesson" != \{* ]] && continue

  id=$(echo "$lesson" | jq -r '.id // "unknown"')
  category=$(echo "$lesson" | jq -r '.category // "process"')
  priority=$(echo "$lesson" | jq -r '.priority_score // 0')
  sprint=$(echo "$lesson" | jq -r '.sprint // "unknown"')
  description=$(echo "$lesson" | jq -r '.description // ""' | cut -c1-120)
  action=$(echo "$lesson" | jq -r '.action // ""')

  agent_file=$(agent_for_category "$category")
  agent_path="$AGENTS_DIR/$agent_file"

  if [[ ! -f "$agent_path" ]]; then
    warn "Agent file not found: $agent_path (skipping lesson $id)"
    continue
  fi

  # 既存ファイルにこの lesson_id が含まれているか確認（重複防止）
  if grep -q "$id" "$agent_path" 2>/dev/null; then
    log "  SKIP: $id already present in $agent_file"
    continue
  fi

  # エージェントごとの一時ファイルに追記エントリを蓄積
  work_file="$WORK_DIR/$agent_file"
  cat >> "$work_file" <<ENTRY

### $id
- **lesson**: $description
- **禁止行動**: $action
- **priority**: $priority / sprint: $sprint
ENTRY

  log "  + $id -> $agent_file"

done <<< "$LESSONS_JSON"

# 追記対象ファイルのリスト
MODIFIED_AGENTS=()
for work_file in "$WORK_DIR"/*.md; do
  [[ -f "$work_file" ]] || continue
  MODIFIED_AGENTS+=("$(basename "$work_file")")
done

# 追記対象がなければ終了
if [[ ${#MODIFIED_AGENTS[@]} -eq 0 ]]; then
  log "All lessons are already reflected in agent files. Nothing to propose."
  exit 0
fi

# ---------- dry-run: 差分のみ表示して終了 ----------

if [[ "$DRY_RUN" == "true" ]]; then
  log "--- DRY RUN MODE: no files modified, no PR created ---"
  for agent_file in "${MODIFIED_AGENTS[@]}"; do
    work_file="$WORK_DIR/$agent_file"
    echo ""
    echo "=== $agent_file ==="
    echo "## 禁止パターン（lessons より自動提案）"
    echo ""
    echo "> 最終更新: $TODAY"
    cat "$work_file"
  done
  exit 0
fi

# ---------- ブランチ作成 ----------

# 既存ブランチの確認
if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME" 2>/dev/null; then
  warn "Branch '$BRANCH_NAME' already exists. Skipping PR creation to avoid overwrite."
  warn "Delete the branch manually if you want to re-run: git branch -D $BRANCH_NAME"
  exit 1
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
log "Creating branch: $BRANCH_NAME (from $CURRENT_BRANCH)"
git checkout -b "$BRANCH_NAME"

# ---------- エージェントファイルへの追記 ----------

MODIFIED_FILES=()

for agent_file in "${MODIFIED_AGENTS[@]}"; do
  agent_path="$AGENTS_DIR/$agent_file"
  work_file="$WORK_DIR/$agent_file"

  # 「禁止パターン」セクションが既存かどうか確認
  if grep -q "^## 禁止パターン" "$agent_path" 2>/dev/null; then
    # 既存セクションの末尾に追記
    cat "$work_file" >> "$agent_path"
    log "Appended to existing section in $agent_file"
  else
    # セクションごと末尾に追加
    {
      printf '\n---\n\n'
      printf '## 禁止パターン（lessons より自動提案）\n\n'
      printf '> このセクションは `scripts/propose-lesson-rules.sh` によって生成されました。\n'
      printf '> オーナーのレビュー後にマージしてください。\n'
      printf '> 最終更新: %s\n' "$TODAY"
      cat "$work_file"
    } >> "$agent_path"
    log "Added new section to $agent_file"
  fi

  MODIFIED_FILES+=("$agent_path")
done

# ---------- コミット ----------

log "Committing changes..."
git add "${MODIFIED_FILES[@]}"
git commit -m "$(cat <<'EOF'
fix: lessons から agent .md へ禁止パターンを自動提案

scripts/propose-lesson-rules.sh により生成。
priority_score >= 4 の未対処 lesson を対象エージェント .md に追記。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"

git push -u origin "$BRANCH_NAME"

# ---------- Draft PR 作成 ----------

log "Creating Draft PR..."

FILES_LIST=""
for f in "${MODIFIED_FILES[@]}"; do
  FILES_LIST="${FILES_LIST}- \`$f\`
"
done

PR_URL=$(gh pr create \
  --draft \
  --title "fix: lessons から agent .md へ禁止パターンを自動提案 ($TODAY)" \
  --body "## Summary

- \`scripts/propose-lesson-rules.sh\` により \`~/.claude/_lessons.json\` から priority_score >= $MIN_PRIORITY の未対処 lesson を抽出
- 対象エージェント .md の「禁止パターン」セクションへ自動追記

## 変更ファイル

${FILES_LIST}
## レビュー手順

1. 追記された禁止パターンの内容を確認する
2. 不要なエントリは削除してからマージする
3. マージ後、対応する lesson の status を \`implemented\` に更新する

## Test plan

- [x] 追記内容が既存セクションと重複していないこと（スクリプトが重複チェック済み）
- [ ] 追記されたルールが実際の lesson 内容と一致していること（目視確認）

🤖 Generated with [Claude Code](https://claude.com/claude-code)")

log "Draft PR created: $PR_URL"
echo ""
echo "PR URL: $PR_URL"

# 元のブランチに戻る
git checkout "$CURRENT_BRANCH"
log "Returned to branch: $CURRENT_BRANCH"
