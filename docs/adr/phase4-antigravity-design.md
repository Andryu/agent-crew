# Phase 4 — Antigravity パイプラインパリティ 設計メモ

対象 Issue: #19（Antigravity パイプラインパリティ）

作成日: 2026-04-19

---

## 1. 問題の整理

### 1.1 現状の Antigravity サポートと Claude Code の差分

README の「ツール対応状況」表が出発点。

| 機能 | Claude Code | Antigravity（現状） |
|------|:-----------:|:-------------------:|
| エージェント本体 | 有 | 有 |
| グローバル配置 | 有 | 有（`~/.gemini/antigravity/skills/`） |
| プロジェクト配置 | 有 | 有（`.agent/skills/riku/`） |
| 自動パイプライン（hook） | 有 | 無 |
| Slack 通知 | 有 | 無 |
| タスクキュー管理 | 有 | 手動のみ |

仕様書（`docs/spec/agent-crew-spec.md` §12）にも同様の記述がある。

> Antigravity サポート — エージェント定義のみ、hook 未対応のため自動化は不可

つまり「パイプラインパリティ」とは、**Claude Code で動く自動パイプライン体験を Antigravity 上でも再現すること**を指す。

### 1.2 Antigravity と Claude Code の技術的差異

Antigravity（Google Gemini のエージェントスキルシステム）は Claude Code の SubagentStop フックに相当するライフサイクルフックを持たない（2026-04 時点）。この制約がパリティを妨げる根本原因。

制約を整理すると以下になる。

- **SubagentStop hook 不在** — エージェント完了時に自動でシェルスクリプトを実行する仕組みがない。
- **キューファイルのパス差異** — Claude Code は `.claude/_queue.json`、Antigravity インストール版は `.agent/_queue.json` を参照している（`install-antigravity.sh` より）。
- **Slack 通知未接続** — `subagent_stop.sh` 内にある Webhook 呼び出しが Antigravity では一切実行されない。
- **queue.sh の扱い** — スクリプト本体は `scripts/queue.sh` にあるが、Antigravity エージェントがシェルを叩けるかはスキル設定次第（SKILL.md の `tools` フィールドで Bash が許可されているか）。

---

## 2. ゴールとスコープ

### 2.1 何を達成したいか

「パイプラインパリティ」を最小限に定義し直す。

1. **エージェントがキューを読み書きできる** — `queue.sh start / done / handoff` が Antigravity 上でも同様に機能する。
2. **次の担当が自動提示される** — SubagentStop hook の代替として、各エージェントの完了時に STDOUT へ「次のコマンド」を出力する。
3. **Slack 通知が届く** — エージェント完了・BLOCKED・スプリント完了の3タイミングで通知する。

### 2.2 スコープ外（今回は対象外）

- Antigravity の SubagentStop フック相当機能が将来追加された場合の対応（拡張余地を残すのみ）。
- queue.sh の冪等性・ロック機構の再実装（Antigravity のファイル操作モデルが不明なため）。
- 複数プロジェクト同時管理（現状のスコープ外、変更なし）。

---

## 3. アーキテクチャ方針

### 3.1 2つのアプローチの比較

**オプション A — エージェント内 STDOUT 提示（軽量）**

各エージェントの完了報告フォーマット末尾に「次のコマンド」を STDOUT 出力させる。SubagentStop hook の代わりに、エージェント自身が次手を提示する。

- メリット: hook 機構に依存しない。SKILL.md を書き換えるだけで実現できる。
- デメリット: オーナーが手動でコピペして次エージェントを呼ぶ必要がある（Claude Code の confirm モードと同等）。auto モードは再現できない。

**オプション B — `queue.sh` を Antigravity スキルから叩く（完全パリティ）**

Antigravity のスキルに `tools: Bash` を付与して `queue.sh` を直接実行できるようにする。完了時に `queue.sh done` と Slack 通知スクリプトを呼ぶことで hook と同等の動作を実現する。

- メリット: Slack 通知・キュー更新・次手提示のすべてが自動化できる。
- デメリット: Antigravity が Bash ツールを許可しているかが未確認。設定次第で動かない可能性がある。

**採用: オプション A を基本とし、オプション B の準備を整える**

Antigravity の Bash ツール許可状況が確認できていないため、確実に動く最小手（オプション A）を採用する。同時に、オプション B への移行が容易になるよう `queue.sh` の QUEUE_FILE パスを環境変数で制御できる状態を維持する。

### 3.2 全体構成

```
Antigravity セッション（オーナーとの対話）
  @yuki / @alex / @mina / @riku / @sora

  エージェントごとの SKILL.md
  ├── 完了時に STDOUT へ次コマンドを出力（オプションA）
  ├── tools: Bash が許可されていれば queue.sh を呼ぶ（オプションB）
  └── Slack 通知は curl で直接呼ぶ（Bash 許可時のみ）

  .agent/
  ├── _queue.json    タスクキュー（QUEUE_FILE=.agent/_queue.json）
  └── skills/
      ├── yuki/SKILL.md
      ├── alex/SKILL.md
      ├── mina/SKILL.md
      ├── riku/SKILL.md
      └── sora/SKILL.md
```

---

## 4. 変更対象ファイルと変更内容

### 4.1 `install-antigravity.sh` の拡張

現状の install-antigravity.sh は以下を行っている。

- `agents/*.md` を `~/.gemini/antigravity/skills/<role>/SKILL.md` へコピー
- `templates/_queue.json` を `.agent/_queue.json` へコピー
- `queue.sh` はコピーしていない

変更点：

1. `scripts/queue.sh` を `.agent/scripts/queue.sh` へコピーし、実行権限を付与する。
2. Antigravity 向け `QUEUE_FILE` のデフォルト値が `.agent/_queue.json` になるよう、スクリプトのコピー時に先頭行のデフォルト値を書き換える（または `QUEUE_FILE` 環境変数を `.agent/` 配下を指すよう `.agent/.env` に書き出す）。
3. スクリプトとともに `scripts/notify_slack.sh` もコピーし、Slack 通知を手動で実行できるよう準備する。

```bash
# install-antigravity.sh への追記イメージ
echo "スクリプトを配置中..."
mkdir -p .agent/scripts
cp "$REPO_DIR/scripts/queue.sh" .agent/scripts/queue.sh
chmod +x .agent/scripts/queue.sh
# QUEUE_FILE のデフォルトを .agent/_queue.json に書き換え
sed -i.bak 's|QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"|QUEUE_FILE="${QUEUE_FILE:-.agent/_queue.json}"|' \
  .agent/scripts/queue.sh && rm -f .agent/scripts/queue.sh.bak
echo "  → queue.sh → .agent/scripts/queue.sh"
```

### 4.2 Antigravity 向けエージェント SKILL.md の overlay 追加

現状の `overlays/` 構造はすべて Claude Code を対象にしている。Antigravity 向けの overlay を追加する。

```
overlays/
├── _queue_protocol.md               # Claude Code 向け（既存）
├── _queue_protocol_antigravity.md   # Antigravity 向け（新規）
└── _slack_notify_antigravity.md     # Slack 通知セクション（新規）
```

**`_queue_protocol_antigravity.md` の要点（Claude Code 版との差分）**

- `scripts/queue.sh` のパスを `.agent/scripts/queue.sh` に変更。
- SubagentStop hook が存在しないため、完了報告フォーマット末尾に以下を出力させる。

```
--- NEXT STEP ---
次のコマンド: @<next-agent> [slug] の<フェーズ>をして
理由: [一文で説明]
---
```

**`_slack_notify_antigravity.md` の要点**

Bash が使える場合、curl で Slack Webhook を呼ぶスニペットをエージェント定義に含める。
`SLACK_WEBHOOK_URL` が未設定なら静かにスキップ（Claude Code 版と同じ挙動）。

### 4.3 `build.sh` への Antigravity ビルドターゲット追加

現在の `build.sh` は `.claude/agents/` 向けにしかビルドしない。Antigravity ターゲットを追加する。

```bash
# build.sh 追記イメージ（既存の build_agent / append_queue_protocol_to_native の後に追加）

build_antigravity() {
  local role=$1
  local src_md="$AGENTS_DIR/${role}.md"
  local out_dir="$HOME/.gemini/antigravity/skills/${role}"
  local out_file="$out_dir/SKILL.md"

  if [[ ! -f "$src_md" ]]; then
    echo "  [SKIP] $role: source not found"
    return
  fi

  mkdir -p "$out_dir"

  # Claude Code 向けキュープロトコルを剥がして Antigravity 向けを追記
  awk '/^## タスクキュー更新プロトコル（全エージェント共通）/{exit} {print}' "$src_md" > "$out_file.tmp"
  awk '
    { lines[NR] = $0 }
    END {
      last = NR
      while (last > 0 && (lines[last] == "" || lines[last] == "---")) last--
      for (i = 1; i <= last; i++) print lines[i]
    }
  ' "$out_file.tmp" > "$out_file"
  rm -f "$out_file.tmp"

  # Antigravity 向けプロトコルを追記
  cat "$OVERLAYS_DIR/_queue_protocol_antigravity.md" >> "$out_file"
  cat "$OVERLAYS_DIR/_slack_notify_antigravity.md" >> "$out_file"
  echo "  [OK] $role → $out_file"
}

# --- Antigravity ビルド（--target=antigravity が指定された場合のみ）---
if [[ "${1:-}" == "--target=antigravity" ]]; then
  echo "=== Antigravity ビルド ==="
  for role in pm architect ux-designer engineer-go qa doc-reviewer; do
    build_antigravity "$role"
  done
fi
```

これにより `bash build.sh --target=antigravity` で Antigravity 向けに出力できる。

### 4.4 `agents/pm.md`（Yuki）への Antigravity 運用セクション追記

Yuki が Antigravity 上で動く場合の次手提示フォーマットを追加する。

```markdown
## Antigravity での次ステップ提示フォーマット

Antigravity（SubagentStop hook 未対応）では、タスク完了後に以下を STDOUT へ出力する。

--- NEXT STEP ---
次のコマンド: @<next-agent> "[slug]" の<フェーズ>をして
理由: [一文で説明]
---

hook が無いため、オーナーがこのコマンドをコピーして次エージェントを呼ぶ。
```

### 4.5 `scripts/queue.sh` の軽微な修正

Antigravity では `.agent/_queue.json` を使うため、`QUEUE_FILE` 環境変数によるオーバーライドが確実に動く必要がある。現状のコードはすでに `QUEUE_FILE="${QUEUE_FILE:-.claude/_queue.json}"` で対応しているが、以下を確認・補強する。

- すべてのコマンドが `$QUEUE_FILE` を直接参照していること（ハードコードがないこと）
- `QUEUE_LOCK` も同様に `${QUEUE_LOCK:-.claude/.queue.lock}` でオーバーライド可能なこと

これは現状すでに正しく実装されているため、変更不要の可能性が高い。Riku が実装時に確認する。

---

## 5. ディレクトリ変更まとめ

### 新規作成

```
overlays/
├── _queue_protocol_antigravity.md   # Antigravity 向けキュー操作プロトコル
└── _slack_notify_antigravity.md     # Antigravity 向け Slack 通知ガイド
```

### 変更

| ファイル | 変更種別 | 内容の要点 |
|---------|---------|-----------|
| `install-antigravity.sh` | 追記 | `queue.sh` と notify スクリプトを `.agent/scripts/` へコピー |
| `build.sh` | 追記 | `--target=antigravity` ビルドターゲットを追加 |
| `agents/pm.md` | 追記 | Antigravity での次手提示フォーマットを追加 |
| `README.md` | 更新 | ツール対応状況表のステータス更新、Antigravity セットアップ手順の詳細化 |

---

## 6. トレードオフ分析

### 6.1 SubagentStop hook の代替としての STDOUT 提示

| 観点 | 採用案（STDOUT 提示） | 代替案（外部 hook スクリプト） |
|-----|---------------------|-------------------------------|
| 実装コスト | 低（SKILL.md の追記のみ） | 高（Antigravity の hook 機構が必要） |
| 自動化度 | confirm モード相当（手動コピペ必要） | auto モード相当 |
| 信頼性 | 高（仕組みが単純） | 未検証（Antigravity の hook 仕様次第） |
| 逆戻りコスト | 低（overlay を変えるだけ） | 中 |

**判断**: STDOUT 提示を採用。Antigravity に hook 機構が追加された時点で overlay を差し替える形で拡張する。

### 6.2 `build.sh` への Antigravity ターゲット追加 vs 別スクリプト

| 観点 | `build.sh` に統合 | 別スクリプト `build-antigravity.sh` |
|-----|------------------|------------------------------------|
| 管理の一元化 | 高（1ファイルで完結） | 低（2ファイルを追う） |
| 既存 CI への影響 | あり（引数なし実行で挙動変わらないよう注意が必要） | なし |
| 発見しやすさ | 高（README の build 手順に自然に追記できる） | 低（ファイルを探す必要あり） |

**判断**: `build.sh` に `--target=antigravity` オプションとして統合する。引数なしの既存動作は一切変えない（後方互換を保つ）。

### 6.3 `queue.sh` のコピー先を `.agent/scripts/` にする理由

- `.agent/` 配下はプロジェクト固有のファイル置き場として `install-antigravity.sh` が確立している。
- `scripts/queue.sh` をそのままコピーし `QUEUE_FILE` を sed で書き換えることで、本体の `scripts/queue.sh` を変更せずに並存できる。
- git でコピー先を追跡しない（`.gitignore` の `.agent/` エントリで管理）。

---

## 7. 未決事項

以下は実装開始前にオーナーの判断が必要な点、または実装時に Riku が確認すべき点。

| # | 事項 | 状況 |
|---|------|------|
| 1 | Antigravity スキルで `tools: Bash` が使えるか | 未確認。使えなければ STDOUT 提示のみで Slack 通知は不可 |
| 2 | `.gemini/antigravity/skills/` のパスが公式仕様として固定か | 2026-04 時点のパスを使用。Gemini 側の変更追跡が必要 |
| 3 | Antigravity の SKILL.md の frontmatter 仕様（`tools` フィールドの有効な値） | agent-crew の SKILL.md は Claude Code の frontmatter 形式を流用しているが Antigravity で正しく認識されるか未検証 |
| 4 | `queue.sh` を sed で書き換えるアプローチの代替案 | `.env` ファイルを `.agent/` に置いてエージェントが `source .env` する方式も検討できる。ただしエージェントが `source` できるかは Bash 許可に依存 |

---

## 8. 実装順序（Riku への引き継ぎ）

1. `overlays/_queue_protocol_antigravity.md` を作成する。Claude Code 版との差分はパスと完了報告フォーマットのみ。
2. `overlays/_slack_notify_antigravity.md` を作成する。`SLACK_WEBHOOK_URL` 未設定時にスキップするロジックを含める。
3. `build.sh` に `--target=antigravity` オプションを追加する。既存の `build_agent` / `append_queue_protocol_to_native` 関数を参考に実装する。
4. `install-antigravity.sh` に `queue.sh` コピーと QUEUE_FILE 書き換えを追加する。
5. `agents/pm.md` に Antigravity 向け次手提示フォーマットを追記する。
6. `README.md` のツール対応状況表とセットアップ手順を更新する。

**注意**: 3 の `build.sh` 変更後は必ず引数なし（既存の Claude Code ビルド）も実行して冪等性が維持されていることを確認すること。

---

## 9. Mina（UX）への引き継ぎ

Antigravity での運用体験は「オーナーが STDOUT の `--- NEXT STEP ---` ブロックを読んでコピペする」という confirm モード相当になる。

この UX は Claude Code の confirm モードと等価だが、コマンド書式が異なる点に注意。

- Claude Code: `Use the alex agent on "slug"`
- Antigravity: `@alex "slug" の設計をして`

オーナーが混乱しないよう、次手提示の文言を Antigravity / Claude Code で明確に分けること。UX 仕様として次手テンプレートの文言を設計してほしい。
