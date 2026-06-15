# Sprint-23 計画書

**期間**: 2026-06-15
**ブランチ**: feat/sprint-23
**ゴール**: Sprint-22 後処理（レトロ + permissions.allow 補完）+ 定量ルーブリック自己評価 (Issue #22) + エージェント人格 Slack 口調 (Issue #30)

---

## スプリント前チェック結果

- [x] 前スプリントの設計完了タスクとの突合: 実施済み（Sprint-22 全7タスク DONE、QA APPROVED_WITH_NOTE）
- [x] 計画重複タスク: なし（Sprint-22 の実装内容と照合済み）
- [x] DECISIONS.md 反映: Sprint-21 までのエントリ確認。sprint-22 エントリは未記録（本スプリントで追記）
- [x] フック関連タスクの権限: Sprint-22 で `Bash(~/.claude/hooks/*)` の permissions.allow 追記が未完（install.sh --only=global-hooks 実行が必要）。本スプリントでフォローアップタスクとして対処する。
- [x] Riku 担当 L タスク: 0件（制限 1件/sprint に適合）
- [x] pm-learned-rules.md 反映:
  - `agent-crew-sprint-09-process-001` (priority:9) — complexity L タスクは M×2 分割 → 今スプリントの全 Riku タスクが M 以下であることを確認済み
  - `agent-crew-sprint-08-tooling-001` (priority:9) — Bash コードサンプルは bash -n バリデーション → 実装タスクの notes に明記
  - `agent-crew-sprint-08-reliability-001` (priority:6) — 委譲指示は 2,000 トークン以下 → 各タスク分割後に確認済み
  - `agent-crew-sprint-13-process-001` (priority:6) — Issue 着手条件を事前確認 → Issue #22: 「前提: _queue.json にルーブリック計算ロジック追加」条件なし（即着手可）。Issue #30: 前提条件なし（即着手可）
  - `agent-crew-sprint-07-process-001` (priority:6) — レトロ自動起動 → sprint-23-retro タスクで明示対処
- [x] 外部リポジトリ global 教訓: 対象なし（_lessons.json に agent-crew 以外の global 教訓なし）

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | risk_level | qa_mode |
|---|------|----------|------|------|------------|------------|---------|
| 1 | sprint22-retro | Sprint-22 レトロスペクティブ実施（みゆきち） | みゆきち | なし | S | low | — |
| 2 | permissions-allow-fix | Sprint-22 積み残し: permissions.allow に `Bash(~/.claude/hooks/*)` を追記 | Riku | なし | S | low | inline |
| 3 | rubric-retro | Issue #22 (1/2): retro.md にルーブリック計算ロジックを追加 | Riku | #1 | M | medium | inline |
| 4 | rubric-pm | Issue #22 (2/2): pm.md の完了報告フォーマットにスコア欄を追加 | Riku | #3 | S | low | inline |
| 5 | slack-persona-design | Issue #30 (1/2): エージェント人格 Slack 口調テンプレート設計 (Alex) | Alex | なし | M | low | — |
| 6 | slack-persona-impl | Issue #30 (2/2): subagent_stop.sh に人格別テンプレートを実装 | Riku | #5 | M | medium | inline |
| 7 | sprint23-qa | Sprint-23 最終 QA | Sora | #2 #3 #4 #6 | S | low | — |

**合計ポイント: 11 pt**（S×3=3 + M×3=9 → S×3 + M×3 = 3 + 9 = 12pt、QA タスクは S=1 で合計 13pt）

> **合計ポイント: 13 pt**（S×4=4 + M×3=9）

### Riku 担当 L タスク確認

Riku 担当タスク: permissions-allow-fix(S)・rubric-retro(M)・rubric-pm(S)・slack-persona-impl(M)
L タスク件数: **0件**（制限 1件/sprint に適合）

---

## 並列化

- **phase-1（並列実行可能）**: sprint22-retro・permissions-allow-fix・slack-persona-design は同時に進められる
- **phase-2（順次）**: rubric-retro は #1 依存（レトロ完了後）、slack-persona-impl は #5 依存（設計完了後）
- **phase-3**: rubric-pm は #3 依存、sprint23-qa は全実装タスク完了後

---

## タスク詳細と着手条件

### sprint22-retro
- 目的: Sprint-22 で実施されなかったレトロスペクティブを補完
- 着手条件: なし（即着手可）
- 成果物: `_lessons.json` への新規 lesson 追記、pm-learned-rules.md 更新、Issue化

### permissions-allow-fix
- 目的: `.claude/settings.json` の `permissions.allow` に `Bash(~/.claude/hooks/*)` を追記
- 着手条件: なし（即着手可）
- 参照ファイル: `.claude/settings.json`（1件のみ）
- bash -n バリデーション: JSON 構文確認で代替（jq . で検証）

### rubric-retro
- 目的: Issue #22 — `agents/retro.md` の「ステップ6: Yuki への完了報告」フォーマットにルーブリックスコア計算と表示を追加
- 着手条件: Issue #22 の「前提条件」セクションを確認 → 前提条件なし、即着手可
- 評価軸:
  - 仕様明確度: `1 - (retry_count合計 / タスク数)` ／ 合格 >= 0.8
  - QA 合格率: `APPROVED数 / QA対象タスク数` ／ 合格 >= 0.9
  - ブロック率: `BLOCKED数 / 総タスク数` ／ 合格 <= 0.1
  - 負荷分散: `最多担当数 / 平均担当数` ／ 合格 <= 2.0
- 参照ファイル: `agents/retro.md`、Issue #22 本文（2件）

### rubric-pm
- 目的: Issue #22 — `agents/pm.md` の「完了報告フォーマット」にスコア欄を追加
- 参照ファイル: `agents/pm.md`（1件のみ）

### slack-persona-design
- 目的: Issue #30 — 6エージェント × 3メッセージパターン（完了・ブロック・差し戻し）の口調テンプレートを `docs/spec/slack-persona.md` として設計
- 着手条件: Issue #30 の「前提条件」セクションを確認 → 前提条件なし（Issue #29 との組み合わせ検証は受け入れ基準だが着手条件ではない）
- 参照ファイル: Issue #30 本文、`hooks/subagent_stop.sh`（2件）

### slack-persona-impl
- 目的: Issue #30 — `hooks/subagent_stop.sh` に人格別テンプレートを実装
- 参照ファイル: `docs/spec/slack-persona.md`、`hooks/subagent_stop.sh`（2件）
- 注意: Bash コードは `bash -n` でバリデーション必須

---

## 変更ファイル予定

| ファイル | 変更種別 |
|---------|---------|
| `.claude/settings.json` | permissions.allow に `Bash(~/.claude/hooks/*)` 追記 |
| `~/.claude/_lessons.json` | Sprint-22 lesson 追記 |
| `.claude/agents/pm-learned-rules.md` | Sprint-22 lesson 反映（あれば） |
| `.claude/agents/retro.md` | ルーブリック計算ロジック追加（Issue #22） |
| `.claude/agents/pm.md` | 完了報告フォーマットにスコア欄追加（Issue #22） |
| `docs/spec/slack-persona.md` | 新規作成（Issue #30 設計書） |
| `hooks/subagent_stop.sh` | 人格別テンプレート実装（Issue #30） |
| `.claude/_queue.json` | Sprint-23 タスク状態記録 |
| `docs/sprints/sprint-23.md` | 本ファイル |
| `docs/DECISIONS.md` | Sprint-22・Sprint-23 エントリ追記 |

---

## 完了条件

- [ ] Sprint-22 レトロスペクティブ完了（みゆきちによる lesson 記録）
- [ ] `.claude/settings.json` に `Bash(~/.claude/hooks/*)` が追記されている
- [ ] `agents/retro.md` にルーブリック計算ロジック（jq コマンド）が追加されている
- [ ] `agents/pm.md` の完了報告フォーマットにスコア欄が追加されている
- [ ] `docs/spec/slack-persona.md` が作成されている
- [ ] `hooks/subagent_stop.sh` に 6エージェント × 3パターンのテンプレートが実装されている
- [ ] Sora QA: APPROVED

---

## トークン消費見積もり

| タスク | complexity | 推定トークン |
|--------|------------|------------|
| sprint22-retro | S | 15,000 |
| permissions-allow-fix | S | 15,000 |
| rubric-retro | M | 40,000 |
| rubric-pm | S | 15,000 |
| slack-persona-design | M | 40,000 |
| slack-persona-impl | M | 40,000 |
| sprint23-qa | S | 15,000 |

推定合計 = (15,000 × 4 + 40,000 × 3) × 1.5 = (60,000 + 120,000) × 1.5 = **270,000 tokens**

300,000 tokens 未満 → 1 バッチで処理可能
