#!/bin/bash
# scripts/privacy-check.sh
# 変更ファイルに個人情報パターンが含まれていないかスキャンする
# Stop フックから自動実行 + /privacy-audit スキルから手動実行

set -euo pipefail

FOUND=0
SUMMARY=false
FINDINGS=0
if [[ "${1:-}" == "--summary" ]]; then
  SUMMARY=true
elif [[ $# -gt 0 ]]; then
  echo 'Usage: privacy-check.sh [--summary]' >&2
  exit 1
fi

# スキャン対象: git で変更されたファイル（未コミット差分 + ステージ済み）
CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null; git diff --name-only --cached 2>/dev/null)
CHANGED_FILES=$(echo "$CHANGED_FILES" | sort -u | grep -v '^\s*$' || true)

if [[ -z "$CHANGED_FILES" ]]; then
  if [[ "$SUMMARY" == true ]]; then echo '{"findings":0}'; fi
  exit 0
fi

# スキャン対象外パターン
EXCLUDE_PATTERNS=(
  "^\.git/"
  "\.lock$"
  "^node_modules/"
  "\.claude/settings\.local\.json$"
  "^\.env"
)

# 個人情報検出パターン
# macOS標準のBash 3でも同じ検査を行う。正規表現の定義はここだけ。
LABELS=('メールアドレス' '絶対パス(ユーザー名)' 'Slack Webhook' 'GitHub PAT' 'OpenAI APIキー' 'Anthropic APIキー' '電話番号(日本)')
PATTERNS=(
  '[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
  '/Users/[a-zA-Z0-9_\-]+/'
  'hooks\.slack\.com/services/'
  'ghp_[A-Za-z0-9]{36}'
  'sk-[A-Za-z0-9]{48}'
  'sk-ant-[A-Za-z0-9\-]+'
  '(0[789]0[-\s]?[0-9]{4}[-\s]?[0-9]{4}|0[0-9]{1,4}[-\s]?[0-9]{1,4}[-\s]?[0-9]{4})'
)

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  [[ ! -f "$file" ]] && continue

  # 除外対象ファイルをスキップ
  SKIP=0
  for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    if echo "$file" | grep -qE "$pattern"; then
      SKIP=1
      break
    fi
  done
  [[ $SKIP -eq 1 ]] && continue

  # バイナリファイルをスキップ
  if file "$file" 2>/dev/null | grep -q "binary"; then
    continue
  fi

  for index in "${!PATTERNS[@]}"; do
    label="${LABELS[$index]}"
    pattern="${PATTERNS[$index]}"
    matches=$(grep -nE "$pattern" "$file" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
      FINDINGS=$((FINDINGS + 1))
      if [[ "$SUMMARY" != true ]]; then
        echo "⚠️  WARNING [$label] $file" >&2
        while IFS= read -r line; do
          echo "   $line" >&2
        done < <(printf '%s\n' "$matches" | sed -n '1,3p')
      fi
      FOUND=1
    fi
  done
done <<< "$CHANGED_FILES"

if [[ "$SUMMARY" == true ]]; then
  printf '{"findings":%s}\n' "$FINDINGS"
elif [[ $FOUND -eq 1 ]]; then
  echo "" >&2
  echo "個人情報の可能性があるパターンが検出されました。コミット前に確認してください。" >&2
  echo "意図的な場合: git commit に --no-verify は使わず、.gitignore または除外パターンを見直してください。" >&2
fi

exit 0
