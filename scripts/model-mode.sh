#!/usr/bin/env bash
# scripts/model-mode.sh
#
# team-lead（メインセッション）の実効モデルを検知し、モデル運用モードを1行で出力する（ADR-017 / ADR-018）。
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

# fail-closed（ADR-017 → ADR-018 で拡張）:
#   - Fable/Opus モードと断定してよいのは実体（hook 入力 / transcript）で確認できたときだけ。
#   - settings.json のみ（初回ターン等）では「fable」「opus」と書いてあっても実体は Sonnet でありうるため、
#     最も厳しい側＝Pro 運用（ADR-018）に倒す。誤検知の害は厳しい側にしか出ない。
CONFIRMED=0
[[ "$SOURCE" == "hook" || "$SOURCE" == "transcript" ]] && CONFIRMED=1

if [[ "$FAMILY" == "fable" && "$CONFIRMED" == "1" ]]; then
  echo "[team-lead=${FAMILY} effort=${EFFORT} src=${SOURCE}] Fable モード: fable-class は中〜大規模タスクで発動（ADR-017）"
elif [[ "$FAMILY" == "opus" && "$CONFIRMED" == "1" ]]; then
  echo "[team-lead=${FAMILY} effort=${EFFORT} src=${SOURCE}] Opus モード（ADR-017）: fable-class ON: complexity≥M or risk≥medium → SPEC/PLAN を docs/plans/ に残す, ミニADRは critic(Kagami,opus) で反証してから確定, ルーティング表 v2 = docs/adr/ADR-017-opus-fable-parity.md §5"
else
  if [[ "$CONFIRMED" == "0" && ( "$FAMILY" == "fable" || "$FAMILY" == "opus" ) ]]; then FAMILY="${FAMILY}?(未確認)"; fi
  echo "[team-lead=${FAMILY} effort=${EFFORT} src=${SOURCE}] Pro 運用（ADR-018）: fable-class ON: complexity≥S（ほぼ全タスク）→ SPEC/PLAN を docs/plans/ に残す。免除は「1ファイル・既存関数の局所修正・テスト有・設計判断なし」の4条件全てを rg/fd/git status で確認したときのみ。設計=ultrathink, 実装=Codex(herdr), 探索・列挙=rg/fd/jq（LLMに投げない）, レビュー=fresh Sonnet, risk high の critic=scripts/critic.sh（従量API, CRITICAL は却下不可）, ルーティング表 v3 = .claude/skills/fable-class/SKILL.md"
fi

exit 0
