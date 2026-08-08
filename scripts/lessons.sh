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
#     [--status <proposed|issue_created|implemented|verified|dismissed>] \
#     [--scope <project|global|stack>] \
#     [--stack <stack>] \
#     [--evidence "<evidence1>" --evidence "<evidence2>" ...] \
#     [--tags "<tag1>" --tags "<tag2>" ...] \
#     [--issue-url <url>] \
#     [--supersedes <id>] \
#     [--recurrence-condition "<condition>"] \
#     [--enforcement <code|prompt|process>] \
#     [--source-repo <url>]
#
#   lessons.sh set-status <id> <proposed|issue_created|implemented|verified|dismissed>
#   lessons.sh promote <id> <project|global|stack> [<stack>]
#   lessons.sh verify-check <current-sprint> [--recurred <id>]...
#
#   verify-check: 効果検証（learning-loop-verification-proposal.md L0-2）。
#     過去スプリントのルール書き出し対象 lesson（type=failure, priority>=3,
#     status が proposed/issue_created/implemented）について:
#       --recurred で指定された lesson → verification_streak を 0 にリセットし
#         last_recurrence_sprint を現スプリントに更新（ルール無効 = 機械化候補）
#       それ以外 → verification_streak を +1。streak >= 2 に達したら
#         status を verified へ自動遷移する
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
  cat >&2 <<'HELP_EOF'
Usage: lessons.sh <command> [OPTIONS]

Commands:
  add            新しい lesson を追加する
  set-status     既存 lesson のステータスを更新する
  promote        既存 lesson の scope (と stack) を更新する

add options:
  --project      プロジェクト名 (必須)
  --sprint       スプリント識別子 例: sprint-02 (必須)
  --category     カテゴリ: planning|implementation|qa|communication|tooling|process|architecture (必須)
  --severity     影響の深刻さ 1-3 (必須)
  --frequency    発生頻度 1-3 (必須)
  --description  何が起きたか・何を学んだか (必須)
  --action       次回取るべきアクション (必須)
  --type         failure|success|observation (省略時: failure)
  --status       proposed|issue_created|implemented|verified|dismissed (省略時: proposed)
  --scope        project|global|stack (省略時: project)
  --stack        スタック名 (scope=stack時に必須)
  --evidence     観察の根拠 (複数指定可)
  --tags         自由タグ (複数指定可)
  --issue-url    対応 GitHub Issue の URL
  --supersedes   改訂対象の旧 lesson ID
  --recurrence-condition
                 再発検知条件: 何が観測されなくなったら効いたと言えるか
                 (type=failure かつ priority_score>=3 では必須、10文字以上)
  --enforcement  code|prompt|process (省略時: prompt)
                 code = script/lint/hook で強制済み。プロンプト書き出し対象外になる
  --source-repo  由来リポジトリURL (省略時: git remote get-url origin。
                 SSH形式は HTTPS 形式へ自動正規化される)
  --help         このヘルプを表示

set-status args:
  <id>           lesson ID (必須)
  <status>       proposed|issue_created|implemented|verified|dismissed (必須)

promote args:
  <id>           lesson ID (必須)
  <scope>        project|global|stack (必須)
  <stack>        スタック名 (scope=stack時に必須)

verify-check args:
  <current-sprint>  現スプリント識別子 例: sprint-28 (必須)
  --recurred <id>   今スプリントで同型再発が観察された lesson ID (複数指定可)
HELP_EOF
  exit 1
}

# source_repo 正規化: SSH形式 (git@github.com:owner/repo.git) を
# HTTPS形式 (https://github.com/owner/repo) に統一する。
# agent-crew-sprint-27-tooling-001 の恒久対応（enforcement: code）。
normalize_source_repo() {
  local url="$1"
  url="${url%.git}"
  if [[ "$url" =~ ^git@([^:]+):(.+)$ ]]; then
    url="https://${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  elif [[ "$url" =~ ^ssh://git@([^/]+)/(.+)$ ]]; then
    url="https://${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  fi
  echo "$url"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

acquire_mkdir_lock() {
  local lock_dir="${LESSONS_FILE}.lock.d"
  local wait_time=0
  while ! mkdir "$lock_dir" 2>/dev/null; do
    sleep 1
    wait_time=$((wait_time + 1))
    if [[ $wait_time -ge $LOCK_TIMEOUT ]]; then
      die "lock timeout (${LOCK_TIMEOUT}s). Another process may be writing."
    fi
  done
}

release_mkdir_lock() {
  local lock_dir="${LESSONS_FILE}.lock.d"
  rm -rf "$lock_dir"
}

# ---------- 引数パース ----------

CMD="${1:-}"
shift || true

if [[ "$CMD" == "--help" || "$CMD" == "-h" || -z "$CMD" ]]; then
  usage
fi

if [[ "$CMD" != "add" && "$CMD" != "set-status" && "$CMD" != "promote" && "$CMD" != "verify-check" ]]; then
  die "unknown command: '$CMD'. Use 'add', 'set-status', 'promote', or 'verify-check'."
fi

SET_STATUS_ID=""
SET_STATUS_VAL=""
PROMOTE_ID=""
PROMOTE_SCOPE=""
PROMOTE_STACK="null"
VERIFY_SPRINT=""
RECURRED_IDS=()

if [[ "$CMD" == "set-status" ]]; then
  SET_STATUS_ID="${1:-}"
  SET_STATUS_VAL="${2:-}"
elif [[ "$CMD" == "promote" ]]; then
  PROMOTE_ID="${1:-}"
  PROMOTE_SCOPE="${2:-}"
  if [[ "$PROMOTE_SCOPE" == "stack" ]]; then
    PROMOTE_STACK="\"${3:-}\""
  fi
elif [[ "$CMD" == "verify-check" ]]; then
  VERIFY_SPRINT="${1:-}"
  shift || true
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --recurred) RECURRED_IDS+=("$2"); shift 2 ;;
      --help|-h)  usage ;;
      *) die "unknown option for verify-check: '$1'" ;;
    esac
  done
fi

PROJECT=""
SPRINT=""
CATEGORY=""
SEVERITY=""
FREQUENCY=""
DESCRIPTION=""
ACTION=""
TYPE="failure"
STATUS="proposed"
SCOPE="project"
STACK="null"
ISSUE_URL="null"
SUPERSEDES="null"
RECURRENCE_CONDITION=""
ENFORCEMENT="prompt"
SOURCE_REPO=""
EVIDENCE_ITEMS=()
TAG_ITEMS=()

if [[ "$CMD" == "add" ]]; then
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
    --status)      STATUS="$2";       shift 2 ;;
    --scope)       SCOPE="$2";        shift 2 ;;
    --stack)       STACK="\"$2\"";    shift 2 ;;
    --issue-url)   ISSUE_URL="\"$2\""; shift 2 ;;
    --supersedes)  SUPERSEDES="\"$2\""; shift 2 ;;
    --recurrence-condition) RECURRENCE_CONDITION="$2"; shift 2 ;;
    --enforcement) ENFORCEMENT="$2";  shift 2 ;;
    --source-repo) SOURCE_REPO="$2";  shift 2 ;;
    --evidence)    EVIDENCE_ITEMS+=("$2"); shift 2 ;;
    --tags)        TAG_ITEMS+=("$2"); shift 2 ;;
    --help|-h)     usage ;;
    *) die "unknown option: '$1'" ;;
  esac
done
fi

# ---------- バリデーション (add のみ) ----------

if [[ "$CMD" == "add" ]]; then
  [[ -n "$PROJECT" ]]     || die "--project is required"
  [[ -n "$SPRINT" ]]      || die "--sprint is required"
  [[ -n "$CATEGORY" ]]    || die "--category is required"
  [[ -n "$SEVERITY" ]]    || die "--severity is required"
  [[ -n "$FREQUENCY" ]]   || die "--frequency is required"
  [[ -n "$DESCRIPTION" ]] || die "--description is required"
  [[ -n "$ACTION" ]]      || die "--action is required"

  [[ "$SPRINT" =~ ^sprint-[0-9]+$ ]] \
    || die "--sprint must match 'sprint-NNN' (e.g. sprint-02), got: '$SPRINT'"

  VALID_CATEGORIES="planning implementation qa communication tooling process architecture reliability"
  echo "$VALID_CATEGORIES" | tr ' ' '\n' | grep -qx "$CATEGORY" \
    || die "--category must be one of: $VALID_CATEGORIES, got: '$CATEGORY'"

  [[ "$SEVERITY" =~ ^[1-3]$ ]] \
    || die "--severity must be 1, 2, or 3, got: '$SEVERITY'"
  [[ "$FREQUENCY" =~ ^[1-3]$ ]] \
    || die "--frequency must be 1, 2, or 3, got: '$FREQUENCY'"

  [[ "$TYPE" =~ ^(failure|success|observation)$ ]] \
    || die "--type must be failure, success, or observation, got: '$TYPE'"

  [[ "$STATUS" =~ ^(proposed|issue_created|implemented|verified|dismissed)$ ]] \
    || die "--status must be proposed|issue_created|implemented|verified|dismissed, got: '$STATUS'"

  [[ "$SCOPE" =~ ^(project|global|stack)$ ]] \
    || die "--scope must be project, global, or stack, got: '$SCOPE'"

  if [[ "$SCOPE" == "stack" && "$STACK" == "null" ]]; then
    die "--stack is required when --scope is stack"
  fi

  [[ ${#DESCRIPTION} -ge 10 ]] \
    || die "--description must be at least 10 characters"
  [[ ${#ACTION} -ge 5 ]] \
    || die "--action must be at least 5 characters"

  [[ "$ENFORCEMENT" =~ ^(code|prompt|process)$ ]] \
    || die "--enforcement must be code, prompt, or process, got: '$ENFORCEMENT'"

  # 再発検知条件ゲート（learning-loop-verification-proposal.md L0-2 / Sora指摘3）:
  # ルール書き出し対象（type=failure かつ priority>=3）では、
  # 「何が観測されなくなったら効いたと言えるか」の明文化をコードで強制する。
  if [[ "$TYPE" == "failure" && $(( SEVERITY * FREQUENCY )) -ge 3 ]]; then
    [[ -n "$RECURRENCE_CONDITION" ]] \
      || die "--recurrence-condition is required for failure lessons with priority_score >= 3 (何が観測されなくなったら効いたと言えるかを書く)"
    [[ ${#RECURRENCE_CONDITION} -ge 10 ]] \
      || die "--recurrence-condition must be at least 10 characters"
  fi

  # source_repo: 未指定なら origin から取得し、SSH形式は HTTPS へ正規化する
  if [[ -z "$SOURCE_REPO" ]]; then
    SOURCE_REPO=$(git remote get-url origin 2>/dev/null || echo "local")
  fi
  SOURCE_REPO=$(normalize_source_repo "$SOURCE_REPO")
fi

# ---------- バリデーション (verify-check) ----------
if [[ "$CMD" == "verify-check" ]]; then
  [[ -n "$VERIFY_SPRINT" ]] || die "verify-check requires <current-sprint> argument"
  [[ "$VERIFY_SPRINT" =~ ^sprint-[0-9]+$ ]] \
    || die "verify-check sprint must match 'sprint-NNN', got: '$VERIFY_SPRINT'"
fi

# ---------- バリデーション (promote) ----------
if [[ "$CMD" == "promote" ]]; then
  [[ -n "$PROMOTE_ID" ]] || die "promote requires <id> argument"
  [[ -n "$PROMOTE_SCOPE" ]] || die "promote requires <scope> argument"
  [[ "$PROMOTE_SCOPE" =~ ^(project|global|stack)$ ]] \
    || die "promote scope must be project, global, or stack, got: '$PROMOTE_SCOPE'"
  if [[ "$PROMOTE_SCOPE" == "stack" && "$PROMOTE_STACK" == "null" ]]; then
    die "promote requires <stack> argument when scope is stack"
  fi
fi

# ファイル存在確認（初期化済みか）
[[ -f "$LESSONS_FILE" ]] \
  || die "$LESSONS_FILE does not exist. Run lessons_init.sh first."

# ---------- jq 確認 ----------

command -v jq >/dev/null 2>&1 \
  || die "jq is not installed. Please install jq."

# ---------- ロック & アトミック書き込み ----------

_do_set_status() {
  local target_id="$1" new_status="$2"
  local existing updated tmp updated_at

  [[ -f "$LESSONS_FILE" ]] || die "$LESSONS_FILE does not exist."
  [[ "$new_status" =~ ^(proposed|issue_created|implemented|verified|dismissed)$ ]] \
    || die "invalid status: '$new_status'"

  existing=$(cat "$LESSONS_FILE")

  jq -e --arg id "$target_id" '.lessons[] | select(.id == $id)' <<< "$existing" > /dev/null \
    || die "lesson not found: '$target_id'"

  updated_at=$(date -u +"%Y-%m-%dT%H:%M:%S+0000")
  updated=$(jq \
    --arg id         "$target_id" \
    --arg status     "$new_status" \
    --arg updated_at "$updated_at" \
    '.lessons |= map(
      if .id == $id then
        .status = $status | .updated_at = $updated_at
      else . end
    )' \
    <<< "$existing")

  tmp=$(mktemp "${LESSONS_FILE}.tmp.XXXXXX")
  echo "$updated" > "$tmp"
  mv "$tmp" "$LESSONS_FILE"

  echo "Updated $target_id: status → $new_status"
}

_do_promote() {
  local target_id="$1" new_scope="$2" new_stack="$3"
  local existing updated tmp updated_at

  [[ -f "$LESSONS_FILE" ]] || die "$LESSONS_FILE does not exist."

  existing=$(cat "$LESSONS_FILE")

  jq -e --arg id "$target_id" '.lessons[] | select(.id == $id)' <<< "$existing" > /dev/null \
    || die "lesson not found: '$target_id'"

  updated_at=$(date -u +"%Y-%m-%dT%H:%M:%S+0000")
  updated=$(jq \
    --arg id         "$target_id" \
    --arg scope      "$new_scope" \
    --argjson stack  "$new_stack" \
    --arg updated_at "$updated_at" \
    '.lessons |= map(
      if .id == $id then
        .scope = $scope | .stack = $stack | .updated_at = $updated_at
      else . end
    )' \
    <<< "$existing")

  tmp=$(mktemp "${LESSONS_FILE}.tmp.XXXXXX")
  echo "$updated" > "$tmp"
  mv "$tmp" "$LESSONS_FILE"

  echo "Updated $target_id: scope → $new_scope"
}

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

  local recurrence_json="null"
  if [[ -n "$RECURRENCE_CONDITION" ]]; then
    recurrence_json=$(jq -n --arg c "$RECURRENCE_CONDITION" '$c')
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
    --arg scope        "$SCOPE" \
    --argjson stack    "$STACK" \
    --argjson evidence "$evidence_json" \
    --argjson tags     "$tags_json" \
    --argjson issue_url "$ISSUE_URL" \
    --arg status       "$STATUS" \
    --argjson supersedes "$SUPERSEDES" \
    --arg created_at   "$created_at" \
    --arg source_repo  "$SOURCE_REPO" \
    --argjson recurrence_condition "$recurrence_json" \
    --arg enforcement  "$ENFORCEMENT" \
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
      scope:           $scope,
      stack:           $stack,
      issue_url:       $issue_url,
      status:          $status,
      supersedes:      $supersedes,
      tags:            $tags,
      source_repo:     $source_repo,
      recurrence_condition: $recurrence_condition,
      enforcement:     $enforcement,
      verification_streak: 0,
      last_recurrence_sprint: null,
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

_do_verify_check() {
  local current_sprint="$1"
  shift
  local recurred_json existing updated tmp updated_at

  existing=$(cat "$LESSONS_FILE")
  updated_at=$(date -u +"%Y-%m-%dT%H:%M:%S+0000")

  # --recurred で渡された ID を JSON 配列へ
  if [[ $# -eq 0 ]]; then
    recurred_json="[]"
  else
    recurred_json=$(printf '%s\n' "$@" | jq -R . | jq -s .)
  fi

  # 指定 ID の存在チェック（typo で無言スキップしないため）
  local missing
  missing=$(jq -r --argjson ids "$recurred_json" '
    ($ids - [.lessons[].id]) | .[]' <<< "$existing")
  [[ -z "$missing" ]] || die "verify-check: lesson not found: $missing"

  # 効果検証の対象 = ルール書き出し対象（type=failure, priority>=3）で
  # 現スプリントより前に記録されたもの。
  # - recurred に含まれる → streak を 0 リセット、last_recurrence_sprint 更新。
  #   verified 済みだった場合は implemented へ差し戻す（検証済みルールの破れ）
  # - 含まれない（未確定ステータスのみ）→ streak +1。streak >= 2 で
  #   status=verified へ自動遷移
  updated=$(jq \
    --arg current    "$current_sprint" \
    --arg updated_at "$updated_at" \
    --argjson recurred "$recurred_json" \
    '
    def rule_target:
      ((.type // "failure") == "failure")
      and ((.priority_score // 0) >= 3)
      and (.sprint != $current);
    def open_status:
      (.status // "proposed") | IN("proposed", "issue_created", "implemented", "open");
    .lessons |= map(
      if (rule_target and ([.id] | inside($recurred))) then
        .verification_streak = 0
        | .last_recurrence_sprint = $current
        | (if .status == "verified" then .status = "implemented" else . end)
        | .updated_at = $updated_at
      elif (rule_target and open_status) then
        .verification_streak = ((.verification_streak // 0) + 1)
        | (if .verification_streak >= 2 then .status = "verified" else . end)
        | .updated_at = $updated_at
      else . end
    )' \
    <<< "$existing")

  tmp=$(mktemp "${LESSONS_FILE}.tmp.XXXXXX")
  echo "$updated" > "$tmp"
  mv "$tmp" "$LESSONS_FILE"

  # サマリー出力: 実行前後の diff で判定する
  # （updated_at のタイムスタンプ比較は秒精度のため同一秒の連続実行で誤報告するリスクがある）
  jq -rn \
    --argjson before "$existing" \
    --argjson after  "$updated" \
    --arg current "$current_sprint" '
    ($before.lessons | map({key: .id, value: .}) | from_entries) as $b
    | [$after.lessons[]
       | . as $l
       | $b[$l.id] as $old
       | select($old != null and (
           (($l.verification_streak // 0) != ($old.verification_streak // 0))
           or ($l.status != $old.status)
           or ($l.last_recurrence_sprint != $old.last_recurrence_sprint)
         ))
      ] as $touched
    | [$touched[] | select(.last_recurrence_sprint == $current)] as $reset
    | [$touched[] | select(.status == "verified" and .last_recurrence_sprint != $current)] as $verified
    | [$touched[] | select(.status != "verified" and .last_recurrence_sprint != $current)] as $progress
    | "verify-check (\($current)):",
      "  再発リセット: \($reset | length) 件\(if ($reset|length) > 0 then " → 機械化候補: " + ([$reset[].id] | join(", ")) else "" end)",
      "  verified 遷移: \($verified | length) 件\(if ($verified|length) > 0 then " → " + ([$verified[].id] | join(", ")) else "" end)",
      "  streak 進行中: \($progress | length) 件"
  '
}

# ---------- コマンド実行 ----------

execute_with_lock() {
  local cmd_func="$1"
  shift
  local result
  
  # 注意: 呼び出し側が `|| exit` で受けると set -e が本関数内で無効化されるため、
  # コマンド置換の失敗を明示的に return で伝搬させる（暗黙の set -e に頼らない）。
  local rc=0
  if command -v flock >/dev/null 2>&1; then
    result=$(
      (
        flock -x -w "$LOCK_TIMEOUT" 200 || die "lock timeout (${LOCK_TIMEOUT}s). Another process may be writing."
        "$cmd_func" "$@"
      ) 200>"$LOCK_FILE"
    ) || rc=$?
  else
    acquire_mkdir_lock
    trap release_mkdir_lock EXIT INT TERM
    result=$("$cmd_func" "$@") || rc=$?
    trap - EXIT INT TERM
    release_mkdir_lock
  fi
  [[ $rc -eq 0 ]] || return $rc
  echo "$result"
}

# 注意: _do_* 内の die はロック用 subshell 内で発火するため、
# 呼び出し側で || exit を明示しないと失敗が exit 0 に化ける。
if [[ "$CMD" == "set-status" ]]; then
  result=$(execute_with_lock _do_set_status "$SET_STATUS_ID" "$SET_STATUS_VAL") || exit $?
  echo "$result"
  exit 0
elif [[ "$CMD" == "promote" ]]; then
  result=$(execute_with_lock _do_promote "$PROMOTE_ID" "$PROMOTE_SCOPE" "$PROMOTE_STACK") || exit $?
  echo "$result"
  exit 0
elif [[ "$CMD" == "add" ]]; then
  result=$(execute_with_lock _do_add) || exit $?
  echo "Added lesson: $result"
  exit 0
elif [[ "$CMD" == "verify-check" ]]; then
  if [[ ${#RECURRED_IDS[@]} -eq 0 ]]; then
    result=$(execute_with_lock _do_verify_check "$VERIFY_SPRINT") || exit $?
  else
    result=$(execute_with_lock _do_verify_check "$VERIFY_SPRINT" "${RECURRED_IDS[@]}") || exit $?
  fi
  echo "$result"
  exit 0
fi

