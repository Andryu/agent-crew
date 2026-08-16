#!/usr/bin/env bash
# scripts/model-mode.sh
#
# team-lead（メインセッション）の実効モデルを検知し、モデル運用モードを1行で出力する（ADR-017）。
# 用途:
#   - UserPromptSubmit フック: 毎ターン1行をコンテキストに注入する（工程の想起）
#   - SessionStart フック（session_start.sh から呼ぶ）: セッション開始時の表示
#
# モデルの解決順（設定ファイルは実体と乖離しうるため最後）:
#   1. フック入力 JSON（stdin）の .model
#   2. .transcript_path の直近 assistant メッセージの .message.model
#   3. ~/.claude/settings.json の .model
#   4. "unknown"
#
# 常に exit 0。stdin が無い／jq が無い場合も静かに縮退する。

set -uo pipefail

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

INPUT=""
if [ ! -t 0 ]; then
  INPUT=$(cat 2>/dev/null || true)
fi

MODEL=""
SOURCE=""

# 1. hook input の model
if [[ -n "$INPUT" ]]; then
  MODEL=$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)
  [[ -n "$MODEL" ]] && SOURCE="hook"
fi

# 2. transcript の直近 assistant メッセージ
if [[ -z "$MODEL" && -n "$INPUT" ]]; then
  TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
  if [[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]]; then
    # assistant 行だけを grep で先に絞る（ツール呼び出しの多いターンでも取りこぼさない。全走査でも数十ms）
    MODEL=$(grep '"type":"assistant"' "$TRANSCRIPT" 2>/dev/null | tail -n 50 \
      | jq -r 'select(.type=="assistant") | .message.model // empty' 2>/dev/null \
      | grep -v '<synthetic>' | tail -n 1 || true)
    [[ -n "$MODEL" ]] && SOURCE="transcript"
  fi
fi

# 3. settings.json
if [[ -z "$MODEL" ]]; then
  MODEL=$(jq -r '.model // empty' "${HOME}/.claude/settings.json" 2>/dev/null || true)
  [[ -n "$MODEL" ]] && SOURCE="settings"
fi

[[ -z "$MODEL" ]] && MODEL="unknown" && SOURCE="none"

# effort（hook input にあれば）
EFFORT=""
if [[ -n "$INPUT" ]]; then
  EFFORT=$(printf '%s' "$INPUT" | jq -r '.effort.level // empty' 2>/dev/null || true)
fi
[[ -z "$EFFORT" ]] && EFFORT=$(jq -r '.effortLevel // "high"' "${HOME}/.claude/settings.json" 2>/dev/null || echo "high")

# 表示用: モデルIDから系統名を短縮
case "$MODEL" in
  *fable*)  FAMILY="fable" ;;
  *opus*)   FAMILY="opus" ;;
  *sonnet*) FAMILY="sonnet" ;;
  *haiku*)  FAMILY="haiku" ;;
  *)        FAMILY="$MODEL" ;;
esac

# fail-closed: Fable モードと断定してよいのは実体（hook 入力 / transcript）で確認できたときだけ。
# settings.json のみ（初回ターン等）では「fable」と書いてあっても実体は Opus でありうるため、fable-class ON 側に倒す。
if [[ "$FAMILY" == "fable" && ( "$SOURCE" == "hook" || "$SOURCE" == "transcript" ) ]]; then
  echo "[team-lead=${FAMILY} effort=${EFFORT} src=${SOURCE}] Fable モード: fable-class は中〜大規模タスクで発動（ADR-017）"
else
  [[ "$FAMILY" == "fable" ]] && FAMILY="fable?(未確認)"
  echo "[team-lead=${FAMILY} effort=${EFFORT} src=${SOURCE}] fable-class ON: complexity≥M or risk≥medium → SPEC/PLAN を docs/plans/ に残す, ミニADRは critic(Kagami,opus) で反証してから確定, ルーティング表 v2 = .claude/skills/fable-class/SKILL.md（ADR-017）"
fi

exit 0
