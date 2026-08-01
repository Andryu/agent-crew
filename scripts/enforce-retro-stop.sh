#!/usr/bin/env bash
# scripts/enforce-retro-stop.sh
#
# Stop フック用スクリプト（Issue #128）。
# スプリントの全実装タスクが DONE なのにレトロスペクティブ（みゆきち）が
# 未実施のままセッションを終了しようとした場合、stderr に警告メッセージを
# 出力する。
#
# 設計方針（risk_level: high につき明記）:
#   このスクリプトは Stop を「ブロック」しない（exit 2 は使わない）。
#   常に exit 0 で終了し、警告は stderr へのメッセージのみとする。
#   誤検知でセッション終了そのものを止めてしまうリスクの方が、
#   レトロ未実施の見逃しより深刻と判断したため。
#
# バイパス条件（いずれか1つでも満たせば即 exit 0、警告なし）:
#   1. .claude/_queue.json が存在しない、またはスプリント外（.sprint フィールドなし）
#   2. レトロタスク（slug に "retro" を含むタスク）の status が DONE
#   3. レトロ完了マーカー docs/sprints/<sprint>-retro.md が実在する
#
# 上記いずれにも該当せず、かつ「レトロタスク以外の全タスクが DONE」の場合のみ
# 警告メッセージを出す。

set -uo pipefail
# 注意: set -e は使わない。途中の jq/git コマンドが失敗しても
# 「警告を出さずに exit 0」へ安全にフォールスルーさせるため。

# ---------- 前提コマンドの確認 ----------

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [[ -z "$REPO_ROOT" ]]; then
  exit 0
fi

QUEUE_FILE="$REPO_ROOT/.claude/_queue.json"

# --- バイパス条件1: キューが存在しない / スプリント外 ---
if [[ ! -f "$QUEUE_FILE" ]]; then
  exit 0
fi

if ! jq -e . "$QUEUE_FILE" >/dev/null 2>&1; then
  # JSONとして壊れている場合も判定不能なので警告せず抜ける
  exit 0
fi

SPRINT=$(jq -r '.sprint // empty' "$QUEUE_FILE" 2>/dev/null)
if [[ -z "$SPRINT" ]]; then
  exit 0
fi

# --- レトロタスクの検出（slug に "retro" を含む最後のタスクを対象とする） ---
RETRO_SLUG=$(jq -r '
  [.tasks[]? | select(.slug // "" | test("retro"; "i"))] |
  if length > 0 then .[-1].slug else "" end
' "$QUEUE_FILE" 2>/dev/null)

if [[ -z "$RETRO_SLUG" ]]; then
  # このスプリントにレトロタスクが定義されていない（テンプレート等）
  exit 0
fi

RETRO_STATUS=$(jq -r --arg slug "$RETRO_SLUG" '
  [.tasks[]? | select(.slug == $slug)] |
  if length > 0 then .[-1].status else "" end
' "$QUEUE_FILE" 2>/dev/null)

# --- バイパス条件2: レトロタスクが DONE ---
if [[ "$RETRO_STATUS" == "DONE" ]]; then
  exit 0
fi

# --- バイパス条件3: レトロ完了マーカーファイルが実在する ---
MARKER_FILE="$REPO_ROOT/docs/sprints/${SPRINT}-retro.md"
if [[ -f "$MARKER_FILE" ]]; then
  exit 0
fi

# ---------- ここまで到達 = 3条件すべて未充足 ----------
# 「レトロタスク以外の全実装タスクが DONE」の場合のみ警告する。
# （スプリントがまだ進行中なら、レトロ未実施は当然なので警告しない）

NON_RETRO_TOTAL=$(jq -r --arg slug "$RETRO_SLUG" '
  [.tasks[]? | select(.slug != $slug)] | length
' "$QUEUE_FILE" 2>/dev/null)

NON_RETRO_DONE=$(jq -r --arg slug "$RETRO_SLUG" '
  [.tasks[]? | select(.slug != $slug and .status == "DONE")] | length
' "$QUEUE_FILE" 2>/dev/null)

if [[ "$NON_RETRO_TOTAL" -gt 0 && "$NON_RETRO_TOTAL" == "$NON_RETRO_DONE" ]]; then
  {
    echo ""
    echo "⚠️  [enforce-retro-stop] スプリント '${SPRINT}' の実装タスクは全て DONE ですが、"
    echo "    レトロスペクティブ（みゆきち, slug: ${RETRO_SLUG}）がまだ完了していません。"
    echo "    docs/sprints/${SPRINT}-retro.md も未作成です。"
    echo "    「みゆきちを呼んで」等で振り返りを実施してから終了することを推奨します。"
    echo "    （このメッセージは警告のみで、セッション終了はブロックされません）"
    echo ""
  } >&2
fi

exit 0
