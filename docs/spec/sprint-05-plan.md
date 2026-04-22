# Sprint-05 計画

作成日: 2026-04-22
作成者: Yuki（PM エージェント）
依拠情報:
- docs/retro/sprint-04.md
- GitHub Issues（open: #22, #23, #24, #30, #36, #39, #43）
- docs/adr/token-optimization-adr.md
- docs/spec/self-improvement-mode-design.md
- .claude/agents/architect.md（Bash ツール未付与の確認）

---

## スプリントゴール

**Alex（architect）が Bash ツールなしで作業を完結できず、Yuki が queue.sh を代行している構造的問題（#43）を解消する。**
あわせて、高優先度 Issue として積み残している「トークン消費最適化の実装（#36）」に着手する。

---

## 背景・判断根拠

### 最優先: Alex への Bash ツール付与（#43）

Sprint-04 レトロの P-1・T-1 で明確に指摘された。
Alex が `queue.sh done / handoff` を自己実行できないため、全スプリントで Yuki の介入コストが発生し続けている。
architect.md の `tools:` 行に `Bash` を追加するだけで解消できるため、実装コストは S。

### 次優先: トークン最適化の実施（#36）

ADR-004（token-optimization-adr.md）は Accepted 状態だが、pm.md・各エージェント定義への反映が未実施。
`priority-high` ラベルで最長積み残しの Issue。レート制限リスクはスプリント規模が大きくなるほど高まるため早期対処が必要。

### バックログ Issue の評価

| Issue | 優先度 | Sprint-05 採否 | 理由 |
|-------|--------|---------------|------|
| #43 Alex Bash ツール問題 | 最高 | 採用 | 毎スプリント再発 |
| #36 トークン最適化 | 高 | 採用 | ADR 実装未完 |
| #39 セッション中断検出 | 中 | 採用（設計のみ） | 検出機構の設計は独立して進められる |
| #22 定量ルーブリック自己評価 | 中 | 保留 | Sprint-06 候補 |
| #23 リアルタイム品質シグナル（_signals.jsonl） | 中 | 保留 | Sprint-06 候補 |
| #24 学習ルール自動反映 | 中 | 保留 | Sprint-07 候補 |
| #30 Slack エージェント人格反映 | 中 | 保留 | UI 改善。コア機能優先 |
| #31 ドット絵 Web アプリ | 低 | スコープ外 | 別リポジトリ扱い |

---

## タスク一覧

### タスク概要表

| # | slug | タイトル | 担当 | complexity | 依存 | 優先度 |
|---|------|---------|------|-----------|------|--------|
| 1 | alex-bash-impl | Alex に Bash ツールを付与する | Riku | S | なし | P0 |
| 2 | alex-bash-qa | Alex Bash 付与の動作確認・QA | Sora | S | #1 | P0 |
| 3 | token-opt-design | トークン最適化ルールの設計（pm.md 反映方針） | Alex | M | なし | P1 |
| 4 | token-opt-impl | pm.md および各エージェント定義への最適化ルール反映 | Riku | M | #3 | P1 |
| 5 | token-opt-qa | トークン最適化反映の QA | Sora | S | #4 | P1 |
| 6 | session-interrupt-design | セッション中断タスク検出機構の設計 | Alex | M | なし | P2 |

---

## タスク詳細

### タスク 1: alex-bash-impl

**目的**: architect.md の `tools:` に `Bash` を追加し、Alex が queue.sh を自己実行できるようにする。

**対象ファイル**: `.claude/agents/architect.md`

**変更内容**:
```
tools: Read, Write, Glob, Grep
↓
tools: Read, Write, Glob, Grep, Bash
```

また、architect.md の本文に以下のルールを追記する:
- `queue.sh` の操作（`start`, `done`, `handoff`, `block`）は **自己実行を基本とする**
- Bash 実行は 1 タスクあたり最大 5 回を目安とする（ADR-004 に準拠）
- `git push` などネットワーク依存コマンドは Yuki へ委譲する

**完了条件**:
- architect.md の tools 行に Bash が含まれている
- Bash 使用ルールが architect.md に記載されている

---

### タスク 2: alex-bash-qa

**目的**: タスク 1 の変更内容を Sora がレビューし、問題がないことを確認する。

**確認ポイント**:
- tools 行の記法が他エージェント定義と一致している
- 追記した Bash ルールが ADR-004 と矛盾していない
- architect.md の既存内容を壊していない

**完了条件**: Sora が APPROVED を返す

---

### タスク 3: token-opt-design

**目的**: ADR-004 の決定事項を pm.md と各エージェント定義に反映するための具体的な変更方針を設計書としてまとめる。

**参照ファイル**:
- `docs/adr/token-optimization-adr.md`
- `.claude/agents/pm.md`（現状把握）

**成果物**: `docs/spec/token-opt-design.md`

**設計書に含める内容**:
1. pm.md に追記する「委譲判断フロー」（親で処理 vs サブエージェント委譲の基準）
2. 各エージェント定義に追記する「Bash 実行上限ルール」の文言
3. complexity 別トークン見積もり表の記載先（pm.md or CLAUDE.md）
4. レート制限到達時のリカバリ手順の記載先

**完了条件**: 設計書ファイルが存在し、上記 4 点が記載されている

---

### タスク 4: token-opt-impl

**目的**: タスク 3 の設計書に基づき、pm.md および Riku（engineer）定義への実際の変更を実施する。

**対象ファイル**:
- `.claude/agents/pm.md`（委譲判断フロー、レート制限対応手順）
- `.claude/agents/qa.md`（Bash 実行上限ルール）
- `.claude/agents/engineer-go.md`（Bash 実行上限ルール）
- `.claude/agents/engineer-next.md`（Bash 実行上限ルール）

**完了条件**:
- 設計書の 4 点が各ファイルに反映されている
- 既存の内容を不用意に削除していない

---

### タスク 5: token-opt-qa

**目的**: タスク 4 の変更内容を Sora がレビューする。

**確認ポイント**:
- pm.md の委譲判断フローが ADR-004 Section 1 と整合している
- 各エージェント定義の Bash 上限ルール（5 回）が統一されている
- 変更漏れがない

**完了条件**: Sora が APPROVED を返す

---

### タスク 6: session-interrupt-design

**目的**: セッション中断時にタスクが IN_PROGRESS のまま放置される問題（#39）を検出・通知する機構を設計する。

**参照ファイル**:
- `.claude/_queue.json`（現在のデータ構造）
- `scripts/queue.sh`（現在の実装）

**成果物**: `docs/spec/session-interrupt-design.md`

**設計書に含める内容**:
1. 「中断タスク」の定義（例: IN_PROGRESS かつ最終 start イベントから N 分以上経過）
2. 検出タイミング（queue.sh show 呼び出し時 / hook / 定期実行）
3. 通知先（Slack / STDOUT）と通知フォーマット
4. 自動リカバリの可否判断（リカバリ条件: token-optimization-adr.md に既定）
5. 実装の影響範囲（queue.sh の変更 or 別スクリプト）

**完了条件**: 設計書ファイルが存在し、上記 5 点が記載されている

---

## 実行順序と依存関係

```
[タスク 1: alex-bash-impl]  → [タスク 2: alex-bash-qa]
[タスク 3: token-opt-design] → [タスク 4: token-opt-impl] → [タスク 5: token-opt-qa]
[タスク 6: session-interrupt-design]  （独立）
```

タスク 1・3・6 はすべて独立して開始できる。
並列実行禁止ルール（scripts/queue.sh の flock 解禁前）に従い、直列実行とする。

**推奨実行順**: 1 → 2 → 3 → 4 → 5 → 6

理由: #43 の修正（タスク 1-2）を先に完了させることで、タスク 3 以降のAlexの
queue.sh 自己実行を検証できる。

---

## 担当エージェント別まとめ

| エージェント | タスク | 役割 |
|------------|--------|------|
| Riku（engineer） | #1, #4 | ファイル変更・実装 |
| Sora（QA） | #2, #5 | レビュー・品質確認 |
| Alex（architect） | #3, #6 | 設計書作成 |

---

## 完了条件（Quality Gate）

スプリント完了の判定基準:

1. 全 6 タスクの `status == "DONE"`
2. QA 対象タスク（#2, #5）の `qa_result == "APPROVED"`
3. 成果物ファイルの存在確認:
   - `.claude/agents/architect.md` に `Bash` が tools に含まれる
   - `docs/spec/token-opt-design.md` が存在する
   - `docs/spec/session-interrupt-design.md` が存在する
   - `.claude/agents/pm.md` に委譲判断フローが記載されている

---

## リスクと対策

| リスク | 確率 | 対策 |
|--------|------|------|
| タスク 3（Alex 設計）完了後に Alex が queue.sh done を自己実行できるかの検証がタスク 2 完了後になる | 中 | タスク 2 完了後に Alex に handoff し、自己実行を試みさせる |
| token-opt の変更がエージェントの既存プロンプトを壊す | 低 | Sora の QA で変更前後の diff を確認させる |
| session-interrupt-design が実装に影響するスコープ拡大 | 中 | Sprint-05 は設計のみ。実装は Sprint-06 以降へ |

---

## 見積もり

ADR-004 の見積もり式に基づく:

| タスク | complexity | 推定トークン |
|--------|-----------|------------|
| #1 alex-bash-impl | S | 15,000 |
| #2 alex-bash-qa | S | 15,000 |
| #3 token-opt-design | M | 40,000 |
| #4 token-opt-impl | M | 40,000 |
| #5 token-opt-qa | S | 15,000 |
| #6 session-interrupt-design | M | 40,000 |
| **合計（×1.5 バッファ）** | | **~233,000** |

合計推定 ~233,000 tokens（300,000 以下）のため 1 バッチで実行可能。

---

## 次スプリント候補（Sprint-06）

- session-interrupt-design の実装（#39）
- 定量ルーブリック自己評価（#22）
- リアルタイム品質シグナル _signals.jsonl 導入（#23）
- self-review チェックリスト効果測定の 2 スプリント目データ収集
