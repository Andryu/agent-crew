#!/bin/bash
# lessons.sh — _lessons.json 書き込みユーティリティ
#
# 使い方:
#   lessons.sh add \
#     --project <project> \
#     --sprint <sprint> \
#     --category <category> \
#     --severity <1-3> \
#     --frequency <1-3> \
#     --description "<description>" \
#     --action "<action>" \
#     [--type <failure|success|observation>] \
#     [--evidence "<evidence1>" --evidence "<evidence2>" ...] \
#     [--tags "<tag1>" --tags "<tag2>" ...] \
#     [--issue-url <url>] \
#     [--supersedes <id>]
#
# 環境変数:
#   LESSONS_FILE   lessons ファイルパス (default: ~/.claude/_lessons.json)
#   LOCK_FILE      flock 用ロックファイル (default: ~/.claude/_lessons.json.lock)
#   LOCK_TIMEOUT   ロック待機タイムアウト秒数 (default: 10)

set -euo pipefail

LESSONS_FILE="${LESSONS_FILE:-$HOME/.claude/_lessons.json}"
LOCK_FILE="${LOCK_FILE:-$HOME/.claude/_lessons.json.lock}"
LOCK_TIMEOUT="${LOCK_TIMEOUT:-10}"

# ---------- ユーティリティ ----------

usage() {
  cat >&2 <<'EOF'
Usage: lessons.sh add [OPTIONS]

Options:
  --project      プロジェクト名 (必須)
  --sprint       スプリント識別子 例: sprint-02 (必須)
  --category     カテゴリ: planning|implementation|qa|communication|tooling|process|architecture (必須)
  --severity     影響の深刻さ 1-3 (必須)
  --frequency    発生頻度 1-3 (必須)
  --description  何が起きたか・何を学んだか (必須)
  --action       次回取るべきアクション (必須)
  --type         failure|success|observation (省略時: failure)
  --evidence     観察の根拠 (複数指定可)
  --tags         自由タグ (複数指定可)
  --issue-url    対応 GitHub Issue の URL
  --supersedes   改訂対象の旧 lesson ID
  --help         このヘルプを表示
EOF
  exit 1
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

# ---------- 引数パース ----------

CMD="${1:-}"
shift || true

if [[ "$CMD" == "--help" || "$CMD" == "-h" || -z "$CMD" ]]; then
  usage
fi

if [[ "$CMD" != "add" ]]; then
  die "unknown command: '$CMD'. Only 'add' is supported."
fi

PROJECT=""
SPRINT=""
CATEGORY=""
SEVERITY=""
FREQUENCY=""
DESCRIPTION=""
ACTION=""
TYPE="failure"
ISSUE_URL="null"
SUPERSEDES="null"
EVIDENCE_ITEMS=()
TAG_ITEMS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)     PROJECT="$2";      shift 2 ;;
    --sprint)      SPRINT="$2";       shift 2 ;;
    --category)    CATEGORY="$2";     shift 2 ;;
    --severity)    SEVERITY="$2";     shift 2 ;;
    --frequency)   FREQUENCY="$2";    shift 2 ;;
    --description) DESCRIPTION="$2";  shift 2 ;;
    --action)      ACTION="$2";       shift 2 ;;
    --type)        TYPE="$2";         shift 2 ;;
    --issue-url)   ISSUE_URL="\"$2\""; shift 2 ;;
    --supersedes)  SUPERSEDES="\"$2\""; shift 2 ;;
    --evidence)    EVIDENCE_ITEMS+=("$2"); shift 2 ;;
    --tags)        TAG_ITEMS+=("$2"); shift 2 ;;
    --help|-h)     usage ;;
    *) die "unknown option: '$1'" ;;
  esac
done

# ---------- バリデーション ----------

[[ -n "$PROJECT" ]]     || die "--project is required"
[[ -n "$SPRINT" ]]      || die "--sprint is required"
[[ -n "$CATEGORY" ]]    || die "--category is required"
[[ -n "$SEVERITY" ]]    || die "--severity is required"
[[ -n "$FREQUENCY" ]]   || die "--frequency is required"
[[ -n "$DESCRIPTION" ]] || die "--description is required"
[[ -n "$ACTION" ]]      || die "--action is required"

# sprint パターン検証
[[ "$SPRINT" =~ ^sprint-[0-9]+$ ]] \
  || die "--sprint must match 'sprint-NNN' (e.g. sprint-02), got: '$SPRINT'"

# category 検証
VALID_CATEGORIES="planning implementation qa communication tooling process architecture"
echo "$VALID_CATEGORIES" | tr ' ' '\n' | grep -qx "$CATEGORY" \
  || die "--category must be one of: $VALID_CATEGORIES, got: '$CATEGORY'"

# severity / frequency 数値範囲検証
[[ "$SEVERITY" =~ ^[1-3]$ ]] \
  || die "--severity must be 1, 2, or 3, got: '$SEVERITY'"
[[ "$FREQUENCY" =~ ^[1-3]$ ]] \
  || die "--frequency must be 1, 2, or 3, got: '$FREQUENCY'"

# type 検証
[[ "$TYPE" =~ ^(failure|success|observation)$ ]] \
  || die "--type must be failure, success, or observation, got: '$TYPE'"

# description / action 最低文字数
[[ ${#DESCRIPTION} -ge 10 ]] \
  || die "--description must be at least 10 characters"
[[ ${#ACTION} -ge 5 ]] \
  || die "--action must be at least 5 characters"

# ファイル存在確認（初期化済みか）
[[ -f "$LESSONS_FILE" ]] \
  || die "$LESSONS_FILE does not exist. Run lessons_init.sh first."

# ---------- jq 確認 ----------

command -v jq >/dev/null 2>&1 \
  || die "jq is not installed. Please install jq."

# ---------- ロック & アトミック書き込み ----------

# flock が使えない環境（macOS では util-linux の flock が無い場合がある）への対応:
# lockfile コマンドまたは mkdir を fallback として使う
_do_add() {
  local existing next_seq id priority_score created_at evidence_json tags_json new_entry updated tmp

  existing=$(cat "$LESSONS_FILE")

  # ID 採番: project-sprint-category プレフィックスで既存の最大連番を探す
  local id_prefix="${PROJECT}-${SPRINT}-${CATEGORY}"
  next_seq=$(
    echo "$existing" \
    | jq -r --arg prefix "$id_prefix" \
        '.lessons[]
         | select(.id | startswith($prefix))
         | .id
         | split("-")
         | last
         | tonumber' \
    | sort -n \
    | tail -1
  )
  if [[ -z "$next_seq" ]]; then
    next_seq=1
  else
    next_seq=$((next_seq + 1))
  fi

  id=$(printf "%s-%03d" "$id_prefix" "$next_seq")

  priority_score=$(( SEVERITY * FREQUENCY ))
  created_at=$(date -u +"%Y-%m-%dT%H:%M:%S+0000")

  # evidence 配列を JSON に変換
  if [[ ${#EVIDENCE_ITEMS[@]} -eq 0 ]]; then
    evidence_json="[]"
  else
    evidence_json=$(printf '%s\n' "${EVIDENCE_ITEMS[@]}" | jq -R . | jq -s .)
  fi

  # tags 配列を JSON に変換
  if [[ ${#TAG_ITEMS[@]} -eq 0 ]]; then
    tags_json="[]"
  else
    tags_json=$(printf '%s\n' "${TAG_ITEMS[@]}" | jq -R . | jq -s .)
  fi

  new_entry=$(jq -n \
    --arg id           "$id" \
    --arg project      "$PROJECT" \
    --arg sprint       "$SPRINT" \
    --arg category     "$CATEGORY" \
    --arg type         "$TYPE" \
    --argjson severity "$SEVERITY" \
    --argjson frequency "$FREQUENCY" \
    --argjson priority "$priority_score" \
    --arg description  "$DESCRIPTION" \
    --arg action       "$ACTION" \
    --argjson evidence "$evidence_json" \
    --argjson tags     "$tags_json" \
    --argjson issue_url "$ISSUE_URL" \
    --argjson supersedes "$SUPERSEDES" \
    --arg created_at   "$created_at" \
    '{
      id:              $id,
      project:         $project,
      sprint:          $sprint,
      category:        $category,
      type:            $type,
      severity_score:  $severity,
      frequency_score: $frequency,
      priority_score:  $priority,
      description:     $description,
      evidence:        $evidence,
      action:          $action,
      issue_url:       $issue_url,
      supersedes:      $supersedes,
      tags:            $tags,
      created_at:      $created_at,
      updated_at:      null
    }'
  )

  updated=$(echo "$existing" | jq --argjson entry "$new_entry" '.lessons += [$entry]')

  tmp=$(mktemp "${LESSONS_FILE}.tmp.XXXXXX")
  echo "$updated" > "$tmp"
  mv "$tmp" "$LESSONS_FILE"

  echo "$id"
}

# flock が使えるか確認（macOS の util-linux 版）
if command -v flock >/dev/null 2>&1; then
  # flock 経由でアトミック書き込み
  result=$(
    (
      flock -x -w "$LOCK_TIMEOUT" 200 || die "lock timeout (${LOCK_TIMEOUT}s). Another process may be writing."
      _do_add
    ) 200>"$LOCK_FILE"
  )
else
  # fallback: flock が無い場合は警告を出しつつ直接実行（シングルセッション想定）
  echo "WARN: flock not available. Running without file lock." >&2
  result=$(_do_add)
fi

echo "Added lesson: $result"
