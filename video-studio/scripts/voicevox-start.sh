#!/usr/bin/env bash
# VOICEVOX engine (macOS arm64, CPU) をオンデマンドで起動するスクリプト。
# 既に localhost:50021 で応答があれば何もしない（多重起動を避ける）。
set -euo pipefail

VOICEVOX_HOME="${VOICEVOX_HOME:-$HOME/Workspace/video-tools/voicevox_engine}"
PORT="${VOICEVOX_PORT:-50021}"
LOG_FILE="${VOICEVOX_LOG:-$VOICEVOX_HOME/engine.log}"

if curl -fsS "http://localhost:${PORT}/version" >/dev/null 2>&1; then
  echo "[voicevox-start] already running on :${PORT} (version: $(curl -fsS "http://localhost:${PORT}/version"))"
  exit 0
fi

BINARY="$VOICEVOX_HOME/run"
if [ ! -x "$BINARY" ]; then
  echo "[voicevox-start] engine binary not found: $BINARY" >&2
  echo "[voicevox-start] setup-voicevox.md の手順に従って展開してください" >&2
  exit 1
fi

echo "[voicevox-start] starting engine from $VOICEVOX_HOME (log: $LOG_FILE)"
cd "$VOICEVOX_HOME"
nohup "$BINARY" --host 127.0.0.1 --port "$PORT" >"$LOG_FILE" 2>&1 &
disown

# 起動待ち（最大30秒）
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:${PORT}/version" >/dev/null 2>&1; then
    echo "[voicevox-start] ready: $(curl -fsS "http://localhost:${PORT}/version")"
    exit 0
  fi
  sleep 1
done

echo "[voicevox-start] timed out waiting for engine to become ready. see $LOG_FILE" >&2
exit 1
