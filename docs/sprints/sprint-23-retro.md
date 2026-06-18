# Sprint-23 レトロスペクティブ

- 実施日: 2026-06-18
- 担当: みゆきち（retro エージェント）
- スプリント: sprint-23

---

## ルーブリックスコア

| 評価軸 | スコア | 合格基準 | 判定 |
|--------|--------|---------|------|
| 仕様明確度 | 1.00 | >= 0.8 | PASS |
| QA合格率 | 1.00 | >= 0.9 | PASS |
| ブロック率 | 0.00 | <= 0.1 | PASS |
| 負荷分散 | 2.29 | <= 2.0 | FAIL |

> FAIL 軸: 負荷分散（次スプリントの改善優先事項: Riku への集中を解消する）

---

## スプリント概要

- タスク数: 7（全 DONE）
- retry_count 合計: 0
- BLOCKED タスク: 0
- QA 対象: 4タスク（全 APPROVED）
- CRITICAL / MAJOR: ゼロ
- MINOR: 2件（build_retry_message の不一致・dead code）

### 担当者内訳

| エージェント | タスク数 | タスク一覧 |
|-------------|---------|-----------|
| Riku | 4 | permissions-allow-fix / rubric-retro / rubric-pm / slack-persona-impl |
| Alex | 1 | slack-persona-design |
| Sora | 1 | sprint23-qa |
| みゆきち | 1 | sprint22-retro |

---

## 成功パターン（Keep）

### フェーズ依存関係の適切な設計

phase-1 → phase-2 → phase-3 → phase-4 の直列依存が正しく機能し、全タスクが retry なし・ブロックなしで完了した。仕様明確度・QA合格率・ブロック率の3軸でルーブリック合格基準をクリアした。

### Sprint-22 積み残しの補完完了

Sprint-22 で未実施だったレトロスペクティブと permissions.allow 修正の2件を sprint22-retro・permissions-allow-fix タスクとして補完し、技術的負債を解消した。

---

## 失敗パターン（Problem）

### 負荷分散 FAIL: Riku への集中

タスク7件中4件が Riku に割り当てられ、負荷分散スコアが 2.29（基準 2.0 超え）になった。permissions-allow-fix(S)・rubric-pm(S) など S タスクは他エージェントへの再配分が可能だった。「実装タスクは Riku が適任」という暗黙の想定がスプリント計画に影響している。

### Slack 人格実装の設計書カバレッジ不足

build_retry_message 関数で Yuki 系エージェントのみ retry_count 表示を省略し、他エージェントには表示するという非一貫な実装が混入した。設計書（slack-persona.md）に retry_count 表示有無のルールが明記されていなかったことが根因。また他エージェントケースが dead code になっており、設計意図が実装に反映されていなかった（Sora QA MINOR 指摘2件）。

---

## 記録した Lesson

| lesson_id | 概要 | priority |
|-----------|------|---------|
| agent-crew-sprint-23-planning-001 | スプリント計画時の担当者負荷分散スコア事前計算 | 6 |
| agent-crew-sprint-23-design-001 | 設計書への条件分岐挙動差異の明示と実装前レビュー | 4 |
| agent-crew-sprint-23-process-001 | Sprint-23 clean run 記録（負荷分散 FAIL を除く3軸 PASS） | 1 |

---

## Issue 化結果

| lesson_id | 判定 | 理由 |
|-----------|------|------|
| agent-crew-sprint-23-planning-001 | 保留 | priority=6・evidence あり — Bash 権限なし（gh issue create 実行不可）。次スプリントで作成すること |
| agent-crew-sprint-23-design-001 | 保留 | priority=4・evidence あり — Bash 権限なし（gh issue create 実行不可）。次スプリントで作成すること |
| agent-crew-sprint-23-process-001 | 対象外 | priority=1（基準 priority >= 4 未満） |

> 注: `gh issue create` は Bash 権限が必要です。Sprint-23 の settings.json に `Bash(gh *)` が含まれていないため Issue 作成はスキップしました。次スプリント開始前に Yuki が手動で Issue 作成するか、settings.json に `Bash(gh *)` を追加してください。

---

## pm-learned-rules.md 更新結果

- 追加: 2件
  - `agent-crew-sprint-23-planning-001`: [Yuki] スプリント計画時に担当者の負荷分散スコアを事前計算する
  - `agent-crew-sprint-23-design-001`: [Alex / Riku] 設計書には条件分岐ごとの挙動差異を明示し、実装前にレビューする
- スキップ（重複）: 0件
- スキップ（priority < 3）: 1件（agent-crew-sprint-23-process-001）

---

## 次スプリントへの改善優先事項

1. **負荷分散改善（FAIL 軸）**: Yuki はスプリント計画時に担当者ドラフト後に負荷分散スコアを計算し、Riku 比率 50% 超の場合は再配分する。
2. **設計書レビューフロー**: Alex が実装着手前に設計書をレビューし、dead code・挙動差異の曖昧さを事前検出するステップをフローに追加する。
3. **Issue 作成の権限設定**: gh コマンドを retro フェーズで使えるよう `Bash(gh *)` を permissions.allow に登録する。
