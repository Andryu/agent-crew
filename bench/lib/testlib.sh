#!/bin/bash
# bench/lib/testlib.sh — holdout / visible テスト共通ヘルパー
#
# テストスクリプトは次の環境変数を受け取る:
#   BENCH_WORK_DIR  解答済みリポジトリ（setup.sh が作った作業ディレクトリ）
#   BENCH_SEED      乱数シード（整数）。採点のたびにハーネスが新しく生成する
#   BENCH_TMP       チェックごとに用意される空の一時ディレクトリ
#   BENCH_TASK_DIR  タスクディレクトリ（fixture 参照用）
#
# 各テストは成功なら exit 0、失敗なら fail で非ゼロ終了する。
set -euo pipefail

: "${BENCH_WORK_DIR:?BENCH_WORK_DIR is required}"
: "${BENCH_TMP:?BENCH_TMP is required}"
BENCH_SEED="${BENCH_SEED:-12345}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# シードから決定的に疑似乱数を得る。
#   t_rand <系列番号> <上限>  → 0 以上 <上限> 未満の整数
# fixture の値はこれで生成し、期待値はテスト側で独立に計算する
# （解答が値を丸暗記できないようにするランダム値注入）。
t_rand() {
  local i="$1" mod="$2"
  local v=$(( ( (BENCH_SEED % 100000 + 1) * 2654435761 + i * 40503 ) % mod ))
  echo $(( v < 0 ? -v : v ))
}

# 指定コマンドを「存在しない」状態にした symlink ファームを作り、そのパスを出力する。
# 使い方:
#   FARM=$(make_restricted_path jq gh)
#   env PATH="$FARM" /bin/bash script.sh   # 注意: bash は絶対パスで起動すること
make_restricted_path() {
  local farm
  farm=$(mktemp -d "$BENCH_TMP/binfarm.XXXXXX")
  local tools=(bash sh cat date mkdir rmdir mv rm mktemp grep sed awk tr sort head
               tail printf sleep ls dirname basename env uname cut wc touch chmod
               ln find xargs cp diff cmp shasum jq gh flock)
  local t x src
  for t in "${tools[@]}"; do
    for x in "$@"; do
      if [[ "$t" == "$x" ]]; then
        continue 2
      fi
    done
    src=$(command -v "$t" 2>/dev/null) || continue
    ln -s "$src" "$farm/$t"
  done
  echo "$farm"
}

# jq でファイルから値を取り出す簡易ヘルパー
jqr() {
  local filter="$1" file="$2"
  jq -r "$filter" "$file"
}
