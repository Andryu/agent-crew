#!/bin/bash
# VAULT_DIR 環境変数で出力先を差し替えられ、既定の場所には何も書かないこと
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_fixture.sh"

make_lessons
run_vault || fail "スクリプトが非ゼロで終了した"

[[ "$(vault_file_count)" -ge 1 ]] || fail "VAULT_DIR に何も生成されていない"
[[ ! -e "$FAKE_HOME/Workspace/Obsidian" ]] \
  || fail "VAULT_DIR を指定したのに既定の \$HOME/Workspace/Obsidian に書き込んだ"

echo "PASS"
