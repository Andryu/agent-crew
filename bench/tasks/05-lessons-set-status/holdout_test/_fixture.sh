#!/bin/bash
# 05 共通 fixture: 教訓ファイル生成と lessons.sh 実行ヘルパー
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

LESSONS_FILE="$BENCH_TMP/_lessons.json"
LOCK_FILE="$BENCH_TMP/_lessons.json.lock"
SAMPLE_ID="agent-crew-sprint-00-tooling-001"

SEV=$(( 1 + $(t_rand 1 3) ))
FREQ=$(( 1 + $(t_rand 2 3) ))
SPRINT="sprint-$(( 1 + $(t_rand 3 98) ))"
DESC="ベンチ検証用の教訓レコード $(t_rand 4 10000) 番"
ACTION="次回はベンチ手順に従うこと"

cat > "$LESSONS_FILE" <<'JSON'
{
  "schema_version": "1.1.0",
  "lessons": [
    {
      "id": "agent-crew-sprint-00-tooling-001",
      "project": "agent-crew",
      "sprint": "sprint-00",
      "category": "tooling",
      "type": "observation",
      "severity_score": 1,
      "frequency_score": 1,
      "priority_score": 1,
      "description": "既存のサンプルエントリ。ベンチではこのレコードが不変であることを確認する。",
      "evidence": ["fixture 初期化"],
      "action": "このレコードには触れないこと。",
      "issue_url": null,
      "status": "implemented",
      "supersedes": null,
      "tags": ["fixture"],
      "created_at": "2026-01-01T00:00:00+0000",
      "updated_at": null
    }
  ]
}
JSON

run_lessons() {
  (
    cd "$BENCH_WORK_DIR" &&
    env LESSONS_FILE="$LESSONS_FILE" LOCK_FILE="$LOCK_FILE" \
      bash scripts/lessons.sh "$@"
  )
}

# 標準の必須オプション付き add を実行する。追加引数はそのまま渡す。
run_add() {
  run_lessons add \
    --project agent-crew \
    --sprint "$SPRINT" \
    --category tooling \
    --severity "$SEV" \
    --frequency "$FREQ" \
    --description "$DESC" \
    --action "$ACTION" \
    "$@"
}

lesson_count() {
  jq '.lessons | length' "$LESSONS_FILE"
}

# DESC で追加したレコードを1件取り出す（compact JSON）
added_record() {
  jq -c --arg d "$DESC" '.lessons[] | select(.description == $d)' "$LESSONS_FILE"
}

sample_record() {
  jq -c --arg id "$SAMPLE_ID" '.lessons[] | select(.id == $id)' "$LESSONS_FILE"
}
