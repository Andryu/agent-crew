#!/usr/bin/env bash
# VOICEVOX engine を叩いてテキストをwavに合成するラッパー。
# 使い方: voice.sh "<テキスト>" <話者ID(speaker/style id)> <出力wavパス> [speedScale]
# speedScale省略時は1.0（等倍）。1.1なら1.1倍速。
set -euo pipefail

if [ $# -lt 3 ]; then
  echo "usage: $0 \"<text>\" <speaker_id> <output.wav> [speedScale]" >&2
  exit 1
fi

TEXT="$1"
SPEAKER="$2"
OUT="$3"
SPEED_SCALE="${4:-1.0}"
PORT="${VOICEVOX_PORT:-50021}"
BASE="http://localhost:${PORT}"

if ! curl -fsS "${BASE}/version" >/dev/null 2>&1; then
  echo "[voice.sh] VOICEVOX engine が応答しません（${BASE}）。voicevox-start.sh を先に実行してください" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

QUERY_JSON=$(curl -fsS -X POST \
  "${BASE}/audio_query?speaker=${SPEAKER}" \
  --get --data-urlencode "text=${TEXT}")

QUERY_JSON=$(echo "$QUERY_JSON" | jq --argjson speed "$SPEED_SCALE" '.speedScale = $speed')

curl -fsS -X POST \
  "${BASE}/synthesis?speaker=${SPEAKER}" \
  -H "Content-Type: application/json" \
  -d "$QUERY_JSON" \
  -o "$OUT"

echo "[voice.sh] wrote $OUT speedScale=${SPEED_SCALE} ($(du -h "$OUT" | cut -f1))"
