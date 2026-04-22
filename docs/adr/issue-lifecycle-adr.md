# ADR: Issue ライフサイクル管理方針

## Status
Accepted

## Context

### 問題の経緯

PR #33 (Sprint-02) がマージされた後、対応済みの Issue（#12〜#15、#17、#18）が open のままになっていた。
一部で open → close → reopen が繰り返された形跡があり、Issue #34 として報告された。

### 調査結果

#### 1. PR body / commit message の `Closes #XX` 構文

PR #33 のコミットメッセージ（`feat: Sprint-02 — エージェント人格化・汎用化・並列実行・新エージェント・Antigravity対応`）には
`Closes #XX` / `Fixes #XX` 構文が含まれていない。

GitHub の自動クローズ機能は PR body または commit message に `Closes #XX` が含まれている場合のみ動作する。
この構文がなければマージ後も Issue は open のままになる。

#### 2. `feat/auto-close-issue` ブランチの存在

Git ログから、`feat/auto-close-issue` というブランチが存在し、コミットメッセージ
「feat: queue.sh done 時に GitHub Issue を自動クローズ」が確認された（コミット `722acd6`）。

このブランチはリモート（origin）にもプッシュされているが、PR #33 のベースとなった
`feat/sprint-02` ブランチには **マージされていない**。

つまり、queue.sh の Issue 自動クローズ実装は「作りかけのまま放置されたブランチ」として存在しており、
本番の queue.sh（`feat/sprint-02` 上）には取り込まれていない。

#### 3. `scripts/queue.sh` の Issue 操作

現時点（feat/sprint-02 上）の `scripts/queue.sh` には GitHub Issue を操作するロジックは**存在しない**。
queue.sh が担うのはタスクキュー（`.claude/_queue.json`）の操作のみであり、
`gh issue` コマンドや GitHub API 呼び出しは一切含まれない。

#### 4. `hooks/subagent_stop.sh` の Issue 操作

`hooks/subagent_stop.sh` は Slack 通知とキュー状態の読み取りのみを行う。
GitHub Issue を操作するコードは含まれない。

#### 5. GitHub Actions ワークフロー

`.github/workflows/slack-notify.yml` が唯一の GitHub Actions ワークフローである。
このワークフローは Issue の `opened` / `closed` イベントを **受信** して Slack に通知するだけであり、
Issue の状態を **変更** する操作は行わない。

他に Issue 操作を行うワークフロー（close-issues.yml、pr-merged.yml 等）は存在しない。

### 根本原因の特定

Issue の open / close が繰り返された直接原因は以下の複合要因である：

**原因1（主因）: PR body に `Closes #XX` 構文がなかった**

Sprint-02 の作業は複数の feature ブランチ（`feat/slack-persona`、`feat/portable-install`、
`feat/phase1-parallel`、`feat/phase2-intelligence`、`feat/phase3-agents`、`feat/phase4-antigravity`）
に分散していた。PR #33 はこれらを一括でまとめた PR であるが、body に `Closes #XX` が書かれなかったため
GitHub の自動クローズ機能が働かなかった。

**原因2（副因）: `feat/auto-close-issue` ブランチによる手動 close の試み**

`queue.sh done` 時に GitHub Issue を自動クローズする実装（`feat/auto-close-issue` ブランチ）が、
Sprint-02 とは別のタイミングで部分的に試みられた。このブランチは PR になっておらず、
本番には取り込まれていないが、ブランチ上での `gh issue close` 呼び出しが一部 Issue を close した可能性がある。

その後、PR #33 のマージや他の操作によって同じ Issue が reopen または再び open 状態に見えた結果、
open → close → reopen のサイクルが生じた。

**原因3（構造的問題）: Issue と PR の紐付けが「notes フィールド」のテキスト記述のみ**

`_queue.json` の `notes` フィールドに `GitHub Issue #12 #13 #14 #15` と記述されているが、
これはエージェントへの参照情報であり、PR のクローズ操作とは連動していない。
Issue を確実にクローズする仕組みがなかった。

## Decision

### 1. Issue クローズの唯一の正規ルート: PR body の `Closes #XX` 構文

GitHub Issue のクローズは **PR body または commit message の `Closes #XX` 構文** のみで行う。

- エージェント（Riku）が PR を作成する際、`notes` フィールドに記載された Issue 番号を PR body に含める
- フォーマット: `Closes #12, Closes #13, Closes #14, Closes #15`（複数記述可）
- GitHub API や `gh issue close` コマンドによる手動クローズは**禁止**する

### 2. `feat/auto-close-issue` ブランチの廃棄

`feat/auto-close-issue` ブランチ（コミット `722acd6`）は削除対象とする。

理由:
- PR になっておらず、QA を通過していない
- `queue.sh done` と GitHub Issue クローズを結合することで、queue.sh の責務が肥大化する
- Issue クローズのタイミングが「タスク完了時」ではなく「PR マージ時」が正しい（コードが main に入った時点で Issue が解消される）

削除コマンド:
```bash
git push origin --delete feat/auto-close-issue
git branch -d feat/auto-close-issue
```

### 3. PR テンプレートの整備

`.github/pull_request_template.md` を作成し、PR 作成時に `Closes #XX` を記述するリマインダーを入れる。

```markdown
## 概要
<!-- このPRで解決する問題を一言で -->

## 関連Issue
<!-- 対応するIssueを列挙してください -->
Closes #

## 変更内容
<!-- 主な変更点を箇条書きで -->

## チェックリスト
- [ ] 関連Issueの番号を `Closes #XX` 形式で記載した
- [ ] QA 承認済み（Sora の APPROVED を確認した）
```

### 4. Riku エージェントへの明示的なガイドライン追加

エージェント定義（pm.md または riku.md 相当のプロンプト）に以下のルールを明記する：

「PR 作成時は、`notes` フィールドに記載された Issue 番号を PR body に `Closes #XX` 形式で全件記載すること。
GitHub API による `gh issue close` の直接呼び出しは禁止。Issue のクローズは PR マージによってのみ行う。」

### 5. `slack-notify.yml` の Issue 監視継続

`slack-notify.yml` による Issue `opened/closed` の Slack 通知は維持する。
これは Issue の状態変更を**観測**するものであり、**操作**しないため問題ない。

## Consequences

### 良くなること

- Issue のクローズ経路が「PR マージ時の GitHub 自動クローズ」に一本化され、二重操作が発生しなくなる
- `queue.sh` の責務がキュー操作のみに限定され、GitHub API への依存が排除される
- PR テンプレートにより、エージェントが Issue 番号を忘れるリスクが構造的に低下する
- `feat/auto-close-issue` ブランチの削除により、未レビューのコードが本番に紛れ込む危険がなくなる

### 変わらないこと / 制約

- `_queue.json` の `notes` フィールドへの Issue 番号記載は維持する（エージェントへの文脈提供として有用）
- Issue クローズのタイミングは「コードが main にマージされた時点」に固定される（タスク完了より後になる場合がある）
- Slack 通知の主語（Yuki/Riku 固定）は変更しない

### トレードオフ

| 選択 | 得たもの | 失ったもの |
|------|---------|-----------|
| PR body の `Closes #XX` に一本化 | Issue 操作の経路が1つになり競合が発生しない | タスク完了から Issue クローズまでにラグが生じうる（PR マージまで待つ必要） |
| `queue.sh` から Issue 操作を排除 | queue.sh の単一責務を保てる | Issue クローズを `queue.sh done` に紐付けるという選択肢が使えなくなる |
| PR テンプレート導入 | 記述漏れをエージェントが気づきやすくなる | テンプレートが更新されない限り強制力はない（チェックリスト形式に留まる） |
