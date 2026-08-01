#!/usr/bin/env bash
# scripts/audit-scan.sh
#
# 組織憲章第3条「最小権限」の Enforcement を実運用化するスキャンスクリプト
# （Sprint-26 audit-scan-design / audit-scan-impl, Issue #140系）。
#
# 本スクリプトは "enforce" ではなく "スキャン・報告" が役割であり、
# enforce-retro-stop.sh 等と異なり Bash 実行を能動的にブロックする用途では
# 使わない。終了コードは呼び出し側（Rin/Yuki/Kai）が次アクション判断に使う
# 入力に留める。
#
# 使い方:
#   scripts/audit-scan.sh [--sprint <sprint-name>] [--out <report-path>]
#
#   --sprint  : 突合対象のスプリント計画書を明示指定
#               （省略時は .claude/_queue.json の .sprint から自動解決。
#                 キューが無い場合は permissions.allow チェックのみ SKIP し、
#                 symlink / hooks チェックは実行する）
#   --out     : Markdownレポートの保存先（省略時は標準出力のみ）
#
# チェック項目:
#   1. permissions.allow 整合性（スプリント計画書に記載のない新規追加を検知）
#   2. symlink 健全性（リンク切れ・自己参照）
#   3. .claude/settings.json hooks の構文・生存確認
#
# 終了コード:
#   0 : 全チェック PASS（SKIP・WARNINGのみは0で問題ない）
#   1 : 1件以上 FAIL あり
#   2 : スクリプト自体の実行前提エラー（jq 不在・settings.json 自体が読めない等）

set -uo pipefail
# 注意: set -e は使わない。個々のチェック内でコマンドが失敗しても、
# そのチェックだけを FAIL/SKIP として記録し、他のチェックは継続するため。

# ---------- 引数パース ----------

SPRINT=""
OUT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sprint)
      SPRINT="${2:-}"
      shift 2
      ;;
    --out)
      OUT_PATH="${2:-}"
      shift 2
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      echo "usage: $0 [--sprint <sprint-name>] [--out <report-path>]" >&2
      exit 2
      ;;
  esac
done

# ---------- 前提コマンドの確認（実行前提エラー = exit 2） ----------

for cmd in jq git find readlink; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: 前提コマンドが見つかりません: $cmd" >&2
    exit 2
  fi
done

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [[ -z "$REPO_ROOT" ]]; then
  echo "ERROR: git リポジトリのルートが取得できません" >&2
  exit 2
fi
cd "$REPO_ROOT" || { echo "ERROR: リポジトリルートへ移動できません" >&2; exit 2; }

SETTINGS_FILE="$REPO_ROOT/.claude/settings.json"
if [[ ! -f "$SETTINGS_FILE" ]]; then
  echo "ERROR: $SETTINGS_FILE が見つかりません" >&2
  exit 2
fi

QUEUE_FILE="$REPO_ROOT/.claude/_queue.json"

# --sprint 省略時は _queue.json の .sprint から自動解決
if [[ -z "$SPRINT" ]]; then
  if [[ -f "$QUEUE_FILE" ]] && jq -e . "$QUEUE_FILE" >/dev/null 2>&1; then
    SPRINT=$(jq -r '.sprint // empty' "$QUEUE_FILE" 2>/dev/null)
  fi
fi

# ========================================================================
# 3.1 permissions.allow 整合性チェック
# ========================================================================

PERM_RESULT="PASS"
PERM_DETAIL_LINES=()

if [[ -z "$SPRINT" ]]; then
  PERM_RESULT="SKIP"
  PERM_DETAIL_LINES+=("SKIP: スプリント不明（_queue.json が無いか .sprint フィールドなし）")
else
  PLAN_FILE="$REPO_ROOT/docs/sprints/${SPRINT}.md"
  if [[ ! -f "$PLAN_FILE" ]]; then
    PERM_RESULT="SKIP"
    PERM_DETAIL_LINES+=("SKIP: スプリント計画書が見つかりません（${PLAN_FILE}）")
  else
    BASE_COMMIT=$(git merge-base origin/main HEAD 2>/dev/null || true)
    if [[ -z "$BASE_COMMIT" ]]; then
      PERM_RESULT="SKIP"
      PERM_DETAIL_LINES+=("SKIP: merge-base不明（origin/main から分岐したブランチではありません）")
    else
      BASE_PERMS=$(git show "${BASE_COMMIT}:.claude/settings.json" 2>/dev/null | jq -r '.permissions.allow[]?' 2>/dev/null | sort -u || true)
      CURRENT_PERMS=$(jq -r '.permissions.allow[]?' "$SETTINGS_FILE" 2>/dev/null | sort -u || true)
      NEW_ENTRIES=$(comm -13 <(echo "$BASE_PERMS") <(echo "$CURRENT_PERMS") 2>/dev/null || true)

      if [[ -z "$NEW_ENTRIES" ]]; then
        PERM_DETAIL_LINES+=("新規追加なし、または全件計画書に記載あり")
      else
        UNDOCUMENTED=0
        while IFS= read -r entry; do
          [[ -z "$entry" ]] && continue
          if grep -F -q -- "$entry" "$PLAN_FILE" 2>/dev/null; then
            continue
          fi
          UNDOCUMENTED=1
          PERM_DETAIL_LINES+=("[FAIL] \"${entry}\" — スプリント計画書に言及なし")
        done <<< "$NEW_ENTRIES"

        if [[ "$UNDOCUMENTED" -eq 1 ]]; then
          PERM_RESULT="FAIL"
        else
          PERM_DETAIL_LINES+=("新規追加なし、または全件計画書に記載あり")
        fi
      fi
    fi
  fi
fi

# ========================================================================
# 3.2 symlink 健全性チェック
# ========================================================================

SYMLINK_RESULT="PASS"
SYMLINK_FAIL_COUNT=0
SYMLINK_DETAIL_LINES=()

SYMLINKS=$(find "$REPO_ROOT" -type l \
  -not -path '*/.git/*' \
  -not -path '*/node_modules/*' \
  -not -path '*/.claude-worktrees/*' \
  2>/dev/null || true)

if [[ -n "$SYMLINKS" ]]; then
  while IFS= read -r link; do
    [[ -z "$link" ]] && continue
    rel_link="${link#"$REPO_ROOT"/}"

    if [[ ! -e "$link" ]]; then
      target=$(readlink "$link" 2>/dev/null || echo "?")
      SYMLINK_DETAIL_LINES+=("[FAIL] ${rel_link} — リンク切れ（参照先: ${target}）")
      SYMLINK_FAIL_COUNT=$((SYMLINK_FAIL_COUNT + 1))
      continue
    fi

    resolved=$(readlink -f "$link" 2>/dev/null || true)
    raw_target=$(readlink "$link" 2>/dev/null || true)
    if [[ -z "$resolved" ]] || [[ "$raw_target" == "$link" ]]; then
      SYMLINK_DETAIL_LINES+=("[FAIL] ${rel_link} — 自己参照（ループ）の疑い")
      SYMLINK_FAIL_COUNT=$((SYMLINK_FAIL_COUNT + 1))
    fi
  done <<< "$SYMLINKS"
fi

if [[ "$SYMLINK_FAIL_COUNT" -gt 0 ]]; then
  SYMLINK_RESULT="FAIL (${SYMLINK_FAIL_COUNT}件)"
else
  SYMLINK_DETAIL_LINES+=("該当なし")
fi

# ========================================================================
# 3.3 hooks 構文・生存確認
# ========================================================================

HOOKS_RESULT="PASS"
HOOKS_FAIL_COUNT=0
HOOKS_WARN_COUNT=0
HOOKS_DETAIL_LINES=()

if ! jq -e . "$SETTINGS_FILE" >/dev/null 2>&1; then
  HOOKS_RESULT="FAIL (1件)"
  HOOKS_FAIL_COUNT=1
  HOOKS_DETAIL_LINES+=("[FAIL] ${SETTINGS_FILE} — JSON構文エラーのため以降のhooksチェックを中断")
else
  COMMANDS=$(jq -r '.hooks // {} | to_entries[]? | .value[]? | .hooks[]?.command // empty' "$SETTINGS_FILE" 2>/dev/null || true)

  if [[ -n "$COMMANDS" ]]; then
    while IFS= read -r cmd; do
      [[ -z "$cmd" ]] && continue

      hook_path="${cmd%% *}"
      if [[ "$hook_path" == *.sh ]]; then
        # 先頭トークンが *.sh のコマンド（.claude/hooks/*.sh・scripts/*.sh 等の
        # 直接呼び出し。末尾の `|| true` 等は許容 — Issue #140系QA指摘、
        # 監査対象自身（enforce-queue-done-stop.sh 等）が監査をすり抜けないため）
        if [[ ! -f "$REPO_ROOT/$hook_path" ]]; then
          HOOKS_DETAIL_LINES+=("[FAIL] ${hook_path} — ファイルが存在しない")
          HOOKS_FAIL_COUNT=$((HOOKS_FAIL_COUNT + 1))
        elif [[ ! -x "$REPO_ROOT/$hook_path" ]]; then
          HOOKS_DETAIL_LINES+=("[FAIL] ${hook_path} — 実行権限がない")
          HOOKS_FAIL_COUNT=$((HOOKS_FAIL_COUNT + 1))
        fi
      elif [[ "$cmd" =~ ^bash\ -c\ \'(.*)\'$ ]]; then
        inner="${BASH_REMATCH[1]}"
        if ! bash -n <<< "$inner" 2>/dev/null; then
          HOOKS_DETAIL_LINES+=("[FAIL] bash -c '${inner}' — 構文エラー")
          HOOKS_FAIL_COUNT=$((HOOKS_FAIL_COUNT + 1))
        fi
      else
        HOOKS_DETAIL_LINES+=("[WARNING] ${cmd} — 未知の形式のため手動確認推奨")
        HOOKS_WARN_COUNT=$((HOOKS_WARN_COUNT + 1))
      fi
    done <<< "$COMMANDS"
  fi

  if [[ "$HOOKS_FAIL_COUNT" -gt 0 ]]; then
    HOOKS_RESULT="FAIL (${HOOKS_FAIL_COUNT}件)"
  elif [[ "$HOOKS_WARN_COUNT" -gt 0 ]]; then
    HOOKS_RESULT="WARNING (${HOOKS_WARN_COUNT}件)"
  fi

  if [[ ${#HOOKS_DETAIL_LINES[@]} -eq 0 ]]; then
    HOOKS_DETAIL_LINES+=("該当なし")
  fi
fi

# ========================================================================
# レポート生成
# ========================================================================

REPORT_DATE=$(date "+%Y-%m-%d %H:%M")
SHORT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

OVERALL="PASS"
if [[ "$PERM_RESULT" == "FAIL" || "$SYMLINK_RESULT" == FAIL* || "$HOOKS_RESULT" == FAIL* ]]; then
  OVERALL="FAIL"
fi

REPORT=$(
  echo "# audit-scan レポート — ${REPORT_DATE}"
  echo ""
  echo "対象スプリント: ${SPRINT:-（不明）}"
  echo "対象コミット: ${SHORT_SHA}"
  echo ""
  echo "## サマリー"
  echo ""
  echo "| チェック項目 | 結果 |"
  echo "|------------|------|"
  echo "| permissions.allow 整合性 | ${PERM_RESULT} |"
  echo "| symlink 健全性 | ${SYMLINK_RESULT} |"
  echo "| hooks 構文・生存確認 | ${HOOKS_RESULT} |"
  echo ""
  echo "## 詳細"
  echo ""
  echo "### permissions.allow"
  for line in "${PERM_DETAIL_LINES[@]}"; do
    echo "- ${line}"
  done
  echo ""
  echo "### symlink"
  for line in "${SYMLINK_DETAIL_LINES[@]}"; do
    echo "- ${line}"
  done
  echo ""
  echo "### hooks"
  for line in "${HOOKS_DETAIL_LINES[@]}"; do
    echo "- ${line}"
  done
  echo ""
  echo "## 総合判定"
  echo "${OVERALL}"
)

if [[ -n "$OUT_PATH" ]]; then
  mkdir -p "$(dirname "$OUT_PATH")" 2>/dev/null || true
  printf '%s\n' "$REPORT" > "$OUT_PATH"
fi

printf '%s\n' "$REPORT"

if [[ "$OVERALL" == "FAIL" ]]; then
  exit 1
fi
exit 0
