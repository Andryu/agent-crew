# Sprint-12 計画書

**期間**: 2026-04-24 〜  
**ブランチ**: `feat/sprint-12`  
**作成**: Yuki

---

## ゴール

Sprint-11 の失敗パターン（Sora Bash上限QA形骸化・レトロ起動スキップ・Riku Lタスク過負荷）を
エージェント定義の直接修正で根絶する。あわせて engineer-go 停止バグの再現調査を行い、
根本原因を特定する。

---

## 背景・判断根拠

- Sprint-11 の失敗パターンより priority_score >= 6 の未対処 lesson が2件（レトロ自動起動・Sora QA形骸化）
- sora.md・qa.md・pm.md への直接追記はアーキテクチャ変更を伴わないため設計不要
- #64（engineer-go 無応答停止）は再現条件が不明なため Alex による調査設計が必要
- #67（QA形骸化）は #76 と同一ファイル（qa.md）を対象とするため統合処理

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | risk_level | qa_mode |
|---|------|---------|------|------|------------|------------|---------|
| 1 | `fix-sora-retro` | sora.md にレトロ起動指示を直接追記（Issue #77） | Riku | なし | S | low | end_of_sprint |
| 2 | `fix-qa-bash-limit` | qa.md に Bash上限時 CHANGES_REQUESTED ルールを追記（Issue #76 + #67） | Riku | なし | S | low | end_of_sprint |
| 3 | `fix-riku-l-limit` | pm.md に Riku の L タスク1件制限ルールを追記（Issue #78） | Riku | なし | S | low | end_of_sprint |
| 4 | `investigate-engineer-go` | engineer-go 無応答停止バグの再現調査・設計（Issue #64） | Alex | なし | M | medium | — |
| 5 | `sprint-end-qa` | Sprint-12 最終 QA（全修正ファイルのレビュー） | Sora | #1 #2 #3 #4 | M | medium | — |

> **合計ポイント: 10 pt**（S×3=3 + M×2=6 + Alex設計1件を含む）

> 推定トークン消費: 90,000 tokens（60K × 1.5）→ **1バッチ構成**

> `qa_mode` 列: `—` は設計・QAタスク（対象外）を意味する。

---

## バッチ構成

### Batch 1（全タスク）

依存グラフ:
```
#1 fix-sora-retro   ─┐
#2 fix-qa-bash-limit ─┤→ #5 sprint-end-qa
#3 fix-riku-l-limit  ─┤
#4 investigate-engineer-go ─┘
```

#1・#2・#3・#4 は互いに独立。全て完了後に #5 を実行。

---

## タスク詳細

### #1 fix-sora-retro（Riku）

**目的**: Issue #77 対処。sora.md の「スプリント完了報告」セクションに
レトロ起動の明示的な指示を直接記載する。

変更対象: `.claude/agents/sora.md`

追記内容:
- 全タスクが DONE になった時点で、完了報告末尾に `@retro を起動してください` を必ず含める
- pm.md 参照ではなく sora.md 内に直接ルールとして記載する

**完了基準**: sora.md にレトロ起動の指示が明示されている

---

### #2 fix-qa-bash-limit（Riku）

**目的**: Issue #76（Bash上限時CHANGES_REQUESTED）と Issue #67（QA形骸化）を統合対処。
qa.md の QA 手順に Bash 実行不可時のルールを追記する。

変更対象: `.claude/agents/qa.md`（存在しない場合は `sora.md` の QA 手順セクション）

追記内容:
- Bash 実行が不可能な場合（上限到達）は CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）を返す
- 静的検証のみで APPROVED を出してはいけない
- 代替実行者（メインセッション）が QA を実施した場合は `performed_by: human` を notes に記録する

**完了基準**: Bash 不可時のルールが QA 手順に明示されている

---

### #3 fix-riku-l-limit（Riku）

**目的**: Issue #78 対処。pm.md の Riku 委譲ルールに L タスク数制限を追記する。

変更対象: `.claude/agents/pm.md`

追記内容:
- Riku への L タスクは1スプリント1件を上限とする
- タスク分解時に L タスクが2件以上になる場合は、いずれかを M に分割するかスコープ削減する

**完了基準**: pm.md に L タスク制限ルールが明示されている

---

### #4 investigate-engineer-go（Alex）

**目的**: Issue #64（engineer-go 無応答停止）の再現条件と根本原因を調査し、
対処方針を設計する。

成果物: `docs/spec/engineer-go-investigation.md`

調査内容:
- engineer-go エージェントの定義（`.claude/agents/engineer-go.md` または相当ファイル）を確認
- 停止が報告されたコンテキスト（タスクサイズ・ファイル数・依存状態）を _queue.json の events から確認
- タイムアウト・レート制限・無限ループの可能性を列挙
- 再現手順（もしあれば）と検出方法を提案
- 対処方針（タイムアウト設定・watchdog・分割基準など）を提示

**完了基準**: 設計書が存在し、再現条件の仮説・検出方法・対処方針が記載されている

---

### #5 sprint-end-qa（Sora）

**目的**: Sprint-12 で修正した全ファイルのレビューを実施する。

確認対象:
- `sora.md`: レトロ起動指示が明確に記載されているか
- `qa.md` または `sora.md` の QA セクション: Bash 不可時ルールが正しく追記されているか
- `pm.md`: L タスク制限ルールが計画手順に組み込まれているか
- `docs/spec/engineer-go-investigation.md`: 調査内容が網羅的か

**重要**: Bash 実行が不可能な場合は CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）を返すこと（今回適用する新ルールを自身に適用する）

---

## 並列化できるもの

- #1 `fix-sora-retro`・#2 `fix-qa-bash-limit`・#3 `fix-riku-l-limit`・#4 `investigate-engineer-go`
  はすべて互いに独立しているが、**同一エージェント（Riku）への同時委譲は禁止**のため直列実行する
- #4 は Alex 担当なので #1〜#3 の完了を待たず着手可能（ただし並列起動は1エージェント1件制限に注意）

---

## Quality Gate

スプリント完了条件:
1. 全タスクの `status == "DONE"`
2. `sprint-end-qa` の `qa_result == "APPROVED"`
3. sora.md・qa.md（またはQAセクション）・pm.md に各ルールが明示されている
