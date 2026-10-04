#!/bin/bash
# 07 共通 fixture: 教訓ファイル生成と lessons-to-vault.sh 実行ヘルパー
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

SCRIPT_REL="scripts/lessons-to-vault.sh"
[[ -f "$BENCH_WORK_DIR/$SCRIPT_REL" ]] || fail "scripts/lessons-to-vault.sh が作られていない"

LESSONS_FILE="$BENCH_TMP/_lessons.json"
FAKE_HOME="$BENCH_TMP/home"
VAULT_DIR="$BENCH_TMP/vault"
mkdir -p "$FAKE_HOME" "$VAULT_DIR"

MP=$(( 3 + $(t_rand 1 4) ))                     # しきい値 3〜6（ランダム）
HI_SPRINT="sprint-$(( 25 + $(t_rand 2 15) ))"   # 25〜39
ID_BOUND="bench-boundary-$(t_rand 3 100000)"
ID_LOW="bench-low-$(t_rand 4 100000)"
ID_OLD="bench-old-$(t_rand 5 100000)"
ID_HI="bench-hi-$(t_rand 6 100000)"
DESC_BOUND="しきい値ちょうどの教訓 desc-$(t_rand 7 100000)"
ACTION_BOUND="境界値を確認する action-$(t_rand 8 100000)"

make_lessons() {
  jq -n \
    --arg id_bound "$ID_BOUND" --arg id_low "$ID_LOW" \
    --arg id_old "$ID_OLD" --arg id_hi "$ID_HI" \
    --arg hi_sprint "$HI_SPRINT" \
    --arg desc_bound "$DESC_BOUND" --arg action_bound "$ACTION_BOUND" \
    --argjson mp "$MP" '{
    schema_version: "1.1.0",
    lessons: [
      {id: $id_bound, project: "agent-crew", sprint: "sprint-24",
       category: "tooling", type: "failure", priority_score: $mp,
       description: $desc_bound, action: $action_bound},
      {id: $id_low, project: "agent-crew", sprint: "sprint-24",
       category: "process", type: "observation", priority_score: ($mp - 1),
       description: "しきい値未満の教訓（転記されないはず）", action: "なし"},
      {id: $id_old, project: "agent-crew", sprint: "sprint-23",
       category: "qa", type: "failure", priority_score: 9,
       description: "古いスプリントの教訓（転記されないはず）", action: "なし"},
      {id: $id_hi, project: "agent-crew", sprint: $hi_sprint,
       category: "planning", type: "failure", priority_score: ($mp + 3),
       description: "高優先度の教訓（転記されるはず）", action: "対応する"}
    ]
  }' > "$LESSONS_FILE"
}

# MIN_SPRINT は既定値（24）のまま、MIN_PRIORITY だけランダムしきい値で実行する
run_vault() {
  (
    cd "$BENCH_WORK_DIR" &&
    env HOME="$FAKE_HOME" VAULT_DIR="$VAULT_DIR" \
        LESSONS_FILE="$LESSONS_FILE" MIN_PRIORITY="$MP" \
      bash "$SCRIPT_REL"
  )
}

vault_file_count() {
  find "$VAULT_DIR" -type f | wc -l | tr -d ' '
}
