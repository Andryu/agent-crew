#!/usr/bin/env bash
# dashboard/restart.sh — STONEFISH ダッシュボードサーバを安全に再起動する
#
# dashboard/stop.sh → dashboard/start.sh をまとめて実行する。
# コード変更（enrich.py・server.py・tokens.py 等）を反映させるには、Pythonプロセスの
# 再起動が必須（ファイル保存だけでは実行中のプロセスには反映されない）。
#
# 環境変数は dashboard/start.sh・dashboard/stop.sh と同じもの
#   STONEFISH_PORT / STONEFISH_DATA_DIR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/stop.sh"
sleep 0.5
"$SCRIPT_DIR/start.sh"
