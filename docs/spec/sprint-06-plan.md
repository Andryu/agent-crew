# Sprint-06 計画

作成日: 2026-04-23
作成者: Yuki（PM エージェント）
依拠情報:
- docs/retro/sprint-05.md（みゆきち レトロ）
- GitHub Issues（open: #47, #48, #49, #50, #51, #52）
- docs/spec/session-interrupt-design.md（設計書完成済み）
- .github/workflows/slack-notify.yml（現行通知ワークフロー）

---

## スプリントゴール

**Slack通知のノイズ削減（#52）を軸に、2スプリント連続で繰り返された PR Test Plan 漏れ（#49）とコミット判断基準の未明文化（#50）をプロセス面から根絶する。**
あわせて、設計書が完成済みのセッション中断検出機構（#39）を実装し、スプリント完了後の retro 自動起動（#47）でオーナー介入をさらに削減する。

---

## 背景・判断根拠

### P0: Slack通知の絞り込み（#52）— オーナー指示・優先度高

Issue登録・クローズ・PR作成・PRマージごとに通知が飛び、ノイズになっている。
`.github/workflows/slack-notify.yml` を無効化し、スプリント開始/完了の2通知のみ Yuki が `curl` で直接送信する構成に一本化する。
実装コスト S・影響範囲が狭く、即時効果が高い。

### P0: PR Test Plan 漏れの恒久対処（#49）— priority-high、2スプリント連続

PRテンプレートと riku.md（実装完了チェックリスト）の両方に「PR Test Planが記入されているか確認する」を追加する。
コード変更不要の設定修正のみ。Sprint-04 から持ち越し続けているため最優先。

### P1: コミット判断基準の明文化（#50）

pm.md に「スプリント完了後はオーナー確認なしにコミット・Draft PR 作成してよい」と明記。
コスト XS。P0 と同じ Riku タスクにまとめて対処できる。

### P1: セッション中断検出の実装（#39）

`session-interrupt-design.md` が Sprint-05 で完成済み。設計に従い `queue.sh` に `check-stale` コマンドと `session_start.sh` への警告表示を実装する。

### P2: みゆきち自動起動の pm.md 組み込み（#47）

スプリント完了後に毎回オーナーが retro 指示を出している。pm.md の完了報告フローに「Quality Gate 通過後、みゆきち（retro）を起動する」を追記する。
コスト XS。Riku 実装タスクに含める。

### バックログ Issue の評価

| Issue | 優先度 | Sprint-06 採否 | 理由 |
|-------|--------|---------------|------|
| #52 Slack通知絞り込み | 最高（オーナー指示） | 採用 | ノイズ解消・即時効果大 |
| #49 PR Test Plan 漏れ | 高（2スプリント連続） | 採用 | 繰り返し防止 |
| #50 コミット判断明文化 | 中 | 採用 | 介入最小化の補強 |
| #39 セッション中断検出 | 中 | 採用（実装） | 設計完成済み・積み残し解消 |
| #47 みゆきち自動起動 | 中 | 採用 | オーナー介入削減 |
| #51 Bash不可コンテキスト問題 | 中 | 保留 | 設計が必要。Sprint-07候補 |
| #48 Soraスリープ切断問題 | 中 | 保留 | 対策難度高・Sprint-07候補 |
| #36 トークン最適化（残課題） | 高 | 保留 | Sprint-05でADR実装済み。追加対処は次スプリント |
| #22 定量ルーブリック | 中 | 保留 | Sprint-07候補 |
| #23 _signals.jsonl | 中 | 保留 | Sprint-07候補 |

---

## タスク一覧

### タスク概要表

| # | slug | タイトル | 担当 | complexity | 依存 | Issues |
|---|------|---------|------|-----------|------|--------|
| 1 | slack-notify-trim | Slack通知をスプリント開始/完了の2つに絞る | Riku | S | なし | #52 |
| 2 | slack-notify-qa | Slack通知絞り込みのQA | Sora | S | #1 | #52 |
| 3 | process-doc-fix | PR Test Plan必須化 + コミット基準明文化 + みゆきち自動起動追記 | Riku | S | なし | #49 #50 #47 |
| 4 | process-doc-qa | プロセスドキュメント修正のQA | Sora | S | #3 | #49 #50 #47 |
| 5 | session-interrupt-impl | セッション中断検出機構の実装（queue.sh + session_start.sh） | Riku | M | なし | #39 |
| 6 | session-interrupt-qa | セッション中断検出機構のQA | Sora | M | #5 | #39 |

---

## 実行順序（直列）

```
#1 slack-notify-trim
  → #2 slack-notify-qa
    → #3 process-doc-fix
      → #4 process-doc-qa
        → #5 session-interrupt-impl
          → #6 session-interrupt-qa
```

タスク #1/#3/#5 は互いに依存しないが、並列実行禁止ルール（`_queue.json` 競合防止）に従い直列で進める。

---

## 各タスクの作業内容

### #1 slack-notify-trim（Riku / S）

- `.github/workflows/slack-notify.yml` のすべてのトリガー（issues/pull_request）を削除または `on: {}` で無効化
- pm.md の Slack通知セクションを更新：「スプリント開始時・完了時のみ curl で直接送信」と明記
- Issue #52 をクローズ

### #2 slack-notify-qa（Sora / S）

- slack-notify.yml が無効化されていることを確認
- pm.md の記載が意図通りであることをレビュー
- Test Plan: 誤通知が発生しないことを diff で確認

### #3 process-doc-fix（Riku / S）

- `.github/PULL_REQUEST_TEMPLATE.md`（存在しなければ新規作成）に Test Plan チェックリスト確認を追加
- `.claude/agents/riku.md` の実装完了チェックリストに「PR Test Plan が記入されているか確認」を追加
- `pm.md`（または `CLAUDE.md`）に「スプリント完了後はオーナー確認なしにコミット・Draft PR 作成してよい（ブランチ: feat/sprint-XX-clean）」を追記
- pm.md の完了報告フローに「Quality Gate 通過後、みゆきち（retro エージェント）を起動する」を追記
- Issues #49 #50 #47 をクローズ

### #4 process-doc-qa（Sora / S）

- PR テンプレートの Test Plan 記載確認
- riku.md チェックリスト追加確認
- pm.md のコミット基準・みゆきち起動フロー記載確認
- Test Plan: 各ファイルの diff レビュー

### #5 session-interrupt-impl（Riku / M）

- `session-interrupt-design.md` に従い `scripts/queue.sh` に `check-stale` サブコマンドを追加
  - IN_PROGRESS かつ最終 start イベントから60分超のタスクを検出して警告表示
  - events に start が存在しない IN_PROGRESS タスクは「不整合状態」警告
- `scripts/session_start.sh` のセッション開始表示に未完了 IN_PROGRESS タスク一覧を追記
- Issue #39 をクローズ

### #6 session-interrupt-qa（Sora / M）

- `check-stale` コマンドの動作確認（モックデータで stale タスクが検出されるか）
- `session_start.sh` の出力に未完了タスクが表示されるか確認
- Test Plan: edge case（IN_PROGRESS タスクなし / 複数 stale タスク）の確認

---

## 並列化できるもの

タスク #1・#3・#5 は互いに依存しないため、並列解禁後は同時実行可能。
現行ルール（直列のみ）では #1 → #3 → #5 の順で進める。

---

## リスク・懸念事項

| リスク | 対策 |
|--------|------|
| slack-notify.yml 無効化により既存 GitHub Actions が壊れる | yml を削除せず `on: {}` で無効化し、差分を Sora が確認 |
| PR テンプレートが存在しない場合 | Riku が `.github/PULL_REQUEST_TEMPLATE.md` を新規作成 |
| session_start.sh が存在しない場合 | Riku が存在確認後、存在しなければスキップし notes に記録 |

---

## Quality Gate（スプリント完了判定）

1. 全タスク（#1〜#6）の `status == "DONE"`
2. 全タスクの `qa_result == "APPROVED"`
3. Issues #52 #49 #50 #47 #39 がすべてクローズ済み

---

## 確認事項

- [ ] #52 の対応方針（slack-notify.yml 削除 vs 無効化）: 無効化（`on: {}`）を推奨。削除だとトリガー構成が失われる。問題なければ Go。
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` が未存在の場合、新規作成してよいか: Yes 想定で進める。

承認したら「Go」と返してください。
