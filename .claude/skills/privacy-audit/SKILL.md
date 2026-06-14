---
name: privacy-audit
description: >-
  リポジトリ内の個人情報・機密情報の漏洩リスクを検査するスキル。
  「個人情報チェック」「プライバシー監査」「情報漏洩チェック」
  「公開前に確認して」「個人情報が含まれていないか調べて」
  のような指示で起動。git 追跡ファイル全体をスキャンし、
  🔴 CRITICAL / 🟡 WARNING / 🟢 INFO で分類して報告する。
  公開リポジトリへの push 前・プラグイン配布前に実行推奨。
---

# Privacy Audit Skill

## ワークフロー（5ステップ）

### ステップ 1: git 追跡ファイルの一覧取得

```bash
git ls-files
```

スキャン対象: `git ls-files` で列挙されたすべてのテキストファイル。  
除外: `.git/`、`node_modules/`、バイナリファイル、`*.lock`、`.env`（未追跡であれば問題なし）

### ステップ 2: 差分ファイルへのパターンスキャン（自動チェック分）

```bash
bash scripts/privacy-check.sh
```

自動スキャンが対象とするパターン:
- メールアドレス（`@` を含むもの）
- 絶対パス（`/Users/<username>/` 等のユーザー名を含むもの）
- Slack Webhook URL（`hooks.slack.com/services/`）
- GitHub PAT（`ghp_` プレフィックス）
- OpenAI / Anthropic API キー
- 日本の電話番号パターン

### ステップ 3: .gitignore の漏れチェック

以下のファイルが git 追跡対象になっていないか確認する:

```bash
git ls-files | grep -E '(settings\.local\.json|\.env|credentials|\.secret|_lessons\.json)' || echo "（対象ファイルなし）"
```

危険なファイルが追跡対象の場合は 🔴 CRITICAL として報告する。

### ステップ 4: git 履歴の直近 50 コミットをスキャン

```bash
git log --oneline -50
```

コミットメッセージに実名・メールアドレス・電話番号が含まれていないか目視確認する。

### ステップ 5: 結果を分類して報告

以下の形式でレポートを出力する:

```
## プライバシー監査結果

### 🔴 CRITICAL（即時対応が必要）
- ファイル: 内容（コミット前に削除または .gitignore 追加が必須）

### 🟡 WARNING（公開前に確認推奨）
- ファイル: 内容（意図的な場合は除外設定を見直す）

### 🟢 INFO（懸念なし）
- 検出なし / 検出内容と判断理由

### 総合判定: SAFE / REVIEW_NEEDED / UNSAFE
```

## 補足

- Stop フック（セッション終了時）でも `scripts/privacy-check.sh` が差分ファイルに対して自動実行される
- このスキルは **全追跡ファイル** を対象とした手動・定期的な包括監査用
- 公開リポジトリへの push 前、または `claude plugin install` で配布前に実行することを推奨
