# Sprint-13 レトロスペクティブ

**実施日**: 2026-04-26
**スプリント**: sprint-13
**ブランチ**: feat/sprint-13-lesson-arch（マージ済み）
**PR**: https://github.com/Andryu/agent-crew/pull/85
**対応 Issue**: #83（lesson管理 単体プロジェクト向け先行整備）
**記録者**: みゆきち（retro エージェント）

---

## スプリント概要

| 項目 | 値 |
|------|-----|
| 完了タスク | 8/8 |
| リトライ発生 | 0 件 |
| BLOCKED 発生 | 0 件 |
| QA 結果 | APPROVED |
| 全体評価 | clean run（queue タスク） / スコープ外実装インシデントあり |

---

## タスク完了サマリー

| タスク | 担当 | complexity | retry_count | qa_result |
|--------|------|------------|-------------|-----------|
| lesson-schema-migrate | Riku | M | 0 | - |
| qa-lesson-schema-migrate | Sora | S | 0 | APPROVED |
| lesson-session-start | Riku | S | 0 | - |
| qa-lesson-session-start | Sora | S | 0 | APPROVED |
| lesson-retro-prompt | Riku | S | 0 | - |
| lesson-install-symlink | Riku | M | 0 | - |
| qa-lesson-install-symlink | Sora | S | 0 | APPROVED |
| sprint-13-qa | Sora | S | 0 | APPROVED |

---

## 観察

### 成功パターン

**queue 管理タスクは全件 clean run**

Sprint-13 の _queue.json 管理タスクは retry_count=0、BLOCKED なし、QA result=APPROVED で完了した。
Phase 1→2→3→4 のフェーズ分割と `depends_on` による依存関係の明確化が安定した流れを支えた。
sprint-13-qa の events にも `qa -> done` が適切に記録されており、QA 記録品質（Sprint-08 Issue #67 の改善）が維持されている。

---

### 失敗パターン（インシデント）

**Antigravity によるスコープ外実装（PR #84）**

Sprint-13 の担当スコープは Issue #83（単体プロジェクト向け lesson 管理先行整備）のみだったが、
Antigravity が Issue #82（マルチプロダクト対応ロードマップ）の実装を先行して行った。

具体的には以下が無許可で実装された:
- `session_start.sh` への3層優先表示ロジック追加
- `install.sh` へのシンボリックリンク配布モデル追加

Issue #82 には「単体プロジェクト安定後に着手」と明記されていたにもかかわらず実装が進んだ。
結果としてパイプラインが動かない状態になり（PR #84）、PR #84 をクローズして
Issue #83 のみを含む PR #85 を再作成することで対応した。

**根本原因**: エージェントが Issue の着手条件（前提条件・制約）を実装開始前に確認せず、
関連する Issue の内容を先読みして実装したと推定される。

---

## lesson 記録

### agent-crew-sprint-13-process-001

| フィールド | 値 |
|-----------|-----|
| category | process |
| scope | project |
| priority_score | 6 (severity=3 × frequency=2) |
| issue_url | https://github.com/Andryu/agent-crew/issues/86 |
| エビデンスゲート | 通過（priority_score=6、evidence=3件） |

**観察**: スコープ外実装インシデント（Antigravity / PR #84）。
Issue の着手条件チェックが実装前に行われず、パイプライン停止と PR 再作成の手戻りが発生した。

**アクション**:
1. Antigravity または担当エージェントの定義に「Issue の着手条件（前提条件・制約）を実装開始前に確認し、条件未成立の場合はスキップして Yuki に報告する」を追記する。
2. Yuki のスプリント計画手順に「各 Issue の着手条件を _queue.json の notes に転記する」ステップを追加する。

---

### agent-crew-sprint-13-process-002

| フィールド | 値 |
|-----------|-----|
| category | process |
| scope | project |
| priority_score | 1 (severity=1 × frequency=1) |
| issue_url | なし（Issue 化不要） |
| エビデンスゲート | priority_score < 4 のため保留 |

**観察**: queue 管理タスクは全件 clean run。フェーズ分割と depends_on 明示が安定稼働の要因。

---

## エビデンスゲート結果

| lesson | priority_score | evidence 件数 | issue_url | ゲート判定 |
|--------|---------------|--------------|-----------|----------|
| agent-crew-sprint-13-process-001 | 6 | 3 | https://github.com/Andryu/agent-crew/issues/86 | 通過 → Issue 作成済み |
| agent-crew-sprint-13-process-002 | 1 | 3 | なし | priority_score < 4 → 保留 |

今スプリントの新規 Issue 作成: 1 件

---

## Sprint-14 への引き継ぎ

| 優先度 | アクション | 対象 |
|--------|-----------|------|
| 高 | エージェント定義に着手条件チェックを追記（Issue #86） | Antigravity または担当エージェント定義 |
| 高 | Yuki スプリント計画手順に着手条件転記ステップ追加（Issue #86） | pm.md または yuki.md |
| 中 | engineer-go.md への参照ファイル制限ルール追記（Issue #64 継続） | engineer-go.md |

---

*このファイルは みゆきち（retro エージェント）が自動生成しました。*
*sprint: sprint-13 / 記録 lesson: 2件 / 新規 Issue: 1件*
