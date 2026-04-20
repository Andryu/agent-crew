# Slack エージェント人格化 設計メモ

GitHub Issue #29（アイコン個別化）#30（口調反映） / branch: `feat/slack-persona`

## 概要

Slack通知にエージェントごとの表示名・アイコン・口調を反映し、「人とやっている感」を出す。

## エージェント Slack 表示プロファイル

| エージェント | Slack 表示名 | icon_emoji | 口調 |
|------------|------------|-----------|------|
| Yuki | Yuki (PM) | :clipboard: | 丁寧語・ですます調 |
| Alex | Alex (Architect) | :building_construction: | 落ち着いた語調・構造と根拠を示す |
| Mina | Mina (UX) | :art: | 柔らかい語調・前向き |
| Riku | Riku (Dev) | :hammer_and_wrench: | カジュアル・端的 |
| Sora | Sora (QA) | :mag: | 客観的・証拠重視 |
| Hana | Hana (Review) | :memo: | 丁寧かつ率直 |

`icon_emoji` 採用理由: 外部ホスティング不要、依存ゼロ。

## メッセージテンプレート（6エージェント × 3パターン）

### Yuki（PM）
| パターン | テンプレート |
|---------|-----------|
| 完了 | `✅ <slug> のタスク分解が完了しました。チームに引き渡します。` |
| ブロック | `🚧 <slug> がブロックされています。オーナーの判断が必要です — <理由>` |
| 差し戻し | `🔄 <sprint> はまだ完了していません。未承認のタスクが残っています。` |

### Alex（アーキテクト）
| パターン | テンプレート |
|---------|-----------|
| 完了 | `✅ <slug> の設計が完了しました。ADRと設計ドキュメントを<next>に引き継ぎます。` |
| ブロック | `🚧 <slug> の設計がブロックされました。前提となる決定が必要です — <理由>` |
| 差し戻し | `🔄 <slug> の設計を見直します。指摘事項を確認してください。` |

### Mina（UX）
| パターン | テンプレート |
|---------|-----------|
| 完了 | `✅ <slug> のデザイン、できました！<next>に渡しますね。` |
| ブロック | `🚧 <slug> のデザインで手が止まっています。確認が必要です — <理由>` |
| 差し戻し | `🔄 <slug> のデザイン、修正します。フィードバックありがとうございます。` |

### Riku（Dev）
| パターン | テンプレート |
|---------|-----------|
| 完了 | `✅ <slug> 実装完了！<next>、レビューよろしく。` |
| ブロック | `🚧 <slug> ブロックされた。詰まってる — <理由>` |
| 差し戻し | `🔄 <slug> 修正する。指摘箇所確認した。` |

### Sora（QA）
| パターン | テンプレート |
|---------|-----------|
| 完了 | `✅ <slug> レビュー完了。品質基準を満たしています — APPROVED` |
| ブロック | `🚧 <slug> のQAがブロックされました。テスト実行に必要な情報が不足しています — <理由>` |
| 差し戻し | `🔄 <slug> 差し戻し。修正が必要な箇所を記録しました — CHANGES_REQUESTED` |

### Hana（Review）
| パターン | テンプレート |
|---------|-----------|
| 完了 | `✅ <slug> のレビューが完了しました。問題ありません。` |
| ブロック | `🚧 <slug> のレビューがブロックされました — <理由>` |
| 差し戻し | `🔄 <slug> に修正依頼を出しました。詳細はコメントを参照してください。` |

## `subagent_stop.sh` 改修方針

### 核心: `slack_notify` 関数への集約

現在 curl 呼び出しが3箇所に重複。関数に集約してエージェントプロファイルを切り替える。

```bash
# bash 3.2 互換（case 文ベース、declare -A は使わない）

get_agent_display_name() {
  case "$1" in
    Yuki) echo "Yuki (PM)" ;;
    Alex) echo "Alex (Architect)" ;;
    Mina) echo "Mina (UX)" ;;
    Riku) echo "Riku (Dev)" ;;
    Sora) echo "Sora (QA)" ;;
    Hana) echo "Hana (Review)" ;;
    *)    echo "agent-crew" ;;
  esac
}

get_agent_icon() {
  case "$1" in
    Yuki) echo ":clipboard:" ;;
    Alex) echo ":building_construction:" ;;
    Mina) echo ":art:" ;;
    Riku) echo ":hammer_and_wrench:" ;;
    Sora) echo ":mag:" ;;
    Hana) echo ":memo:" ;;
    *)    echo ":robot_face:" ;;
  esac
}

slack_notify() {
  local agent="$1" message="$2"
  [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0

  local display_name icon payload
  display_name=$(get_agent_display_name "$agent")
  icon=$(get_agent_icon "$agent")

  payload=$(jq -n \
    --arg text "$message" \
    --arg username "$display_name" \
    --arg icon_emoji "$icon" \
    '{"text": $text, "username": $username, "icon_emoji": $icon_emoji}')

  curl -s --max-time 3 --connect-timeout 2 -X POST "$SLACK_WEBHOOK_URL" \
    -H 'Content-type: application/json' \
    -d "$payload" >/dev/null 2>&1
}
```

### メッセージ生成関数

```bash
build_done_message() {
  local agent="$1" slug="$2" next_agent="$3"
  case "$agent" in
    Yuki)  echo "✅ ${slug} のタスク分解が完了しました。チームに引き渡します。" ;;
    Alex)  echo "✅ ${slug} の設計が完了しました。${next_agent}に引き継ぎます。" ;;
    Mina)  echo "✅ ${slug} のデザイン、できました！${next_agent}に渡しますね。" ;;
    Riku)  echo "✅ ${slug} 実装完了！${next_agent}、レビューよろしく。" ;;
    Sora)  echo "✅ ${slug} レビュー完了。品質基準を満たしています — APPROVED" ;;
    Hana)  echo "✅ ${slug} のレビューが完了しました。問題ありません。" ;;
    *)     echo "✅ ${agent}: ${slug} が完了しました / 次: ${next_agent}" ;;
  esac
}

build_block_message() {
  local agent="$1" slug="$2" reason="$3"
  case "$agent" in
    Yuki)  echo "🚧 ${slug} がブロックされています。オーナーの判断が必要です — ${reason}" ;;
    Alex)  echo "🚧 ${slug} の設計がブロックされました — ${reason}" ;;
    Mina)  echo "🚧 ${slug} のデザインで手が止まっています — ${reason}" ;;
    Riku)  echo "🚧 ${slug} ブロックされた。詰まってる — ${reason}" ;;
    Sora)  echo "🚧 ${slug} のQAがブロックされました — ${reason}" ;;
    Hana)  echo "🚧 ${slug} のレビューがブロックされました — ${reason}" ;;
    *)     echo "🚧 ${agent}: ${slug} がブロックされました — ${reason}" ;;
  esac
}
```

## `slack-notify.yml` 改修方針

ペイロードに `username` と `icon_emoji` を追加するだけ:

- Issue通知 → Yuki (PM) / :clipboard:
- PR通知 → Riku (Dev) / :hammer_and_wrench:

## フォールバック設計

- `*` ケースで未知エージェントを吸収
- `SLACK_WEBHOOK_URL` 未設定時はノーオペレーション
- Slack側で上書きが無効でもテキスト本文は届く
- `jq` 不在時の早期 exit は既存実装で対応済み

## 実装上の注意

- **bash 3.2 互換**: `declare -A` は使わない、`case` 文で実装
- **JSON インジェクション修正**: 既存の `echo "{\"text\": \"$MESSAGE\"}"` を `jq -n --arg` に統一
- **差し戻し通知**: `READY_FOR_RIKU` かつ `retry_count > 0` で検出（queue.sh 変更不要）
- **Slack アプリ設定**: Incoming Webhook で「ユーザー名とアイコンの上書き」が有効か要確認

## 改修対象ファイル

| ファイル | 改修内容 |
|---------|---------|
| `hooks/subagent_stop.sh` | `slack_notify` 関数追加、プロファイル定義、メッセージ生成関数、curl 3箇所を関数に置換、jq構築に統一 |
| `.github/workflows/slack-notify.yml` | ペイロードに `username`・`icon_emoji` 追加（数行の変更） |

新規ファイルの追加は不要。
