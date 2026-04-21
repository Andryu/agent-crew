# Sprint-03 計画書

作成日: 2026-04-21
ステータス: Draft

---

## ゴール

agent-crew の「自己学習・自己改善」基盤を構築する。
スプリントをまたいで失敗パターンを蓄積し、次スプリントの計画品質を自動的に向上させるループを完成させる。
あわせて Issue の open/close 管理上の不具合（#34）を根本解消する。

---

## 背景・前提

### Sprint-02 の振り返り

- エージェント人格化・汎用化・並列実行基盤・新エージェント（Tomo/Ren/みゆきち）が完成
- QA差し戻し率 0%、BLOCKED 0件と安定稼働
- 課題：みゆきち（retro.md）は存在するが Yuki（pm.md）との連携フローが未定義
- 課題：_lessons.json / _signals.jsonl / pm-learned-rules.md の仕組みが未実装
- 課題：Issue の open/close 制御に繰り返しバグがある（#34）

### 対象 Issue

| Issue | タイトル | 優先度 | Sprint-03 採否 |
|-------|---------|--------|---------------|
| #34 | Issue open/close が繰り返される問題 | priority-high（Bug） | 採用 |
| #20 | Yuki 自己改善提案モード | priority-high | 採用 |
| #21 | エピソード記憶ファイル（_lessons.json） | priority-high | 採用 |
| #25 | エビデンス閾値ゲート | priority-high | 採用 |
| #27 | セッション開始時の文脈ブリーフィング（Start hook） | priority-high | 採用 |
| #28 | pm.md にみゆきち連携フローを追加 | priority-high | 採用 |
| #22 | 定量ルーブリック自己評価 | priority-medium | 保留（Sprint-04候補） |
| #23 | リアルタイム品質シグナル捕捉（_signals.jsonl） | priority-medium | 保留（Sprint-04候補） |
| #24 | 学習ルール自動反映（Learnings Loop） | priority-medium | 保留（Sprint-04候補） |
| #26 | 改善提案レビューループ（Hana による品質チェック） | priority-low | 対象外 |
| #30 | Slack エージェント人格口調反映 | priority-medium | 対象外 |
| #31 | ドット絵キャラ＋カフェ可視化 Web アプリ | priority-low | 対象外 |

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | 対応 Issue |
|---|------|---------|------|------|-----------|-----------|
| 1 | issue-close-bug-investigation | Issue open/close 繰り返しバグの調査・修正 | Alex → Riku → Sora | なし | M | #34 |
| 2 | lessons-json-schema | _lessons.json スキーマ定義と templates 追加 | Alex | なし | S | #21 |
| 3 | evidence-gate-design | エビデンス閾値ゲートの設計（Idea F） | Alex | #2 | S | #25 |
| 4 | miyukichi-yuki-flow-design | pm.md へのみゆきち連携フロー設計 | Alex | #2 #3 | S | #28 |
| 5 | self-improvement-mode-design | Yuki 自己改善提案モードの設計 | Alex | #4 | S | #20 |
| 6 | start-hook-design | Start hook（session_start.sh）設計 | Alex | #2 | S | #27 |
| 7 | lessons-json-impl | _lessons.json 実装（テンプレ + 初期データ） | Riku | #2 | S | #21 |
| 8 | miyukichi-yuki-flow-impl | pm.md + retro.md 更新（みゆきち連携） | Riku | #4 #7 | M | #28 |
| 9 | self-improvement-mode-impl | pm.md 自己改善提案モード実装 | Riku | #5 #8 | M | #20 |
| 10 | evidence-gate-impl | エビデンスゲートロジック実装（retro.md 更新） | Riku | #3 #8 | S | #25 |
| 11 | start-hook-impl | session_start.sh + settings.json + install.sh 更新 | Riku | #6 #7 | S | #27 |
| 12 | sprint03-qa | 全実装の QA・コードレビュー | Sora | #7〜#11 | M | — |

---

## タスク詳細

### タスク 1: issue-close-bug-investigation

**概要**: Issue #34 の調査と修正。PR body の `Closes #XX` 有無確認、subagent_stop.sh / queue.sh での Issue 操作有無の確認、GitHub Actions workflow の確認、再発防止策の実装。

**完了条件**:
- 原因が特定され docs/adr/ または DECISIONS.md に記録されている
- 再発防止策が実装またはドキュメント化されている
- 同様のバグが発生しない仕組みが整っている

### タスク 2: lessons-json-schema

**概要**: `.claude/_lessons.json` のスキーマを設計し `templates/_lessons.json` を新規作成する。Issue #21 のスキーマ例をベースに。

**完了条件**:
- `templates/_lessons.json` が作成されている
- スキーマが docs/spec に記載されている

### タスク 3: evidence-gate-design

**概要**: 改善提案を issue 化する前のフィルタリングロジック設計。`severity_score × frequency_score` による priority 算出ルール。

**完了条件**:
- ゲート条件と priority 算出式が ADR または pm.md に定義されている

### タスク 4: miyukichi-yuki-flow-design

**概要**: Yuki（pm.md）がスプリント完了後にみゆきちを起動し、提案を受け取って Issue 化するフローの設計。

**完了条件**:
- Yuki → みゆきち → Yuki の連携フローが設計文書化されている

### タスク 5: self-improvement-mode-design

**概要**: Yuki がスプリント完了後または明示的指示で自己改善提案を実施するモードの設計。トリガー条件・出力フォーマット・gh issue create コマンドのテンプレートを含む。

**完了条件**:
- 自己改善提案モードの仕様が設計文書化されている

### タスク 6: start-hook-design

**概要**: `Start` hook として `hooks/session_start.sh` の設計。未完了タスクと _lessons.json のサマリーを表示する。

**完了条件**:
- session_start.sh の動作仕様が定義されている

### タスク 7〜11: 各実装

設計（#2〜#6）に基づく実装。

### タスク 12: sprint03-qa

全実装タスクのレビュー。ファイル構成・pm.md の整合性・フロー定義の一貫性を確認。

---

## 実行順序（直列）

```
タスク1（issue-close-bug）
  ↓
タスク2（lessons-json-schema）
  ↓
タスク3・6（evidence-gate-design / start-hook-design）※どちらか先に1件ずつ
  ↓
タスク4（miyukichi-yuki-flow-design）
  ↓
タスク5（self-improvement-mode-design）
  ↓
タスク7（lessons-json-impl）
  ↓
タスク8（miyukichi-yuki-flow-impl）
  ↓
タスク9（self-improvement-mode-impl）
  ↓
タスク10（evidence-gate-impl）
  ↓
タスク11（start-hook-impl）
  ↓
タスク12（sprint03-qa）
```

注: 現状は並列実行禁止。タスク3と6は依存関係がないが、直列で1件ずつ実行する。

---

## 並列化の可能性（将来）

scripts/queue.sh の flock 対応後に以下を並列化できる：
- タスク3（evidence-gate-design）と タスク6（start-hook-design）

---

## 成功指標

| 指標 | 目標 |
|------|------|
| _lessons.json 実装完了 | templates/ + .claude/ 両方に存在 |
| Yuki→みゆきち連携フロー | pm.md に手順が記載されている |
| 自己改善提案モード | pm.md に定義 + gh issue create テンプレート付き |
| Start hook | session_start.sh が動作し queue + lessons を表示 |
| Issue #34 根本対応 | 原因特定 + 再発防止策が実装またはドキュメント化 |
| QA差し戻し率 | 30% 以下（Sprint-02 実績: 0% を維持）|

---

## 保留タスク（Sprint-04 候補）

| Issue | タイトル | 理由 |
|-------|---------|------|
| #22 | 定量ルーブリック自己評価 | _lessons.json と みゆきち連携が安定してから |
| #23 | リアルタイム品質シグナル捕捉（_signals.jsonl） | Start hook 基盤が完成してから拡張 |
| #24 | 学習ルール自動反映（Learnings Loop） | #21 #22 #23 が揃ってから |

---

## 決定事項（2026-04-21 オーナー承認済み）

- [x] `_lessons.json` → **グローバル**（`~/.claude/_lessons.json`）。競合対策（ファイルロック or append-only）を設計に含める
- [x] `session_start.sh` → **プロジェクトローカル**（`.claude/settings.json` で設定）。プロジェクトごとにキュー状態が異なるため
- [x] Issue #34 調査で不要スクリプト（queue.sh / subagent_stop.sh 等で Issue API を直接叩いている箇所）が見つかった場合 → **削除OK**
