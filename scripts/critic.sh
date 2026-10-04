#!/usr/bin/env bash
# scripts/critic.sh — 従量 API の critic（Kagami）を外部プロセスとして呼び、成果物 md を残す（ADR-018）
#
# 用途:
#   team-lead が Opus 以上でない（Pro/Sonnet 運用）とき、設計判断（ミニADR / plan）を
#   プラン上限の外にある従量 API のモデル（既定: claude-opus-5）に反証させる。
#   出力は docs/plans/<slug>-critic.md に保存し、team-lead は plan の critic 節へ採否付きで転記する。
#
# 使い方:
#   scripts/critic.sh --target <反証対象.md> [--slug <slug>] [--ctx <添付ファイル>]... \
#                     [--model <model>] [--effort <low|medium|high|xhigh|max>] \
#                     [--instruction "<追加指示>"] [--out <出力パス>] [--mode <fable|opus|pro>] \
#                     [--no-auto-ctx] [--dry-run]
#
#   対象 md 内で参照されているリポジトリ内パス（`path` やリンク）は自動で添付候補にする（--no-auto-ctx で無効）。
#   サイズ上限を超える分は送らずにヘッダへ attach_skipped として列挙する（切り詰めは行わない）。
#
# 環境変数:
#   ANTHROPIC_API_KEY      API キー。**このラッパ内でのみ使う。** シェルプロファイルで export しないこと
#                          （Claude Code 本体が拾って従量課金に切り替わりうる）。
#                          解決順: 環境変数 → ~/.config/agent-crew/critic.env → <repo>/.env（gitignore 済み）
#   CRITIC_MODEL           既定 claude-opus-5（team-lead より強いことが非対称ルールの前提）
#   CRITIC_EFFORT          既定 xhigh
#   CRITIC_MAX_TOKENS      既定 32000（thinking を含む出力上限。1回あたりのコスト上限を兼ねる）
#   CRITIC_MAX_CTX_BYTES   既定 300000（対象＋添付の合計バイト上限。明示添付で超えたら送らずに終了、自動添付は超える分を見送る）
#   CRITIC_FALLBACK=1      安全分類器の拒否時に別モデルへ自動フォールバック（beta）。既定オフ
#   CRITIC_API_URL         既定 https://api.anthropic.com/v1/messages（テスト用に差し替え可）
#   CRITIC_NO_ENV_FILES=1  キーのファイル探索を行わない（テスト用）
#
# 月次上限は Console 側の Spend limit を前提とする（ラッパは1回上限のみ持つ）。
#
# 終了コード: 0 成功 / 1 引数・鍵・API エラー / 2 モデルが拒否（refusal）または本文なし

set -euo pipefail

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; }

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
TARGET=""; SLUG=""; OUT=""; INSTRUCTION=""; DRY_RUN=0; MODE="${CRITIC_MODE:-}"; AUTO_CTX=1
CTX_FILES=()
AUTO_FILES=(); SKIPPED=()
MODEL="${CRITIC_MODEL:-claude-opus-5}"
EFFORT="${CRITIC_EFFORT:-xhigh}"
MAX_TOKENS="${CRITIC_MAX_TOKENS:-32000}"
MAX_CTX_BYTES="${CRITIC_MAX_CTX_BYTES:-300000}"
API_URL="${CRITIC_API_URL:-https://api.anthropic.com/v1/messages}"
PERSONA_FILE="${REPO_ROOT}/.claude/agents/critic.md"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --slug) SLUG="$2"; shift 2 ;;
    --ctx) CTX_FILES+=("$2"); shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --effort) EFFORT="$2"; shift 2 ;;
    --instruction) INSTRUCTION="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --no-auto-ctx) AUTO_CTX=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "critic.sh: 不明な引数: $1" >&2; usage >&2; exit 1 ;;
  esac
done

for cmd in jq curl; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "critic.sh: $cmd が必要です" >&2; exit 1; }
done
[[ -n "$TARGET" ]] || { echo "critic.sh: --target は必須です" >&2; exit 1; }
[[ -f "$TARGET" ]] || { echo "critic.sh: 対象が見つかりません: $TARGET" >&2; exit 1; }
[[ -f "$PERSONA_FILE" ]] || { echo "critic.sh: ペルソナ定義が見つかりません: $PERSONA_FILE" >&2; exit 1; }
for f in "${CTX_FILES[@]+"${CTX_FILES[@]}"}"; do
  [[ -f "$f" ]] || { echo "critic.sh: 添付ファイルが見つかりません: $f" >&2; exit 1; }
done

# ---- サイズ上限（送る前に止める） ----
total_bytes=$(wc -c < "$TARGET")
for f in "${CTX_FILES[@]+"${CTX_FILES[@]}"}"; do
  total_bytes=$(( total_bytes + $(wc -c < "$f") ))
done
if (( total_bytes > MAX_CTX_BYTES )); then
  echo "critic.sh: 対象＋添付が ${total_bytes} bytes で上限 ${MAX_CTX_BYTES} を超えています。添付を絞るか CRITIC_MAX_CTX_BYTES を上げてください" >&2
  exit 1
fi

# ---- 自動添付: 対象 md が参照するリポジトリ内パスを候補にし、上限内で追加（超える分は見送って記録） ----
if (( AUTO_CTX )); then
  target_abs=$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")
  while IFS= read -r cand; do
    [[ -n "$cand" ]] || continue
    abs="${REPO_ROOT}/${cand}"
    [[ -f "$abs" ]] || continue
    [[ "$abs" == "$target_abs" ]] && continue
    dup=0
    for f in "${CTX_FILES[@]+"${CTX_FILES[@]}"}"; do
      [[ "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")" == "$abs" ]] && { dup=1; break; }
    done
    (( dup )) && continue
    sz=$(wc -c < "$abs")
    if (( total_bytes + sz > MAX_CTX_BYTES )); then SKIPPED+=("${cand} (${sz}B)"); continue; fi
    total_bytes=$(( total_bytes + sz ))
    CTX_FILES+=("$abs"); AUTO_FILES+=("$cand")
  done < <(grep -oE '`[A-Za-z0-9_./-]+\.[A-Za-z0-9]+`|\]\([A-Za-z0-9_./-]+\)' "$TARGET" \
            | sed -E 's/^`//; s/`$//; s/^\]\(//; s/\)$//' | grep -vE '^(https?:|#)' | sed -E 's#^\./##' | sort -u)
fi

# ---- slug / 出力パス ----
if [[ -z "$SLUG" ]]; then
  SLUG=$(basename "$TARGET"); SLUG="${SLUG%.*}"
fi
if [[ -z "$OUT" ]]; then
  OUT="${REPO_ROOT}/docs/plans/${SLUG}-critic.md"
  n=2
  while [[ -e "$OUT" ]]; do OUT="${REPO_ROOT}/docs/plans/${SLUG}-critic-${n}.md"; n=$((n+1)); done
fi

# ---- system prompt: critic.md 本文（frontmatter 除去）＋ API 用の注意書き ----
PERSONA=$(awk 'BEGIN{fm=0} NR==1 && /^---$/ {fm=1; next} fm==1 && /^---$/ {fm=2; next} fm!=1 {print}' "$PERSONA_FILE")
SYSTEM_PROMPT="${PERSONA}

---

## この実行の前提（従量 API から呼ばれている）

あなたはいま Claude Code のサブエージェントではなく、外部プロセス（scripts/critic.sh）から従量 API 経由で呼ばれている。Read/Grep/Glob などのツールは使えない。裏取りは、このメッセージに添付されたファイルの範囲でのみ行うこと。添付されていないファイルの内容を推測して根拠にしてはならない。確認できない点は「未確認（添付なし）」と明記し、反証の強さを「弱」に留める。**強（CRITICAL）には、対象または添付ファイル内の該当箇所の引用（ファイル名と原文）を必ず添える** — 引用できない指摘は中以下に留める。反証命題の件数は 0〜5 個でよく、件数を揃えるために強さを上げてはならない。該当が無ければ「確認した範囲と限界」だけを書く。出力は報告フォーマットのとおり Markdown で書く。"

# ---- user message: 対象 ＋ 添付 ----
build_user_message() {
  printf '%s\n\n' "以下の決定を反証せよ。反証命題は該当がある分だけ（最大5個）、各命題に 強(CRITICAL)/中(MAJOR)/弱(MINOR)・根拠（引用）・修正提案を付け、最後に総合判定を一言で示すこと。"
  if [[ -n "$INSTRUCTION" ]]; then printf '追加指示: %s\n\n' "$INSTRUCTION"; fi
  printf '# 反証対象: %s\n\n' "$TARGET"
  cat "$TARGET"; printf '\n\n'
  if (( ${#CTX_FILES[@]} > 0 )); then
    printf '# 添付ファイル（裏取り用。ここにあるものだけが確認可能な事実）\n\n'
    for f in "${CTX_FILES[@]}"; do
      printf -- '---\n\n## 添付: %s\n\n' "$f"
      cat "$f"; printf '\n\n'
    done
  else
    printf '# 添付ファイル: なし（リポジトリの実体は確認できない前提で反証すること）\n'
  fi
}
USER_MSG=$(build_user_message)

# ---- リクエスト JSON ----
REQUEST=$(jq -n \
  --arg model "$MODEL" \
  --arg system "$SYSTEM_PROMPT" \
  --arg user "$USER_MSG" \
  --arg effort "$EFFORT" \
  --argjson max_tokens "$MAX_TOKENS" \
  --argjson fallback "${CRITIC_FALLBACK:-0}" \
  '{
    model: $model,
    max_tokens: $max_tokens,
    stream: true,
    thinking: {type: "adaptive"},
    output_config: {effort: $effort},
    system: $system,
    messages: [{role: "user", content: $user}]
  } + (if $fallback == 1 then {fallbacks: "default"} else {} end)')

if (( DRY_RUN )); then
  printf '%s\n' "$REQUEST"
  echo "critic.sh: dry-run（API 呼び出しなし）。出力予定: $OUT" >&2
  echo "critic.sh: 添付 ${#CTX_FILES[@]} 件（自動 ${#AUTO_FILES[@]} 件）、見送り ${#SKIPPED[@]} 件、合計 ${total_bytes} bytes" >&2
  exit 0
fi

# ---- API キー解決（ラッパ内でのみ使用） ----
read_key_from_file() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  # `source` はしない（任意コードの実行を避ける）。ANTHROPIC_API_KEY=... の行だけを読む
  sed -n 's/^[[:space:]]*\(export[[:space:]]\+\)\{0,1\}ANTHROPIC_API_KEY[[:space:]]*=[[:space:]]*//p' "$f" | tail -n 1 | tr -d '"'"'" | tr -d '\r'
}
API_KEY="${ANTHROPIC_API_KEY:-}"
if [[ -z "$API_KEY" && "${CRITIC_NO_ENV_FILES:-0}" != "1" ]]; then
  API_KEY=$(read_key_from_file "${HOME}/.config/agent-crew/critic.env" || true)
  [[ -n "$API_KEY" ]] || API_KEY=$(read_key_from_file "${REPO_ROOT}/.env" || true)
fi
if [[ -z "$API_KEY" ]]; then
  cat >&2 <<'EOF'
critic.sh: ANTHROPIC_API_KEY が見つかりません。
  推奨: ~/.config/agent-crew/critic.env に `ANTHROPIC_API_KEY=sk-ant-...` を置く（chmod 600）。
  シェルプロファイルで export しないこと（Claude Code 本体が拾って従量課金に切り替わりうる）。
  Console 側で Spend limit を設定してから使うこと（ADR-018）。
EOF
  exit 1
fi

# ---- 呼び出し（ストリーミングで受け、SSE を jq で組み立てる） ----
TMPDIR_C=$(mktemp -d "${TMPDIR:-/tmp}/critic.XXXXXX")
trap 'rm -rf "$TMPDIR_C"' EXIT
RAW="${TMPDIR_C}/raw.sse"
REQ_FILE="${TMPDIR_C}/request.json"
printf '%s' "$REQUEST" > "$REQ_FILE"

HEADERS=(-H "x-api-key: ${API_KEY}" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" -H "accept: text/event-stream")
if [[ "${CRITIC_FALLBACK:-0}" == "1" ]]; then
  HEADERS+=(-H "anthropic-beta: server-side-fallback-2026-07-01")
fi

STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
HTTP_CODE=$(curl -sS -N --max-time "${CRITIC_TIMEOUT_SEC:-900}" -o "$RAW" -w '%{http_code}' \
  "${HEADERS[@]}" -X POST "$API_URL" --data-binary @"$REQ_FILE" || echo "000")
unset API_KEY

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "critic.sh: API エラー (HTTP $HTTP_CODE)" >&2
  head -c 2000 "$RAW" >&2 || true; echo >&2
  exit 1
fi

DATA=$(grep '^data: ' "$RAW" | sed 's/^data: //' || true)
if [[ -z "$DATA" ]]; then
  echo "critic.sh: SSE データがありません（レスポンス先頭）:" >&2; head -c 1000 "$RAW" >&2; echo >&2
  exit 1
fi
API_ERR=$(printf '%s\n' "$DATA" | jq -r 'select(.type=="error") | .error.message // "unknown error"' 2>/dev/null | head -n 1 || true)
BODY=$(printf '%s\n' "$DATA" | jq -j 'select(.type=="content_block_delta" and .delta.type=="text_delta") | .delta.text' 2>/dev/null || true)
RESP_MODEL=$(printf '%s\n' "$DATA" | jq -r 'select(.type=="message_start") | .message.model // empty' 2>/dev/null | tail -n 1 || true)
STOP_REASON=$(printf '%s\n' "$DATA" | jq -r 'select(.type=="message_delta") | .delta.stop_reason // empty' 2>/dev/null | tail -n 1 || true)
IN_TOK=$(printf '%s\n' "$DATA" | jq -r 'select(.type=="message_start") | .message.usage.input_tokens // 0' 2>/dev/null | tail -n 1 || echo 0)
CACHE_READ=$(printf '%s\n' "$DATA" | jq -r 'select(.type=="message_start") | .message.usage.cache_read_input_tokens // 0' 2>/dev/null | tail -n 1 || echo 0)
OUT_TOK=$(printf '%s\n' "$DATA" | jq -r 'select(.type=="message_delta") | .usage.output_tokens // empty' 2>/dev/null | tail -n 1 || echo 0)
[[ -n "$OUT_TOK" ]] || OUT_TOK=0

if [[ -n "$API_ERR" ]]; then
  echo "critic.sh: API がエラーを返しました: $API_ERR" >&2
  exit 1
fi

# CRITICAL 件数（近似: 「強さ: 強(CRITICAL)」形式の行を数える。凡例行 [強/中/弱 を併記] は除外）
CRITICAL_COUNT=$(printf '%s\n' "$BODY" | grep -E '強さ[:：].*CRITICAL' | grep -vE 'MAJOR.*MINOR' | wc -l | tr -d ' ')
VERDICT=$(printf '%s\n' "$BODY" | grep -E '採択可|差し戻し' | tail -n 1 || true)

CTX_LIST="なし"
if (( ${#CTX_FILES[@]} > 0 )); then CTX_LIST=$(printf '%s, ' "${CTX_FILES[@]}"); CTX_LIST="${CTX_LIST%, }"; fi
AUTO_LIST="なし"
if (( ${#AUTO_FILES[@]} > 0 )); then AUTO_LIST=$(printf '%s, ' "${AUTO_FILES[@]}"); AUTO_LIST="${AUTO_LIST%, }"; fi
SKIP_FLAG="no"; SKIP_LIST=""
if (( ${#SKIPPED[@]} > 0 )); then SKIP_FLAG="yes"; SKIP_LIST=$(printf '%s, ' "${SKIPPED[@]}"); SKIP_LIST="${SKIP_LIST%, }"; fi

mkdir -p "$(dirname "$OUT")"
{
  echo "# critic: ${SLUG}"
  echo
  echo "- **日時**: ${STARTED_AT}"
  echo "- **対象**: \`${TARGET}\`"
  echo "- **添付**: ${CTX_LIST}"
  echo "- **自動添付**: ${AUTO_LIST}"
  echo "- **attach_skipped**: ${SKIP_FLAG}${SKIP_LIST:+ — ${SKIP_LIST}}"
  echo "- **mode（呼び出し時の team-lead）**: ${MODE:-未指定}"
  echo "- **モデル**: ${RESP_MODEL:-$MODEL}（要求: ${MODEL}, effort: ${EFFORT}）"
  echo "- **stop_reason**: ${STOP_REASON:-unknown}"
  echo "- **usage**: input=${IN_TOK} (cache_read=${CACHE_READ}) output=${OUT_TOK}"
  echo "- **CRITICAL 件数（近似・要目視）**: ${CRITICAL_COUNT}"
  echo "- **総合判定行**: ${VERDICT:-（検出できず）}"
  echo "- **採否**: team-lead が plan の critic 節に転記する。plan の mode が pro なら CRITICAL は却下不可（例外: 決定的コマンドの生出力で事実誤認を示せる場合。attach_skipped: yes の回は対象外）（ADR-018）"
  echo
  echo "---"
  echo
  if [[ -n "$BODY" ]]; then printf '%s\n' "$BODY"; else echo "（本文なし）"; fi
} > "$OUT"

echo "critic.sh: 成果物 → ${OUT}"
echo "critic.sh: model=${RESP_MODEL:-$MODEL} stop=${STOP_REASON:-?} usage in=${IN_TOK} out=${OUT_TOK} CRITICAL≈${CRITICAL_COUNT}"
[[ -n "$VERDICT" ]] && echo "critic.sh: 総合判定: ${VERDICT}"

if [[ "$STOP_REASON" == "refusal" || -z "$BODY" ]]; then
  echo "critic.sh: モデルが拒否したか本文が空です（stop_reason=${STOP_REASON:-?}）。CRITIC_FALLBACK=1 で再試行できます" >&2
  exit 2
fi
exit 0
