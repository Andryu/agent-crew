# Sprint-17 計画書 / レトロスペクティブ

**期間**: 2026-04-26  
**ブランチ**: feat/sprint-17  
**PR**: https://github.com/Andryu/agent-crew/pull/98

---

## ゴール

Issue #61（TaskCompleted hook）の実装、Issue #86（engineer-go 着手条件チェック）の適用、Sprint-16 マージ済み lesson の Issue クローズ処理を完遂する。

---

## スプリント前チェック結果

- [x] 前スプリントの設計完了タスクとの突合: 実施済み（Sprint-16 全4タスク DONE 確認）
- [x] 計画重複タスク: なし
- [x] _lessons.json priority >= 6 未解決エントリ確認: sprint-17-tooling-001（新規）・sprint-13-process-001（Issue #86 対応タスクとして sprint-17 で対処）

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | retry | qa_result |
|---|------|----------|------|------|------------|-------|-----------|
| 1 | hook-design | TaskCompleted hook 設計書作成 | Alex | なし | M | 0 | — |
| 2 | lesson-issue-close | PR #93 マージ済み lesson status 更新・Issue #95/#96/#78/#36 クローズ | Yuki | なし | S | 0 | — |
| 3 | agent-precondition-doc | engineer-go.md 着手条件チェック追記（Issue #86 対応） | Riku | なし | S | 0 | inline |
| 4 | hook-impl | TaskCompleted hook 実装（task_completed.sh 新規作成・settings.json 更新） | Riku | hook-design | M | 0 | inline |
| 5 | sprint17-qa | Sprint-17 最終QA | Sora | #3 #4 | S | 0 | APPROVED |

**Riku担当 L タスク**: 0件（制限 1件/sprint に適合）

---

## 今スプリントで起きたこと

### ブロック事象

- **Write 権限不足で Yuki が2回ブロック**: `Write(**)` / `Bash(chmod *)` / `Bash(bash *)` の3権限が settings.json に未登録だった。hook-impl タスク中に判明し、settings.json に追記して対処した。
- **レート制限による一時中断**: hook-impl 完了直後にレート制限に到達。再開後、sprint17-qa が正常完了した。

### 成功パターン

- _queue.json への状態記録により、レート制限中断後に重複作業なく再開できた（全タスク retry_count=0）。
- hook-design（Alex）→ hook-impl（Riku）の依存関係（depends_on）が設計通りに機能した。
- Sora QA が bash -n・jq valid・settings.json hook 登録を実際に確認し APPROVED（全5チェック通過）。

---

## 変更ファイル

| ファイル | 変更種別 |
|---------|---------|
| `.claude/hooks/task_completed.sh` | 新規作成 |
| `.claude/settings.json` | TaskCompleted hook 追加・権限3件追加 |
| `.claude/agents/engineer-go.md` | 着手条件チェック2箇所追記 |
| `docs/spec/hook-taskcompleted-design.md` | 新規作成 |
| `.claude/_queue.json` | Sprint-17 タスク状態記録 |
| `.claude/_signals.jsonl` | task_completed イベント記録 |

---

## レトロスペクティブ（みゆきち）

### 記録した lesson

| lesson_id | 概要 | priority |
|-----------|------|----------|
| agent-crew-sprint-17-tooling-001 | フック実装タスクで権限3件が未登録のまま着手、Yuki が2回ブロック | 6 |
| agent-crew-sprint-17-reliability-001 | レート制限中断後も _queue.json の状態保持で重複なく再開 | 3 |

### エビデンスゲート結果

| lesson_id | priority_score | evidence 件数 | ゲート通過 |
|-----------|---------------|--------------|----------|
| agent-crew-sprint-17-tooling-001 | 6 | 2 | 通過 |
| agent-crew-sprint-17-reliability-001 | 3 | 2 | 保留（priority < 4） |

### Issue 化

- **作成**: agent-crew-sprint-17-tooling-001 → Issue 作成対象
- **保留**: agent-crew-sprint-17-reliability-001（priority_score=3）

### pm-learned-rules.md 追記

- 追加: 1件（agent-crew-sprint-17-tooling-001）
- スキップ（重複）: 0件

---

## 完了条件（達成済み）

- [x] `.claude/hooks/task_completed.sh` が存在し bash -n 構文エラーなし
- [x] `settings.json` に TaskCompleted hook が登録されている
- [x] `engineer-go.md` に着手条件チェックルールが2箇所追記されている
- [x] Sora QA: APPROVED（全5チェック通過）
- [x] Draft PR #98 作成済み
