#!/usr/bin/env bash
# 「落書きショート」テンプレートで episode.json をレンダリングするラッパー。
#
# 使い方:
#   video-studio/scripts/render.sh <エピソードディレクトリ>
#   video-studio/scripts/render.sh episodes/ep01
#   video-studio/scripts/render.sh ep01               # video-studio/episodes/ep01 と解釈
#
# 出力先: <エピソードディレクトリ>/out/<episodeId>.mp4
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VIDEO_STUDIO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REMOTION_DIR="${VIDEO_STUDIO_DIR}/remotion"

if [ $# -lt 1 ]; then
  echo "使い方: $0 <エピソードディレクトリ> [出力ファイル名]" >&2
  echo "例:   $0 ep01" >&2
  echo "例:   $0 episodes/ep01" >&2
  exit 1
fi

EPISODE_ARG="$1"

# "ep01" のような短縮指定なら episodes/ep01 に解決する
if [ -d "${VIDEO_STUDIO_DIR}/episodes/${EPISODE_ARG}" ]; then
  EPISODE_DIR="${VIDEO_STUDIO_DIR}/episodes/${EPISODE_ARG}"
elif [ -d "${EPISODE_ARG}" ]; then
  EPISODE_DIR="$(cd "${EPISODE_ARG}" && pwd)"
else
  echo "エピソードディレクトリが見つかりません: ${EPISODE_ARG}" >&2
  exit 1
fi

EPISODE_JSON="${EPISODE_DIR}/episode.json"
if [ ! -f "${EPISODE_JSON}" ]; then
  echo "episode.json が見つかりません: ${EPISODE_JSON}" >&2
  exit 1
fi

EPISODE_ID="$(basename "${EPISODE_DIR}")"
OUT_DIR="${EPISODE_DIR}/out"
OUT_FILE="${2:-${OUT_DIR}/${EPISODE_ID}.mp4}"

mkdir -p "${OUT_DIR}"

if [ ! -d "${REMOTION_DIR}/node_modules" ]; then
  echo "node_modules がありません。先に (cd ${REMOTION_DIR} && npm install) を実行してください。" >&2
  exit 1
fi

echo "レンダリング開始: episode=${EPISODE_ID} -> ${OUT_FILE}"

cd "${REMOTION_DIR}"
npx remotion render doodle-short "${OUT_FILE}" --props="{\"episodeId\":\"${EPISODE_ID}\"}"

echo "完了: ${OUT_FILE}"
