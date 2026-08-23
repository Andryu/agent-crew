#!/bin/bash
# 08 共通 fixture: キューを持つ対象リポジトリと、CWD 用のおとりリポジトリを組み立てる
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

QUEUE_PY="$BENCH_WORK_DIR/scripts/queue.py"
UV="${BENCH_UV:-$HOME/.local/bin/uv}"
[[ -x "$UV" ]] || UV=$(command -v uv || true)
[[ -n "$UV" && -x "$UV" ]] || fail "uv が見つからない（queue.py の実行に必要）"

OUT="$BENCH_TMP/stdout.txt"
ERR="$BENCH_TMP/stderr.txt"

SLUG="bench-task-$(t_rand 1 100000)"
AGENT="Riku"
# 未コミットにする「変更済み追跡ファイル」の件数（シードで 2〜5）
DIRTY_N=$(( 2 + $(t_rand 2 4) ))

git_init() { # <dir>
  git -C "$1" init -q
  git -C "$1" config user.email bench@example.invalid
  git -C "$1" config user.name bench
  git -C "$1" config commit.gpgsign false
}

write_queue() { # <queue-file>
  local qf="$1"
  mkdir -p "$(dirname "$qf")"
  cat > "$qf" <<EOF
{
  "sprint": "bench-sprint",
  "tasks": [
    {
      "slug": "$SLUG",
      "title": "bench task",
      "status": "IN_PROGRESS",
      "assigned_to": "$AGENT",
      "complexity": "S",
      "risk_level": "low",
      "parallel_group": null,
      "depends_on": [],
      "qa_mode": null,
      "created_at": "2026-01-01",
      "updated_at": "2026-01-01",
      "notes": "",
      "retry_count": 0,
      "qa_result": null,
      "summary": null,
      "events": []
    }
  ]
}
EOF
}

# キューを .claude/ 配下に持つ git リポジトリを作る（初期状態はクリーン）
# .claude/ は追跡対象外にして「done 自身の書き込み」が差分に混ざらないようにする
mk_target_repo() { # <dir>
  local d="$1" i
  rm -rf "$d"
  mkdir -p "$d"
  git_init "$d"
  printf '.claude/\n' > "$d/.gitignore"
  printf '# bench target repo\n' > "$d/README.md"
  i=1
  while [[ $i -le $DIRTY_N ]]; do
    printf 'original content %d\n' "$i" > "$d/file$i.txt"
    i=$(( i + 1 ))
  done
  git -C "$d" add -A >/dev/null 2>&1
  git -C "$d" commit -q -m init >/dev/null 2>&1
  write_queue "$d/.claude/_queue.json"
}

# 追跡ファイルを DIRTY_N 件だけ書き換えて「未コミットの変更」を作る
make_dirty() { # <dir>
  local d="$1" i=1
  while [[ $i -le $DIRTY_N ]]; do
    printf 'modified content %d (%s)\n' "$i" "$SLUG" > "$d/file$i.txt"
    i=$(( i + 1 ))
  done
}

# CWD 用のおとりリポジトリ（対象リポジトリとは別物）
mk_decoy_repo() { # <dir> <dirty:0|1>
  local d="$1" dirty="$2"
  rm -rf "$d"
  mkdir -p "$d"
  git_init "$d"
  printf 'decoy\n' > "$d/decoy.txt"
  git -C "$d" add -A >/dev/null 2>&1
  git -C "$d" commit -q -m init >/dev/null 2>&1
  if [[ "$dirty" == "1" ]]; then
    printf 'decoy dirty %s\n' "$SLUG" > "$d/decoy.txt"
    printf 'decoy extra\n' > "$d/decoy2.txt"
  fi
}

# done を実行する。<cwd> <queue-file> [extra env assignments...]
run_done() {
  local cwd="$1" qf="$2"; shift 2
  : > "$OUT"; : > "$ERR"
  RC=0
  ( cd "$cwd" && env QUEUE_FILE="$qf" "$@" \
      "$UV" run --no-project --script "$QUEUE_PY" done "$SLUG" "$AGENT" "完了" ) \
    >"$OUT" 2>"$ERR" || RC=$?
}

assert_done_ok() { # <queue-file>
  local qf="$1"
  [[ "$RC" -eq 0 ]] || fail "done の終了コードが 0 でない: $RC
--- stdout ---
$(cat "$OUT")
--- stderr ---
$(cat "$ERR")"
  grep -q '"status": *"DONE"' "$qf" \
    || fail "タスクが DONE になっていない
$(cat "$qf")"
}

assert_warned() {
  [[ -s "$ERR" ]] || fail "未コミットの変更があるのに stderr が空"
  grep -qE "(^|[^0-9])${DIRTY_N}([^0-9]|$)" "$ERR" \
    || fail "警告に未コミット件数 ${DIRTY_N} が含まれていない
--- stderr ---
$(cat "$ERR")"
}

# git を含まない PATH を作る（uv は絶対パスで起動するので PATH には要らない）
make_nogit_path() {
  local farm="$BENCH_TMP/nogitbin" t src
  rm -rf "$farm"; mkdir -p "$farm"
  for t in sh bash env cat ls mkdir rm cp mv printf uname dirname basename python3; do
    src=$(command -v "$t" 2>/dev/null) || continue
    ln -s "$src" "$farm/$t" 2>/dev/null || true
  done
  echo "$farm"
}

assert_not_warned() {
  if [[ -s "$ERR" ]]; then
    fail "未コミットの変更が無いのに stderr に出力がある
--- stderr ---
$(cat "$ERR")"
  fi
}
