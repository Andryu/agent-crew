#!/bin/bash
# 12 共通 fixture: 教訓ファイル・自リポジトリ役ディレクトリ・実行ヘルパー
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

LESSONS_FILE="$BENCH_TMP/_lessons.json"
LOCK_FILE="$BENCH_TMP/_lessons.json.lock"

OWN_SSH="git@github.com:benchuser/bench-own.git"
OWN_HTTPS="https://github.com/benchuser/bench-own"
EXT_REPO="https://github.com/external/other-repo"

MINP=$(( 2 + $(t_rand 1 4) ))   # しきい値 2〜5（ランダム）
SUF=$(t_rand 2 100000)

ID_IN="bench-in-$SUF"
ID_LOWP="bench-lowp-$SUF"
ID_VERIFIED="bench-verified-$SUF"
ID_DISMISSED="bench-dismissed-$SUF"
ID_IMPL="bench-impl-$SUF"
ID_OPEN="bench-open-$SUF"
ID_NULLST="bench-nullst-$SUF"
ID_CODE="bench-code-$SUF"
ID_NULLREPO="bench-nullrepo-$SUF"
ID_EXT="bench-ext-$SUF"
ID_APPR="bench-appr-$SUF"
ID_SSH="bench-sshrepo-$SUF"

# 自リポジトリ役の cwd（origin リモート付き git リポジトリ）
OWN_DIR="$BENCH_TMP/own-repo"
mkdir -p "$OWN_DIR"
git -C "$OWN_DIR" init -q
git -C "$OWN_DIR" remote add origin "$OWN_SSH"

run_lessons() {
  (
    cd "$OWN_DIR" &&
    env LESSONS_FILE="$LESSONS_FILE" LOCK_FILE="$LOCK_FILE" \
      bash "$BENCH_WORK_DIR/scripts/lessons.sh" "$@"
  )
}

make_empty_lessons() {
  echo '{"schema_version":"1.3.0","lessons":[]}' > "$LESSONS_FILE"
}

# 1件ぶんの教訓 JSON を組み立てる（source_repo は "null" で JSON null になる）
mk_lesson() { # id category priority status enforcement source_repo owner_approved
  jq -n --arg id "$1" --arg cat "$2" --argjson pri "$3" \
        --argjson status "$4" --arg enf "$5" \
        --argjson repo "$6" --argjson appr "$7" '{
    id: $id, project: "agent-crew", sprint: "sprint-30", category: $cat,
    type: "failure", severity_score: 3, frequency_score: 2,
    priority_score: $pri,
    description: ("bench fixture lesson " + $id),
    action: ("do something about " + $id),
    status: $status, enforcement: $enf,
    source_repo: $repo, owner_approved: $appr,
    evidence: [], tags: [], issue_url: null, supersedes: null,
    scope: "project", stack: null, recurrence_condition: "同型の再発が観測されないこと",
    verification_streak: 0,
    created_at: "2026-01-01T00:00:00+0000", updated_at: null
  }'
}

# 抽出条件の全組み合わせを含む fixture を作る
make_combo_lessons() {
  {
    mk_lesson "$ID_IN"        tooling      "$MINP"          '"proposed"'    prompt "\"${OWN_HTTPS}.git\"" false
    mk_lesson "$ID_LOWP"      tooling      "$(( MINP - 1 ))" '"proposed"'   prompt "\"${OWN_HTTPS}\""     false
    mk_lesson "$ID_VERIFIED"  qa           "$(( MINP + 2 ))" '"verified"'   prompt "\"${OWN_HTTPS}\""     false
    mk_lesson "$ID_DISMISSED" process      "$MINP"          '"dismissed"'   prompt "\"${OWN_HTTPS}\""     false
    mk_lesson "$ID_IMPL"      qa           "$MINP"          '"implemented"' prompt "\"${OWN_HTTPS}\""     false
    mk_lesson "$ID_OPEN"      architecture "$MINP"          '"open"'        prompt "\"${OWN_HTTPS}\""     false
    mk_lesson "$ID_NULLST"    process      "$MINP"          'null'          prompt "\"${OWN_HTTPS}\""     false
    mk_lesson "$ID_CODE"      tooling      "$(( MINP + 1 ))" '"proposed"'   code   "\"${OWN_HTTPS}\""     false
    mk_lesson "$ID_NULLREPO"  tooling      "$MINP"          '"proposed"'    prompt 'null'                 false
    mk_lesson "$ID_EXT"       qa           "$MINP"          '"proposed"'    prompt "\"${EXT_REPO}\""      false
    mk_lesson "$ID_APPR"      qa           "$MINP"          '"proposed"'    prompt "\"${EXT_REPO}\""      true
    mk_lesson "$ID_SSH"       tooling      "$MINP"          '"proposed"'    prompt "\"${OWN_SSH}\""       false
  } | jq -s '{schema_version: "1.3.0", lessons: .}' > "$LESSONS_FILE"
}

# 期待される抽出結果（ソート済み・改行区切り）
combo_expected_ids() {
  printf '%s\n' "$ID_IN" "$ID_IMPL" "$ID_OPEN" "$ID_NULLST" \
                "$ID_NULLREPO" "$ID_APPR" "$ID_SSH" | sort
}

list_ids() { # 引数はそのまま list-rule-candidates へ
  run_lessons list-rule-candidates "$@" | jq -r '.id' | sort
}
