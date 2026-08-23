#!/bin/bash
# どのケースでも終了コードは 0（フックを止めない）
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

mk_repo

# 1) 検出ありでも 0
reset_repo
put_line "src/app.txt" "$LN_OPENAI" "key: $FAKE_OPENAI"
run_scan
assert_exit0
assert_reported "src/app.txt" "$LN_OPENAI"   # 前提: 実際に検出できている

# 2) クリーンでも 0
reset_repo
run_scan
assert_exit0

# 3) ステージ済みの変更だけでも 0
reset_repo
put_line "src/app.txt" "$LN_EMAIL" "owner: $FAKE_EMAIL"
git -C "$REPO" add -A >/dev/null 2>&1
run_scan
assert_exit0

# 4) 追跡対象外の新規ファイルが混ざっていても 0
reset_repo
put_line "src/app.txt" "$LN_PHONE" "tel: $FAKE_PHONE"
echo "untracked memo" > "$REPO/notes/brand-new.md"
run_scan
assert_exit0

# 5) 読み取り権限の無いファイルが混ざっていても 0
reset_repo
put_line "src/app.txt" "$LN_EMAIL" "owner: $FAKE_EMAIL"
put_line "notes/locked.md" 2 "just a memo"
chmod 000 "$REPO/notes/locked.md"
run_scan
chmod 644 "$REPO/notes/locked.md"
assert_exit0

echo "PASS"
