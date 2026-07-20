#!/usr/bin/env bash
#
# animate.sh — Meta AnimatedDrawings のレンダリングラッパー
#
# アノテーション済みキャラクター（char_cfg.yaml, mask.png, texture.png を含むディレクトリ）に
# モーションを適用し、MP4として書き出す。
#
# 使い方:
#   video-studio/scripts/animate.sh <char_anno_dir> <motion_name> <output_mp4_path> [retarget_cfg]
#
# 引数:
#   char_anno_dir    キャラのアノテーション済みディレクトリ（char_cfg.yaml を含む）
#                     例: ~/Workspace/video-tools/AnimatedDrawings/examples/characters/char1
#   motion_name       モーション名（walk/jump/wave等）またはBVH motion configへのパス
#                     組み込みプリセット: dab, jesse_dance, jumping_jacks, jumping, wave_hello, zombie
#                     ※ "jump" は jumping、"wave" は wave_hello のエイリアスとして解決する
#   output_mp4_path   出力するMP4ファイルのパス
#   retarget_cfg      (省略可) retarget configへのパス。デフォルトは fair1_spf.yaml
#                     （examples/characters/char1〜char6 と同じ骨格を使う自作アノテーションに対応）
#
# 環境変数:
#   ANIMATED_DRAWINGS_ROOT   AnimatedDrawingsリポジトリのルート（デフォルト: ~/Workspace/video-tools/AnimatedDrawings）
#   CONDA_ENV_NAME           condaの環境名（デフォルト: animated_drawings）
#   USE_MESA                 1 を指定すると view.USE_MESA: True を設定してレンダリングする
#                             （このリポジトリではmacOSネイティブのオフスクリーンGLFWで問題なく動作したため通常は不要）
#   CAMERA_POS / CAMERA_FWD  カメラ位置・向きを上書きする（"x,y,z" 形式、カンマ or スペース区切り）。
#                             デフォルトは胸から上がフレームの6割以上を占める胸像構図
#                             （CAMERA_POS=0,0.55,2.2 / CAMERA_FWD=0,0.35,2.2）にチューニング済み。
#                             AnimatedDrawings同梱サンプルは自動アノテーションで胴体・腕までしか
#                             マスクに含まれないことが多く（脚が別の輪郭として除外されるため）、
#                             全身が写る前提のカメラ距離にするとキャラが小さく見切れて写る。
#                             キャラの体格が大きく異なる場合は個別に調整すること。
#
# 例:
#   video-studio/scripts/animate.sh \
#     ~/Workspace/video-tools/AnimatedDrawings/examples/characters/char1 \
#     jump \
#     ./out/char1_jump.mp4
#
#   CAMERA_POS="0,0.6,2.4" CAMERA_FWD="0,0.4,2.4" \
#   video-studio/scripts/animate.sh ... （カメラを個別調整する場合）

set -euo pipefail

ANIMATED_DRAWINGS_ROOT="${ANIMATED_DRAWINGS_ROOT:-$HOME/Workspace/video-tools/AnimatedDrawings}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-animated_drawings}"

usage() {
  echo "使い方: $0 <char_anno_dir> <motion_name> <output_mp4_path> [retarget_cfg]" >&2
  exit 1
}

if [[ $# -lt 3 ]]; then
  usage
fi

CHAR_ANNO_DIR="$1"
MOTION_NAME="$2"
OUTPUT_MP4_PATH="$3"
RETARGET_CFG="${4:-}"

if [[ ! -d "$ANIMATED_DRAWINGS_ROOT" ]]; then
  echo "エラー: AnimatedDrawingsが見つかりません: $ANIMATED_DRAWINGS_ROOT" >&2
  echo "ANIMATED_DRAWINGS_ROOT環境変数で場所を指定するか、READMEに従ってcloneしてください。" >&2
  exit 1
fi

if [[ ! -f "$CHAR_ANNO_DIR/char_cfg.yaml" ]]; then
  echo "エラー: char_cfg.yaml が見つかりません: $CHAR_ANNO_DIR/char_cfg.yaml" >&2
  echo "キャラのアノテーション済みディレクトリを指定してください。" >&2
  exit 1
fi

# モーション名 -> configファイルパスの解決
resolve_motion_cfg() {
  local name="$1"
  case "$name" in
    jump) name="jumping" ;;
    wave) name="wave_hello" ;;
  esac

  if [[ -f "$name" ]]; then
    echo "$name"
    return
  fi

  local candidate="$ANIMATED_DRAWINGS_ROOT/examples/config/motion/${name}.yaml"
  if [[ -f "$candidate" ]]; then
    echo "$candidate"
    return
  fi

  echo "" # not found
}

MOTION_CFG_FN="$(resolve_motion_cfg "$MOTION_NAME")"
if [[ -z "$MOTION_CFG_FN" ]]; then
  echo "エラー: モーション '$MOTION_NAME' が見つかりません。" >&2
  echo "利用可能なプリセット: $(ls "$ANIMATED_DRAWINGS_ROOT/examples/config/motion" | sed 's/\.yaml$//' | tr '\n' ' ')" >&2
  exit 1
fi

if [[ -z "$RETARGET_CFG" ]]; then
  RETARGET_CFG="$ANIMATED_DRAWINGS_ROOT/examples/config/retarget/fair1_spf.yaml"
fi
if [[ ! -f "$RETARGET_CFG" ]]; then
  echo "エラー: retarget config が見つかりません: $RETARGET_CFG" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_MP4_PATH")"

# conda環境をactivate
CONDA_BASE="$(conda info --base 2>/dev/null || true)"
if [[ -z "$CONDA_BASE" ]]; then
  echo "エラー: condaが見つかりません。setup-animated-drawings.md を参照してください。" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV_NAME"

USE_MESA_FLAG="${USE_MESA:-0}"
CAMERA_POS="${CAMERA_POS:-0,0.55,2.2}"
CAMERA_FWD="${CAMERA_FWD:-0,0.35,2.2}"

python - "$CHAR_ANNO_DIR" "$MOTION_CFG_FN" "$RETARGET_CFG" "$OUTPUT_MP4_PATH" "$USE_MESA_FLAG" "$CAMERA_POS" "$CAMERA_FWD" <<'PYEOF'
import sys
import yaml
from pathlib import Path
import animated_drawings.render as render

char_anno_dir, motion_cfg_fn, retarget_cfg_fn, output_mp4_path, use_mesa_flag, camera_pos_str, camera_fwd_str = sys.argv[1:8]


def parse_vec3(s: str):
    parts = [p for p in s.replace(',', ' ').split() if p]
    if len(parts) != 3:
        raise SystemExit(f"CAMERA_POS/CAMERA_FWD must have 3 components (x,y,z). Got: {s!r}")
    return [float(p) for p in parts]


mvc_cfg = {
    'scene': {
        'ANIMATED_CHARACTERS': [{
            'character_cfg': str(Path(char_anno_dir, 'char_cfg.yaml').resolve()),
            'motion_cfg': str(Path(motion_cfg_fn).resolve()),
            'retarget_cfg': str(Path(retarget_cfg_fn).resolve()),
        }]
    },
    'view': {
        'CAMERA_POS': parse_vec3(camera_pos_str),
        'CAMERA_FWD': parse_vec3(camera_fwd_str),
    },
    'controller': {
        'MODE': 'video_render',
        'OUTPUT_VIDEO_PATH': str(Path(output_mp4_path).resolve()),
        'OUTPUT_VIDEO_CODEC': 'avc1',
    },
}

if use_mesa_flag == '1':
    mvc_cfg['view']['USE_MESA'] = True

tmp_cfg_path = Path(char_anno_dir, '_animate_sh_mvc_cfg.yaml')
with open(tmp_cfg_path, 'w') as f:
    yaml.dump(mvc_cfg, f)

try:
    render.start(str(tmp_cfg_path))
finally:
    tmp_cfg_path.unlink(missing_ok=True)

print(f"\n生成完了: {output_mp4_path}")
PYEOF
