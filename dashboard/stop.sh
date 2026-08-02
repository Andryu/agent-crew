#!/usr/bin/env bash
# dashboard/stop.sh — STONEFISH ダッシュボードサーバを安全に停止する
#
# 1. PIDファイル（<data-dir>/server.pid）を優先して使う
# 2. PIDファイルが無い・古い（既に死んでいる）場合は、ポート（既定8787）を
#    LISTENしているプロセスをlsofで検索するフォールバックを使う
# どちらの経路でも、まずSIGTERMで正常終了（aiohttpのon_cleanupでバックグラウンド
# タスクを正しく後始末させる）を試み、一定時間停止しなければSIGKILLする。
#
# 環境変数（dashboard/start.sh と同じもの）:
#   STONEFISH_PORT     既定 8787
#   STONEFISH_DATA_DIR 既定 ~/.claude/stonefish
set -euo pipefail

PORT="${STONEFISH_PORT:-8787}"
DATA_DIR="${STONEFISH_DATA_DIR:-$HOME/.claude/stonefish}"
PID_FILE="$DATA_DIR/server.pid"

# SIGTERM送信後、最大3秒（0.3秒 x 10回）は正常終了を待ち、
# それでも生きていればSIGKILLする。
_terminate() {
  local pid="$1"
  if ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "停止しました: PID=$pid" >&2
      return 0
    fi
    sleep 0.3
  done
  echo "SIGTERM で終了しなかったため SIGKILL します: PID=$pid" >&2
  kill -9 "$pid" 2>/dev/null || true
}

stopped_any=0

# 1. PIDファイル基準
if [ -f "$PID_FILE" ]; then
  pid_from_file="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$pid_from_file" ] && kill -0 "$pid_from_file" 2>/dev/null; then
    _terminate "$pid_from_file"
    stopped_any=1
  fi
  rm -f "$PID_FILE"
fi

# 2. フォールバック: ポート基準（PIDファイルが古い/無い場合に備える。
#    1で既に止めたPIDが再度ヒットしても kill -0 で無害にスキップされる）
port_pids="$(lsof -ti:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$port_pids" ]; then
  for pid in $port_pids; do
    _terminate "$pid"
    stopped_any=1
  done
fi

if [ "$stopped_any" -eq 0 ]; then
  echo "port $PORT で稼働中のサーバは見つかりませんでした（既に停止済み）。" >&2
fi
