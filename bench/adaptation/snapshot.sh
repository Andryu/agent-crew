#!/bin/bash
# adaptation/snapshot.sh — ハーネスの「書き換え可能な状態」を Git で追跡する（v4.1 #8）
#
# 使い方:
#   adaptation/snapshot.sh <harness> "<label>"
#   例: adaptation/snapshot.sh hermes "round-3 proposed"
#       adaptation/snapshot.sh pi     "round-3 accepted"
#
# 設計意図:
#   Hermes / Prime / pi は skill・memory・prompt を自分で書き換える。その差分を Git に残し、
#   failure → proposed change → benchmark → accept/reject を追跡できるようにする。
#   reject した変更も revert コミットとして残す（何を試して何がダメだったかが履歴になる）。
#
# 安全設計:
#   ~/.hermes を丸ごと git init すると auth.json や .env まで追跡してしまうため、
#   **許可リストのパスだけ**を別リポジトリへコピーする。コミット前に秘密情報を走査し、
#   見つかったら中断する。
set -uo pipefail
HARNESS="${1:-}"; LABEL="${2:-snapshot}"
STATE_REPO="${HARNESS_STATE_REPO:-$HOME/Workspace/harness-state}"
[[ -n "$HARNESS" ]] || { echo "usage: snapshot.sh <hermes|pi|prime|agent-crew> \"<label>\"" >&2; exit 2; }

# --- 許可リスト（ここに無いものは絶対にコピーしない） ---
declare -a SRCS
case "$HARNESS" in
  hermes)
    SRCS=("$HOME/.hermes/skills" "$HOME/.hermes/memories" "$HOME/.hermes/SOUL.md" "$HOME/.hermes/config.yaml")
    ;;
  pi)
    SRCS=("$HOME/.pi/agent/skills" "$HOME/.pi/agent/extensions" "$HOME/.pi/agent/models.json")
    ;;
  prime)
    SRCS=("$HOME/.prime/agent/skills" "$HOME/.prime/agent/memory" "$HOME/.prime/agent/models.json")
    ;;
  agent-crew)
    # agent-crew は既に Git 管理下なので、SHA を記録するだけ
    R="${AGENT_CREW_REPO:-$HOME/Workspace/agent-crew}"
    mkdir -p "$STATE_REPO/agent-crew"
    { echo "sha: $(git -C "$R" rev-parse HEAD 2>/dev/null)"
      echo "branch: $(git -C "$R" branch --show-current 2>/dev/null)"
      echo "at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
      echo "dirty: $([[ -n "$(git -C "$R" status --porcelain 2>/dev/null)" ]] && echo yes || echo no)"
    } > "$STATE_REPO/agent-crew/HEAD.txt"
    ;;
  *) echo "未対応のハーネス: $HARNESS" >&2; exit 2;;
esac

mkdir -p "$STATE_REPO"
if ! git -C "$STATE_REPO" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$STATE_REPO" init -q
  printf '# 秘密情報は絶対に置かない（snapshot.sh が許可リストでコピーする）\n*.env\nauth.json\n*credential*\n*secret*\n' > "$STATE_REPO/.gitignore"
  git -C "$STATE_REPO" add .gitignore && git -C "$STATE_REPO" commit -qm "init: ハーネス state 追跡用"
  echo "初期化: $STATE_REPO"
fi

# --- コピー（許可リストのみ） ---
if [[ "$HARNESS" != "agent-crew" ]]; then
  DEST="$STATE_REPO/$HARNESS"
  rm -rf "$DEST"; mkdir -p "$DEST"
  for s in "${SRCS[@]}"; do
    [[ -e "$s" ]] || continue
    cp -R "$s" "$DEST/" 2>/dev/null || true
  done
fi

# --- コミット前の秘密情報スキャン（見つかったら中断） ---
# 実在しうる値の「形」だけを検出する。プレースホルダ（xxxx/YOUR_/<...>/example）や
# ドキュメント内の語（"access_token" という単語そのもの）は誤検知になるため除外する。
HITS=$(grep -rlE '(sk-ant-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|xoxb-[0-9]{8,}-[0-9]{8,}-[A-Za-z0-9]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"(access|refresh)_token"[[:space:]]*:[[:space:]]*"[A-Za-z0-9._-]{20,}")' \
  "$STATE_REPO/$HARNESS" 2>/dev/null \
  | while IFS= read -r f; do
      # プレースホルダしか含まないファイルは除外
      grep -qE '(x{8,}|X{8,}|YOUR_|<[A-Za-z_]+>|example|placeholder|dummy)' "$f" 2>/dev/null && continue
      echo "$f"
    done | head -5)
if [[ -n "$HITS" ]]; then
  echo "ABORT: 秘密情報らしき内容を検出したためコミットを中止した:" >&2
  echo "$HITS" | sed 's/^/  /' >&2
  echo "  → 許可リスト（snapshot.sh の SRCS）を見直すこと" >&2
  rm -rf "$STATE_REPO/$HARNESS"
  exit 4
fi

git -C "$STATE_REPO" add -A "$HARNESS" 2>/dev/null
if git -C "$STATE_REPO" diff --cached --quiet 2>/dev/null; then
  echo "変化なし: $HARNESS ($LABEL)"
else
  git -C "$STATE_REPO" commit -qm "$HARNESS: $LABEL"
  echo "記録: $HARNESS ($LABEL) → $(git -C "$STATE_REPO" rev-parse --short HEAD)"
  git -C "$STATE_REPO" show --stat --oneline HEAD | head -8
fi
