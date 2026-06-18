# Slack エージェント人格別口調テンプレート設計

**Issue**: #30「エージェント人格 Slack 口調」  
**Sprint**: Sprint-23  
**担当**: Alex (Architect)  
**対象フェーズ**: 設計 (1/2) — 実装は Issue #30 の Riku フェーズが担う

---

## 1. 設計の目的と背景

### 問題

現在の Slack 通知は `subagent_stop.sh` から送信されるが、以下の課題がある。

1. **差し戻しパターンが未実装** — 完了・ブロックの2パターンしか存在せず、QA の CHANGES_REQUESTED 通知に人格が乗っていない
2. **メッセージのエージェント感が弱い** — `build_done_message` / `build_block_message` は定義されているが、呼び出しコンテキストがずれている箇所がある（READY_FOR_* 検出時に直前 done イベントの agent を参照する遅延取得）
3. **テンプレートがコードに埋め込まれている** — 口調の変更にスクリプト改修が必要で、設計意図が文書化されていない

### 設計方針

- テンプレートの仕様をこのドキュメントに集約する（実装はスクリプト側）
- 6エージェント × 3パターンを網羅する
- 変数定義を明確にし、Riku が迷わず実装できる状態にする
- bash 3.2 互換（`declare -A` 禁止、`case` 文使用）を維持する

---

## 2. エージェントプロファイル

| エージェント | ロール | Slack 表示名 | アイコン (Unicode) | 口調の特徴 |
|------------|------|------------|-----------------|---------|
| Yuki | PM | Yuki (PM) | 📋 | 丁寧語・ですます調・チームへの橋渡し感 |
| Alex | 設計 | Alex (Architect) | 🏗️ | 論理的・構造を示す・引き継ぎ先を明記 |
| Mina | UX | Mina (UX) | 🎨 | 柔らかい口調・感謝を添える・前向き |
| Riku | 実装 | Riku (Dev) | 🔨 | カジュアル・端的・体言止め多め |
| Sora | QA | Sora (QA) | 🔍 | 客観的・証拠ベース・判定を明示 |
| Hana | レビュー | Hana (Review) | 📝 | 丁寧・根拠を添える・建設的 |

### 絵文字使用方針

- アイコン絵文字は Slack Webhook のメッセージ本文に埋め込む（`icon_emoji` フィールド override は Slack App 型 Webhook で無効なため）
- メッセージ先頭のステータス絵文字は全エージェント共通（パターンによって固定）

| ステータス絵文字 | 意味 |
|--------------|-----|
| ✅ | 完了 (done) |
| 🚧 | ブロック (blocked) |
| 🔄 | 差し戻し (changes_requested) |

---

## 3. メッセージテンプレート定義

### 変数定義

| 変数名 | 説明 | 例 |
|-------|------|---|
| `{SLUG}` | タスクの slug | `slack-persona-design` |
| `{NEXT_AGENT}` | 次の担当エージェント表示名 | `Riku` |
| `{REASON}` | ブロック理由または差し戻し理由 | `APIキーが未設定` |
| `{SPRINT}` | スプリント識別子 | `Sprint-23` |
| `{RETRY_COUNT}` | 差し戻し回数 | `1` |

### 3-1. 完了パターン (done)

| エージェント | メッセージテンプレート |
|------------|-------------------|
| Yuki | `✅ {SLUG} のタスク分解が完了しました。チームに引き渡します。` |
| Alex | `✅ {SLUG} の設計が完了しました。ADR と設計ドキュメントを {NEXT_AGENT} に引き継ぎます。` |
| Mina | `✅ {SLUG} のデザイン、できました！{NEXT_AGENT} に渡しますね。` |
| Riku | `✅ {SLUG} 実装完了！{NEXT_AGENT}、レビューよろしく。` |
| Sora | `✅ {SLUG} レビュー完了。品質基準を満たしています — APPROVED` |
| Hana | `✅ {SLUG} のレビューが完了しました。問題ありません。` |
| (デフォルト) | `✅ {AGENT}: {SLUG} が完了しました / 次: {NEXT_AGENT}` |

### 3-2. ブロックパターン (blocked)

| エージェント | メッセージテンプレート |
|------------|-------------------|
| Yuki | `🚧 {SLUG} がブロックされています。オーナーの判断が必要です — {REASON}` |
| Alex | `🚧 {SLUG} の設計がブロックされました。前提となる決定が必要です — {REASON}` |
| Mina | `🚧 {SLUG} のデザインで手が止まっています。確認が必要です — {REASON}` |
| Riku | `🚧 {SLUG} ブロックされた。詰まってる — {REASON}` |
| Sora | `🚧 {SLUG} のQAがブロックされました。テスト実行に必要な情報が不足しています — {REASON}` |
| Hana | `🚧 {SLUG} のレビューがブロックされました — {REASON}` |
| (デフォルト) | `🚧 {AGENT}: {SLUG} がブロックされました — {REASON}` |

### 3-3. 差し戻しパターン (changes_requested)

差し戻しは Sora が `qa CHANGES_REQUESTED` を発行した際に送信する。  
`retry_count > 0` かつ `status == "READY_FOR_RIKU"` で検出する（queue.sh 変更不要）。

| エージェント | メッセージテンプレート |
|------------|-------------------|
| Yuki | `🔄 {SPRINT} はまだ完了していません。未承認のタスクが残っています。` |
| Alex | `🔄 {SLUG} の設計を見直します。指摘事項を確認してください。` |
| Mina | `🔄 {SLUG} のデザイン、修正します。フィードバックありがとうございます。` |
| Riku | `🔄 {SLUG} 修正する。指摘箇所確認した。` |
| Sora | `🔄 {SLUG} 差し戻し。修正が必要な箇所を記録しました — CHANGES_REQUESTED` |
| Hana | `🔄 {SLUG} に修正依頼を出しました。詳細はコメントを参照してください。` |
| (デフォルト) | `🔄 {AGENT}: {SLUG} を差し戻しました (retry {RETRY_COUNT})` |

---

## 4. 実装仕様

### 4-1. bash 関数シグネチャ

```bash
# build_done_message <agent> <slug> <next_agent>
# 戻り値: 完了メッセージ文字列 (stdout)
build_done_message() { ... }

# build_block_message <agent> <slug> <reason>
# 戻り値: ブロックメッセージ文字列 (stdout)
build_block_message() { ... }

# build_retry_message <agent> <slug> <retry_count>
# 戻り値: 差し戻しメッセージ文字列 (stdout)
# Sprint-23 で新規追加
build_retry_message() { ... }
```

### 4-2. 差し戻し検出ロジック

`subagent_stop.sh` の Section 2（READY_FOR_* 提示）内で、以下の条件で差し戻し通知を分岐する。

```bash
# 擬似コード
RETRY_COUNT=$(jq -r --arg s "$SLUG" '.tasks[] | select(.slug == $s) | .retry_count // 0' "$QUEUE_FILE")
if [[ "$RETRY_COUNT" -gt 0 ]]; then
  # 差し戻し通知: QA エージェント(Sora)が主語
  MESSAGE=$(build_retry_message "Sora" "$SLUG" "$RETRY_COUNT")
  slack_notify "Sora" "$MESSAGE"
fi
```

### 4-3. Slack ペイロード構造

```json
{
  "text": "{ICON} *{DISPLAY_NAME}*: {MESSAGE}",
  "username": "{DISPLAY_NAME}",
  "icon_emoji": "{ICON_EMOJI_CODE}"
}
```

- `text` にアイコンと表示名を埋め込む（Slack App 型 Webhook で username/icon_emoji override が効かない場合のフォールバック）
- `jq -n --arg` でペイロードを構築し、JSON インジェクションを防ぐ

### 4-4. メッセージ長の指針

| パターン | 上限目安 | 理由 |
|---------|---------|------|
| 完了 | 80文字以内 | Slack 通知プレビュー（1行）に収める |
| ブロック | 120文字以内 | 理由文を含むが、詳細は Issue/ログで確認 |
| 差し戻し | 100文字以内 | 完了とブロックの中間 |

---

## 5. スコープ外（実装フェーズへの引き継ぎ）

以下は Riku の実装タスク（Issue #30 2/2）で対応する。

- `hooks/subagent_stop.sh` への `build_retry_message` 関数追加
- 差し戻し検出ロジックの実装
- `.github/workflows/slack-notify.yml` への `username`/`icon_emoji` フィールド追加（Webhook 設定確認後）
- 既存の差し戻しなし状態でのリグレッションテスト

---

## 6. 変更対象ファイル一覧

| ファイル | 変更種別 | 担当フェーズ |
|---------|---------|-----------|
| `hooks/subagent_stop.sh` | 修正（`build_retry_message` 追加、差し戻し検出ロジック追加） | Riku (実装) |
| `.github/workflows/slack-notify.yml` | 修正（ペイロードに `username`/`icon_emoji` 追加） | Riku (実装) |
| `docs/spec/slack-persona.md` | 新規作成 | Alex (設計) ← 本ファイル |

---

## 7. 受け入れ基準（Issue #30 より抜粋）

- [ ] 6エージェント × 3メッセージパターン以上がそれぞれ異なる口調で送信される
- [ ] テンプレートの追加・変更がスクリプト本体の変更なしに行える（将来の拡張性）
- [ ] 既存の通知フロー（完了・ブロック）が引き続き正常に動作する
- [ ] Issue #29（アイコン個別化）と組み合わせて動作検証済み

---

## 8. 設計上のトレードオフ

| 選択 | 得たもの | 失ったもの |
|------|---------|-----------|
| テンプレートをコード内 `case` 文で管理 | 依存ファイルなし・bash 3.2 互換 | テンプレートの変更にスクリプル改修が必要 |
| 差し戻し主語を Sora 固定 | 実装がシンプル | 実際の差し戻しエージェントが Hana 等の場合に不正確 |
| Block Kit を使わない | curl ペイロードが単純・メンテしやすい | ボタン・インタラクションは使えない |
| メッセージ長の上限を指針のみ（強制なし） | 実装シンプル | 長いブロック理由がそのまま流れる可能性がある |
