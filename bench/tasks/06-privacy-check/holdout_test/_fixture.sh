#!/bin/bash
# 06 共通 fixture: スキャン対象の git リポジトリを組み立てる
#
# 重要: fixture に本物のトークンは一切置かない。形式だけ満たす偽値を
# BENCH_SEED から決定的に生成する（乱数注入）。
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

SCRIPT="$BENCH_WORK_DIR/scripts/privacy-check.sh"
REPO="$BENCH_TMP/scanrepo"
OUT="$BENCH_TMP/stdout.txt"
ERR="$BENCH_TMP/stderr.txt"

ALPHA="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
DIGITS="0123456789"

# シードから決定的に英数字列を作る（本物ではない・形式だけ満たす偽値）
t_str() {
  local series="$1" len="$2" i k out=""
  i=0
  while [[ $i -lt $len ]]; do
    k=$(t_rand $(( series * 977 + i )) 62)
    out="$out${ALPHA:$k:1}"
    i=$(( i + 1 ))
  done
  echo "$out"
}

t_digits() {
  local series="$1" len="$2" i k out=""
  i=0
  while [[ $i -lt $len ]]; do
    k=$(t_rand $(( series * 613 + i )) 10)
    out="$out${DIGITS:$k:1}"
    i=$(( i + 1 ))
  done
  echo "$out"
}

# ---- 偽の検出対象（すべてダミー） ----
FAKE_EMAIL="bench.user$(t_rand 11 9000)+tag@example.invalid"
FAKE_PATH="/Users/benchuser$(t_rand 12 900)/work/memo.md"
FAKE_SLACK="https://hooks.slack.com/services/T$(t_str 13 9)/B$(t_str 14 9)/$(t_str 15 24)"
FAKE_GHP="ghp_$(t_str 16 36)"
FAKE_OPENAI="sk-$(t_str 17 48)"
FAKE_ANTHROPIC="sk-ant-api03-$(t_str 18 24)"
FAKE_PHONE="0$(( 7 + $(t_rand 19 3) ))0-$(t_digits 20 4)-$(t_digits 21 4)"

# 各偽値を仕込む行番号（シードでばらす）
LN_EMAIL=$(( 2 + $(t_rand 31 9) ))
LN_PATH=$(( 2 + $(t_rand 32 9) ))
LN_SLACK=$(( 2 + $(t_rand 33 9) ))
LN_GHP=$(( 2 + $(t_rand 34 9) ))
LN_OPENAI=$(( 2 + $(t_rand 35 9) ))
LN_ANTHROPIC=$(( 2 + $(t_rand 36 9) ))
LN_PHONE=$(( 2 + $(t_rand 37 9) ))

# スキャン対象になる普通のファイル群
PLAIN_FILES="notes/email.md notes/path.md notes/slack.md notes/ghp.md notes/openai.md notes/anthropic.md notes/phone.md notes/dates.md src/app.txt"
# 除外されるべきファイル群
EXCLUDED_FILES=".env .env.local vendor/deps.lock node_modules/pkg/index.js .claude/settings.local.json"

git_q() { git -C "$REPO" "$@" >/dev/null 2>&1; }

mk_repo() {
  rm -rf "$REPO"
  mkdir -p "$REPO/notes" "$REPO/src" "$REPO/vendor" "$REPO/node_modules/pkg" \
           "$REPO/.claude" "$REPO/assets"
  local f
  for f in $PLAIN_FILES $EXCLUDED_FILES assets/blob.bin; do
    mkdir -p "$REPO/$(dirname "$f")"
    printf 'placeholder\n' > "$REPO/$f"
  done
  git -C "$REPO" init -q
  git -C "$REPO" config user.email bench@example.invalid
  git -C "$REPO" config user.name bench
  git -C "$REPO" config commit.gpgsign false
  git_q add -A
  git -C "$REPO" -c user.name=bench -c user.email=bench@example.invalid \
    commit -q -m "init" >/dev/null 2>&1
}

# 作業ツリーをコミット直後の状態に戻す
reset_repo() {
  git_q checkout -- .
  git_q clean -fdq
}

# <file> <lineno> <text> : 指定行に text が来るファイルを作る
put_line() {
  local f="$1" ln="$2" text="$3" i=1
  mkdir -p "$REPO/$(dirname "$f")"
  : > "$REPO/$f"
  while [[ $i -lt $ln ]]; do
    echo "# filler line $i" >> "$REPO/$f"
    i=$(( i + 1 ))
  done
  echo "$text" >> "$REPO/$f"
  echo "# tail" >> "$REPO/$f"
}

# スキャンを実行する。終了コードを RC に、出力を OUT/ERR に入れる
run_scan() {
  [[ -f "$SCRIPT" ]] || fail "scripts/privacy-check.sh が無い"
  : > "$OUT"; : > "$ERR"
  RC=0
  ( cd "$REPO" && bash "$SCRIPT" ) >"$OUT" 2>"$ERR" || RC=$?
}

# stderr に <file> と <lineno>: が出ていること
assert_reported() {
  local f="$1" ln="$2"
  grep -qF -- "$f" "$ERR" || fail "stderr にファイル名 $f が出ていない
--- stderr ---
$(cat "$ERR")"
  grep -qE "(^|[^0-9])${ln}:" "$ERR" || fail "stderr に行番号 $ln が出ていない ($f)
--- stderr ---
$(cat "$ERR")"
}

assert_not_reported() {
  local f="$1"
  if grep -qF -- "$f" "$ERR"; then
    fail "報告されるべきでない $f が報告されている
--- stderr ---
$(cat "$ERR")"
  fi
  return 0
}

assert_exit0() {
  [[ "$RC" -eq 0 ]] || fail "終了コードが 0 でない: $RC
--- stderr ---
$(cat "$ERR")"
}
