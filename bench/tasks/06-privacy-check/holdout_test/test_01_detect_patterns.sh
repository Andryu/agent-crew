#!/bin/bash
# 6分類それぞれについて、ファイル名と行番号が stderr に出ること
# （1回のスキャンにつき変更ファイルは1つだけにして、報告の対応関係を一意にする）
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

mk_repo

one_case() { # <file> <lineno> <line-content>
  reset_repo
  put_line "$1" "$2" "$3"
  run_scan
  assert_exit0
  assert_reported "$1" "$2"
  [[ ! -s "$OUT" ]] || fail "stdout に出力している ($1): $(cat "$OUT")"
}

one_case "notes/email.md"     "$LN_EMAIL"     "連絡先: $FAKE_EMAIL"
one_case "notes/path.md"      "$LN_PATH"      "参照: $FAKE_PATH を見る"
one_case "notes/slack.md"     "$LN_SLACK"     "webhook: $FAKE_SLACK"
one_case "notes/ghp.md"       "$LN_GHP"       "token: $FAKE_GHP"
one_case "notes/openai.md"    "$LN_OPENAI"    "key: $FAKE_OPENAI"
one_case "notes/anthropic.md" "$LN_ANTHROPIC" "key: $FAKE_ANTHROPIC"
one_case "notes/phone.md"     "$LN_PHONE"     "tel: $FAKE_PHONE"

echo "PASS"
