#!/usr/bin/env bash
# dashboard/start.sh — STONEFISH ダッシュボードサーバをバックグラウンドで起動する
#
# 既に同じポートでサーバが起動中の場合は何もせず終了する（多重起動防止）。
# 実際にポートをLISTENしているプロセスのPIDを <data-dir>/server.pid に記録し、
# dashboard/stop.sh・dashboard/restart.sh がこれを使ってプロセスを特定する。
#
# 環境変数（既存の dashboard/server/server.py と同じもの）:
#   STONEFISH_PORT     既定 8787
#   STONEFISH_DATA_DIR 既定 ~/.claude/stonefish（events.jsonl・server.pid・server.log の保存先）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PORT="${STONEFISH_PORT:-8787}"
DATA_DIR="${STONEFISH_DATA_DIR:-$HOME/.claude/stonefish}"
PID_FILE="$DATA_DIR/server.pid"
LOG_FILE="$DATA_DIR/server.log"

mkdir -p "$DATA_DIR"

# 既存プロセスの生存確認（PIDファイル基準）。多重起動を防ぐ。
if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "既にサーバが起動中です（PID: ${existing_pid}, port: ${PORT}）。再起動する場合は dashboard/restart.sh を使ってください。" >&2
    exit 0
  fi
fi

cd "$REPO_ROOT"
STONEFISH_PORT="$PORT" STONEFISH_DATA_DIR="$DATA_DIR" \
  nohup uv run --group dashboard python dashboard/server/server.py >> "$LOG_FILE" 2>&1 &
disown || true

# `uv run` は python を子プロセスとして起動するラッパーのため、$! は uv run 自身のPIDで
# あり、実際にポートをbindするpythonプロセスのPIDとは異なる。ポートがLISTEN状態になるまで
# 待ち、lsof でポート基準にPIDを確定する（多重起動時の混同を避けるため名前一致検索は使わない）。
actual_pid=""
for _ in $(seq 1 30); do
  actual_pid="$(lsof -ti:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$actual_pid" ]; then
    break
  fi
  sleep 0.2
done

if [ -z "$actual_pid" ]; then
  echo "起動確認に失敗しました。ログを確認してください: $LOG_FILE" >&2
  exit 1
fi

echo "$actual_pid" > "$PID_FILE"
echo "起動しました: PID=$actual_pid port=$PORT data_dir=$DATA_DIR log=$LOG_FILE" >&2
