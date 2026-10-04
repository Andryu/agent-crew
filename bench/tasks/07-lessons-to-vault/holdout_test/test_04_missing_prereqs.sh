#!/bin/bash
# 前提欠如（LESSONS_FILE無し・VAULT_DIR無し・jq無し）でも exit 0 で何も書かないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

# a) LESSONS_FILE が存在しない
(
  cd "$BENCH_WORK_DIR" &&
  env HOME="$FAKE_HOME" VAULT_DIR="$VAULT_DIR" \
      LESSONS_FILE="$BENCH_TMP/no-such-lessons.json" MIN_PRIORITY="$MP" \
    bash "$SCRIPT_REL"
) || fail "LESSONS_FILE 不在で非ゼロ終了した"
[[ "$(vault_file_count)" == "0" ]] || fail "LESSONS_FILE 不在なのに vault に書き込んだ"

# b) VAULT_DIR が存在しない
make_lessons
NOVAULT="$BENCH_TMP/no-vault"
(
  cd "$BENCH_WORK_DIR" &&
  env HOME="$FAKE_HOME" VAULT_DIR="$NOVAULT" \
      LESSONS_FILE="$LESSONS_FILE" MIN_PRIORITY="$MP" \
    bash "$SCRIPT_REL"
) || fail "VAULT_DIR 不在で非ゼロ終了した"
[[ ! -f "$NOVAULT/inbox/agent-crew-lessons-sprint-24.md" ]] \
  || fail "VAULT_DIR 不在なのに転記された"

# c) jq が無い
FARM=$(make_restricted_path jq)
(
  cd "$BENCH_WORK_DIR" &&
  env PATH="$FARM" HOME="$FAKE_HOME" VAULT_DIR="$VAULT_DIR" \
      LESSONS_FILE="$LESSONS_FILE" MIN_PRIORITY="$MP" \
    /bin/bash "$SCRIPT_REL"
) || fail "jq 不在で非ゼロ終了した"
[[ "$(vault_file_count)" == "0" ]] || fail "jq 不在なのに vault に書き込んだ"

echo "PASS"
