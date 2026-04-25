# Sprint-12 レトロスペクティブ

**実施日**: 2026-04-25  
**スプリント**: sprint-12  
**ブランチ**: feat/sprint-12  
**PR**: https://github.com/Andryu/agent-crew/pull/80  
**記録者**: みゆきち（retro エージェント）

---

## スプリント概要

| 項目 | 値 |
|------|-----|
| 完了タスク | 5/5 |
| リトライ発生 | 0 件 |
| BLOCKED 発生 | 0 件 |
| QA 結果 | APPROVED |
| 全体評価 | clean run |

---

## 観察

### 成功パターン

**全タスクがリトライ・BLOCKED なしで完了（clean run）**

Sprint-12 は全5タスクで retry_count=0、BLOCKED イベントなし、QA result=APPROVED だった。
Sprint-11 で発生した3つの失敗パターン（Sora QA形骸化・レトロスキップ・Riku Lタスク過負荷）が
エージェント定義への直接修正によって今スプリント内での再発なしに抑制された。

また、sprint-end-qa の events に `handoff → qa → done` の3段階が適切に記録されており、
Sprint-08 で問題化した QA 記録品質（Issue #67）の改善効果が確認できた。

**エージェント定義直接埋め込みが pm.md 参照より効果的**

Sprint-06 から Sprint-11 まで pm.md への記載でレトロ自動起動を促してきたが継続的に失敗した。
Sprint-12 ではエージェント定義（sora.md・qa.md）への直接追記に変更したところ、
今スプリントでの再発はなかった。今後の改善アクション設計の原則として記録する。

---

### engineer-go 調査の完了

**背景**

Issue #64（engineer-go 無応答停止バグ）は Sprint-08 から4スプリント越しの未解決課題だった。
Sprint-12 で Alex が `investigate-engineer-go` タスクを担当し、調査設計書を完成させた。

**調査設計書の成果物**: `docs/spec/engineer-go-investigation.md`

| 項目 | 内容 |
|------|------|
| 根本原因（最有力仮説） | コンテキストウィンドウ超過（仮説 A） |
| 検出方法 | 事前：指示トークン数 2,000 超で分割 / 事後：IN_PROGRESS 長時間タスクの確認 |
| 即時対処 | engineer-go.md に参照ファイル3件以下ルールを追記 |
| 中期対処 | pm.md に委譲チェックリストを追記・タスク分割基準の厳格化 |
| 将来対処 | Watchdog パターン（Sprint-13 以降） |

**残課題**: 設計書の内容が engineer-go.md・pm.md にまだ反映されていない。
Sprint-13 での実装タスクが必要。

---

## lesson 記録

### agent-crew-sprint-12-reliability-001

| フィールド | 値 |
|-----------|-----|
| category | reliability |
| priority_score | 6 (severity=3 × frequency=2) |
| issue_url | https://github.com/Andryu/agent-crew/issues/64 |
| エビデンスゲート | issue_url 設定済みのため Issue 化スキップ |

**観察**: Sprint-12 で engineer-go 無応答停止の根本原因仮説・検出方法・対処方針が設計書として完成した。しかし対処方針の実装（engineer-go.md ルール追記・pm.md 委譲チェックリスト追記）は未着手。

**アクション**: Sprint-13 で engineer-go.md・pm.md に対処ルールを実装し、Issue #64 をクローズする。

---

### agent-crew-sprint-12-process-001

| フィールド | 値 |
|-----------|-----|
| category | process |
| priority_score | 1 (severity=1 × frequency=1) |
| issue_url | なし（Issue 化不要） |
| エビデンスゲート | priority_score < 4 のため保留 |

**観察**: Sprint-12 は clean run。エージェント定義直接埋め込みが改善手法として有効であることを確認。

---

## エビデンスゲート結果

| 新規 lesson | priority_score | issue_url | ゲート判定 |
|------------|---------------|-----------|----------|
| agent-crew-sprint-12-reliability-001 | 6 | 設定済み | issue_url 既存 → Issue 化スキップ |
| agent-crew-sprint-12-process-001 | 1 | なし | priority_score < 4 → 保留 |

今スプリントの新規 Issue 作成: 0 件

---

## Sprint-13 への引き継ぎ

| 優先度 | アクション | 対象 |
|--------|-----------|------|
| 高 | engineer-go.md に参照ファイル3件以下・200行超は limit/offset ルールを追記 | engineer-go.md |
| 高 | pm.md に engineer-go 委譲チェックリストを追記 | pm.md |
| 中 | タスク分割基準（M 以下のみ委譲）を pm.md に追記 | pm.md |
| 低 | Watchdog パターンの設計・実装 | 新規スクリプト |

Issue #64 は上記の実装完了後にクローズする。

---

*このファイルは みゆきち（retro エージェント）が自動生成しました。*  
*sprint: sprint-12 / 記録 lesson: 2件 / 新規 Issue: 0件*
