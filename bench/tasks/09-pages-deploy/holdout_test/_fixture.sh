#!/bin/bash
# 09 共通 fixture: PyYAML の使える python を選んでチェッカーを呼ぶ
source "$BENCH_TASK_DIR/../../lib/testlib.sh"

CHECKER="$BENCH_TASK_DIR/holdout_test/_check.py"

# 1) 環境変数指定 → 2) システムの python3 に PyYAML → 3) uv 経由
run_check() {
  local name="$1"
  if [[ -n "${BENCH_PYTHON_YAML:-}" ]]; then
    $BENCH_PYTHON_YAML "$CHECKER" "$name" || fail "check '$name' が失敗"
    return
  fi
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' >/dev/null 2>&1; then
    python3 "$CHECKER" "$name" || fail "check '$name' が失敗"
    return
  fi
  local uv="${BENCH_UV:-$HOME/.local/bin/uv}"
  [[ -x "$uv" ]] || uv=$(command -v uv || true)
  [[ -n "$uv" && -x "$uv" ]] \
    || fail "PyYAML の使える python が無い（BENCH_PYTHON_YAML か uv を用意してください）"
  "$uv" run --no-project --with pyyaml python "$CHECKER" "$name" \
    || fail "check '$name' が失敗"
}
