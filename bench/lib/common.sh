#!/bin/bash
# bench/lib/common.sh — setup.sh 共通ヘルパー
#
# bench_setup <parent_sha> <work_dir> <task_dir>
#   元リポジトリ（BENCH_SRC_REPO、省略時は bench/ を含むリポジトリ自身）から
#   親SHA時点のスナップショットを取り出し、履歴1件の新規リポジトリとして
#   <work_dir> に展開する。git 操作を前提とするタスクがあるため、元リポジトリの
#   履歴は持ち込まず、initial commit だけの状態にする。
#   さらに prompt.md を TASK.md として、visible_test/ をそのままコピーし、
#   解答者が作業ディレクトリだけで完結できるようにする。
#
# 注意:
# - clone に --single-branch は使わない（対象SHAが取得できず setup が壊れた
#   前例 #153 への対策）。
set -euo pipefail

bench_setup() {
  local sha="${1:?parent sha required}"
  local work="${2:?work dir required}"
  local task_dir="${3:?task dir required}"

  local src="${BENCH_SRC_REPO:-}"
  if [[ -z "$src" ]]; then
    src=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && git rev-parse --show-toplevel)
  fi

  if [[ -e "$work" ]]; then
    echo "ERROR: work dir already exists: $work" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$work")"

  git clone --quiet --no-checkout "$src" "$work"
  # リモート指定の場合に備えて SHA を明示 fetch（ローカル clone では通常不要）
  git -C "$work" cat-file -e "${sha}^{commit}" 2>/dev/null \
    || git -C "$work" fetch --quiet origin "$sha"
  git -C "$work" checkout --quiet "$sha"

  # 履歴を捨てて initial commit 1件の新規リポジトリにする
  rm -rf "$work/.git"
  git -C "$work" init --quiet
  git -C "$work" add -A
  git -C "$work" -c user.name=bench -c user.email=bench@example.com \
    commit --quiet -m "bench: initial snapshot"

  # 解答者に見せるファイルを配置（holdout はコピーしない）
  cp "$task_dir/prompt.md" "$work/TASK.md"
  if [[ -d "$task_dir/visible_test" ]]; then
    cp -R "$task_dir/visible_test" "$work/visible_test"
  fi

  echo "OK: setup done"
  echo "  work dir : $work"
  echo "  snapshot : $sha"
  echo "  task     : $work/TASK.md"
}
