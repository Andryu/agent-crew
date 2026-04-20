#!/bin/bash
# claude-crew install script
# 使い方: bash install.sh [OPTIONS] [STACK] [TARGET_DIR]
# 例:     bash install.sh --dry-run go /path/to/myproject

set -euo pipefail

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EXIT_OK=0
EXIT_ARG_ERROR=1
EXIT_SRC_MISSING=2
EXIT_PERM_ERROR=3
EXIT_ABORTED=4

# ---------------------------------------------------------------------------
# デフォルト値
# ---------------------------------------------------------------------------
OPT_DRY_RUN=0
OPT_ONLY=""
OPT_NO_GLOBAL=0
OPT_FORCE=0
OPT_UNINSTALL=0
STACK="go"
TARGET_DIR="."

# ---------------------------------------------------------------------------
# ヘルプ
# ---------------------------------------------------------------------------
usage() {
  cat <<'EOF'
使い方: bash install.sh [OPTIONS] [STACK] [TARGET_DIR]

OPTIONS:
  --dry-run           変更内容をプレビュー表示（実際のファイル操作なし）
  --only=<component>  選択的インストール（カンマ区切り）
                        agents       グローバルエージェント + Riku
                        global-agents グローバルエージェントのみ
                        riku         Riku のみ
                        hooks        subagent_stop.sh
                        config       _queue.json + settings.json
  --no-global         グローバルエージェントのインストールをスキップ
  --force             競合プロンプトをスキップして全て上書き
  --uninstall         インストール済みファイルを削除
  --help              このヘルプを表示

引数:
  STACK      スタック識別子（go / vue / next）。デフォルト: go
  TARGET_DIR インストール先プロジェクトのパス。デフォルト: .

終了コード:
  0  成功
  1  引数・オプションエラー
  2  ソースファイル不在
  3  書き込み権限なし
  4  オーナーが中断
EOF
}

# ---------------------------------------------------------------------------
# 引数パース
# ---------------------------------------------------------------------------
POSITIONAL_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      OPT_DRY_RUN=1
      ;;
    --only=*)
      OPT_ONLY="${arg#--only=}"
      ;;
    --no-global)
      OPT_NO_GLOBAL=1
      ;;
    --force)
      OPT_FORCE=1
      ;;
    --uninstall)
      OPT_UNINSTALL=1
      ;;
    --help|-h)
      usage
      exit $EXIT_OK
      ;;
    --*)
      echo "エラー: 不明なオプション: $arg" >&2
      echo "ヘルプ: bash install.sh --help" >&2
      exit $EXIT_ARG_ERROR
      ;;
    *)
      POSITIONAL_ARGS+=("$arg")
      ;;
  esac
done

# 位置引数を適用
if [ ${#POSITIONAL_ARGS[@]} -ge 1 ]; then
  STACK="${POSITIONAL_ARGS[0]}"
fi
if [ ${#POSITIONAL_ARGS[@]} -ge 2 ]; then
  TARGET_DIR="${POSITIONAL_ARGS[1]}"
fi

# TARGET_DIR を絶対パスに正規化
_RAW_TARGET="$TARGET_DIR"
TARGET_DIR="$(cd "$TARGET_DIR" 2>/dev/null && pwd)" || {
  echo "エラー: TARGET_DIR が存在しません: $_RAW_TARGET" >&2
  exit $EXIT_ARG_ERROR
}

# ---------------------------------------------------------------------------
# コンポーネント選択ヘルパー
# ---------------------------------------------------------------------------
# --only が未指定なら全コンポーネントを有効にする
# bash 3.2 互換のため連想配列不使用
COMP_GLOBAL_AGENTS=1
COMP_RIKU=1
COMP_HOOKS=1
COMP_CONFIG=1

if [ -n "$OPT_ONLY" ]; then
  COMP_GLOBAL_AGENTS=0
  COMP_RIKU=0
  COMP_HOOKS=0
  COMP_CONFIG=0

  # カンマ区切りを分割（bash 3.2 互換）
  IFS=',' read -r -a ONLY_LIST <<< "$OPT_ONLY"
  for comp in "${ONLY_LIST[@]}"; do
    case "$comp" in
      agents)
        COMP_GLOBAL_AGENTS=1
        COMP_RIKU=1
        ;;
      global-agents)
        COMP_GLOBAL_AGENTS=1
        ;;
      riku)
        COMP_RIKU=1
        ;;
      hooks)
        COMP_HOOKS=1
        ;;
      config)
        COMP_CONFIG=1
        ;;
      *)
        echo "エラー: 不明なコンポーネント: $comp" >&2
        echo "有効な値: agents, global-agents, riku, hooks, config" >&2
        exit $EXIT_ARG_ERROR
        ;;
    esac
  done
fi

# --no-global はグローバルエージェントを無効化
if [ $OPT_NO_GLOBAL -eq 1 ]; then
  COMP_GLOBAL_AGENTS=0
fi

# ---------------------------------------------------------------------------
# アンインストールモード
# ---------------------------------------------------------------------------
if [ $OPT_UNINSTALL -eq 1 ]; then
  echo "=== claude-crew アンインストール ==="
  echo "対象: $TARGET_DIR"
  echo ""

  RIKU_FILE="$TARGET_DIR/.claude/agents/riku.md"
  HOOK_FILE="$TARGET_DIR/.claude/hooks/subagent_stop.sh"

  for f in "$RIKU_FILE" "$HOOK_FILE"; do
    if [ -f "$f" ]; then
      if [ $OPT_DRY_RUN -eq 1 ]; then
        echo "  [DRY-RUN] 削除予定: $f"
      else
        rm -f "$f"
        echo "  [REMOVED] $f"
      fi
    else
      echo "  [SKIP]    $f (存在しない)"
    fi
  done

  echo ""
  echo "アンインストール完了。"
  echo "注意: _queue.json / settings.json / グローバルエージェントは保護されています。"
  exit $EXIT_OK
fi

# ---------------------------------------------------------------------------
# ユーティリティ関数
# ---------------------------------------------------------------------------

# ソースファイルの存在チェック
check_src() {
  local src="$1"
  if [ ! -f "$src" ]; then
    echo "エラー: ソースファイルが見つかりません: $src" >&2
    exit $EXIT_SRC_MISSING
  fi
}

# ディレクトリの書き込み権限チェック（作成も含む）
ensure_dir() {
  local dir="$1"
  if [ $OPT_DRY_RUN -eq 1 ]; then
    return 0
  fi
  mkdir -p "$dir" || {
    echo "エラー: ディレクトリを作成できません: $dir" >&2
    exit $EXIT_PERM_ERROR
  }
}

# ---------------------------------------------------------------------------
# コピーロジック
# ---------------------------------------------------------------------------
# 競合が発生した際のグローバル応答（'a' で全て上書き）
GLOBAL_ANSWER=""

# ファイルを1件コピーする
# 引数: <src> <dst> <policy: conflict|overwrite|skip>
copy_file() {
  local src="$1"
  local dst="$2"
  local policy="$3"

  check_src "$src"

  # ファイルが存在しない → 新規コピー
  if [ ! -f "$dst" ]; then
    if [ $OPT_DRY_RUN -eq 1 ]; then
      printf "  [NEW]       %s\n" "$dst"
    else
      ensure_dir "$(dirname "$dst")"
      cp "$src" "$dst"
      printf "  [NEW]       %s\n" "$dst"
    fi
    return 0
  fi

  # policy: skip
  if [ "$policy" = "skip" ]; then
    printf "  [SKIP]      %s  <- 既存ファイルを保護\n" "$dst"
    return 0
  fi

  # policy: overwrite
  if [ "$policy" = "overwrite" ]; then
    if [ $OPT_DRY_RUN -eq 1 ]; then
      printf "  [OVERWRITE] %s\n" "$dst"
    else
      ensure_dir "$(dirname "$dst")"
      cp "$src" "$dst"
      printf "  [OVERWRITE] %s\n" "$dst"
    fi
    return 0
  fi

  # policy: conflict
  # --force の場合はプロンプトなしで上書き
  if [ $OPT_FORCE -eq 1 ]; then
    if [ $OPT_DRY_RUN -eq 1 ]; then
      printf "  [OVERWRITE] %s  <- --force により上書き\n" "$dst"
    else
      ensure_dir "$(dirname "$dst")"
      cp "$src" "$dst"
      printf "  [OVERWRITE] %s\n" "$dst"
    fi
    return 0
  fi

  # dry-run の場合は CONFLICT 表示だけ
  if [ $OPT_DRY_RUN -eq 1 ]; then
    printf "  [CONFLICT]  %s  <- 既に存在\n" "$dst"
    return 0
  fi

  # グローバル応答が 'a'（全て上書き）の場合
  if [ "$GLOBAL_ANSWER" = "a" ]; then
    ensure_dir "$(dirname "$dst")"
    cp "$src" "$dst"
    printf "  [OVERWRITE] %s\n" "$dst"
    return 0
  fi

  # diff 表示 + プロンプト
  echo ""
  echo "  [CONFLICT] $dst"
  echo "  --- 差分 (既存 vs 新規) ---"
  diff "$dst" "$src" || true
  echo "  ---------------------------"
  printf "  上書きしますか? [y/N/a/q] (y=はい, N=スキップ, a=以降すべて上書き, q=中断): "

  local answer
  read -r answer </dev/tty || answer="N"

  case "$answer" in
    y|Y)
      ensure_dir "$(dirname "$dst")"
      cp "$src" "$dst"
      printf "  [OVERWRITE] %s\n" "$dst"
      ;;
    a|A)
      GLOBAL_ANSWER="a"
      ensure_dir "$(dirname "$dst")"
      cp "$src" "$dst"
      printf "  [OVERWRITE] %s\n" "$dst"
      ;;
    q|Q)
      echo "中断しました。" >&2
      exit $EXIT_ABORTED
      ;;
    *)
      printf "  [SKIP]      %s\n" "$dst"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------
echo "=== claude-crew インストール (stack: $STACK) ==="
echo "インストール先: $TARGET_DIR"
if [ $OPT_DRY_RUN -eq 1 ]; then
  echo "[DRY-RUN] 以下は実際には実行されません"
fi
echo ""

# --- グローバルエージェント ---
if [ $COMP_GLOBAL_AGENTS -eq 1 ]; then
  echo "--- グローバルエージェント (~/.claude/agents/) ---"
  GLOBAL_AGENTS_DIR="$HOME/.claude/agents"
  ensure_dir "$GLOBAL_AGENTS_DIR"

  for agent_file in pm.md architect.md ux-designer.md qa.md doc-reviewer.md \
                    security.md devops.md data-analyst.md; do
    copy_file \
      "$REPO_DIR/agents/$agent_file" \
      "$GLOBAL_AGENTS_DIR/$agent_file" \
      "conflict"
  done
  echo ""
fi

# --- Riku ---
if [ $COMP_RIKU -eq 1 ]; then
  echo "--- Riku ($STACK) ($TARGET_DIR/.claude/agents/) ---"

  # riku-<STACK>.md を優先し、なければ engineer-<STACK>.md、さらに engineer-go.md へフォールバック
  RIKU_SRC=""
  for candidate in \
    "$REPO_DIR/agents/riku-${STACK}.md" \
    "$REPO_DIR/agents/engineer-${STACK}.md" \
    "$REPO_DIR/agents/engineer-go.md"; do
    if [ -f "$candidate" ]; then
      RIKU_SRC="$candidate"
      break
    fi
  done

  if [ -z "$RIKU_SRC" ]; then
    echo "エラー: Riku のソースファイルが見つかりません (stack: $STACK)" >&2
    exit $EXIT_SRC_MISSING
  fi

  if [ "$RIKU_SRC" != "$REPO_DIR/agents/riku-${STACK}.md" ] && \
     [ "$RIKU_SRC" != "$REPO_DIR/agents/engineer-${STACK}.md" ]; then
    echo "  注意: riku-${STACK}.md が見つからないため engineer-go.md を使用します"
  fi

  copy_file \
    "$RIKU_SRC" \
    "$TARGET_DIR/.claude/agents/riku.md" \
    "conflict"
  echo ""
fi

# --- hooks ---
if [ $COMP_HOOKS -eq 1 ]; then
  echo "--- hooks ($TARGET_DIR/.claude/hooks/) ---"

  HOOK_DST="$TARGET_DIR/.claude/hooks/subagent_stop.sh"
  copy_file \
    "$REPO_DIR/hooks/subagent_stop.sh" \
    "$HOOK_DST" \
    "overwrite"

  # dry-run 以外では実行権限を付与
  if [ $OPT_DRY_RUN -eq 0 ] && [ -f "$HOOK_DST" ]; then
    chmod +x "$HOOK_DST"
  fi
  echo ""
fi

# --- config ---
if [ $COMP_CONFIG -eq 1 ]; then
  echo "--- 設定ファイル ($TARGET_DIR/.claude/) ---"
  ensure_dir "$TARGET_DIR/.claude"

  copy_file \
    "$REPO_DIR/templates/_queue.json" \
    "$TARGET_DIR/.claude/_queue.json" \
    "skip"

  copy_file \
    "$REPO_DIR/templates/settings.json" \
    "$TARGET_DIR/.claude/settings.json" \
    "skip"
  echo ""
fi

# ---------------------------------------------------------------------------
# 完了メッセージ
# ---------------------------------------------------------------------------
if [ $OPT_DRY_RUN -eq 1 ]; then
  echo "=== [DRY-RUN] プレビュー完了 (実際のファイル変更なし) ==="
else
  echo "=== インストール完了 ==="
  echo ""
  echo "次のステップ:"
  echo "  1. Slack通知を使う場合: export SLACK_WEBHOOK_URL='https://hooks.slack.com/...'"
  echo "  2. Claude Code を起動して試す:"
  echo "     > Use the yuki agent to plan [作りたい機能名]"
fi
