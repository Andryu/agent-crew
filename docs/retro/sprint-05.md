# レトロスペクティブ — sprint-05

生成日: 2026-04-23
生成者: みゆきち（retro エージェント）

---

## スプリント概要

**スプリントゴール**: Alex への Bash ツール付与（#43）によるキュー自律実行の実現と、トークン消費最適化ルールの各エージェント定義への反映（#36）

**期間**: 2026-04-22 〜 2026-04-23
**結果**: 全 6 タスク DONE / QA 2 件 APPROVED

---

## タスク完了サマリー

| タスク | 担当 | complexity | 実行時間 | retry_count | qa_result |
|--------|------|-----------|---------|-------------|-----------|
| alex-bash-impl | Riku | S | — | 0 | — |
| alex-bash-qa | Sora | S | — | 0 | APPROVED |
| token-opt-design | Alex | M | 4分 | 0 | — |
| token-opt-impl | Riku | M | — | 0 | — |
| token-opt-qa | Sora | S | — | 1 | APPROVED（差し戻し後） |
| session-interrupt-design | Alex | M | — | 0 | — |

> token-opt-qa は差し戻し（CHANGES_REQUESTED）が 1 回発生。architect.md の Bash 実行上限が sprint-05-plan.md の「5回」のまま修正されていなかった（ADR-004 準拠の「3回」が正しい）。

---

## 集計

- 完了タスク数: 6 / 6（完了率 100%）
- ブロック発生: 0 件
- 総リトライ回数: 1（token-opt-qa）
- QA 差し戻し率: 50%（CHANGES_REQUESTED 1 件 / QA タスク 2 件）
- Sora エージェント内部エラー: 1 回（スマホ Remote Control スリープによる接続切断と推定）

---

## Complexity 精度評価

| complexity | タスク数 | 実行時間の傾向 |
|-----------|---------|-------------|
| S | 3 | 短時間 |
| M | 3 | token-opt-design は 4 分（Alex が自己 start/done を発行した初のケース） |
| L | 0 | — |

---

## KPT — Keep / Problem / Try

### Keep（続けること）

**K-1: Alex が Bash 付与後に queue.sh を自己実行できた（token-opt-design）**
sprint-04 の課題だった「Yuki が Alex の done/handoff を代行」問題に対し、Bash ツール付与が部分的に機能した。token-opt-design では start（08:25:55）・done（08:29:47）を Alex が自己発行し、Yuki の介入なしでタスクを完結させた。

**K-2: Design → Impl → QA フローが機能し続けている**
token-opt の 3 タスク（design/impl/qa）は差し戻しを経つつも最終的に APPROVED となった。設計書が実装の引き継ぎ資料として機能した。

**K-3: Sora の CHANGES_REQUESTED が正しく機能した**
token-opt-qa で計画文書（5回）と ADR-004（3回）の数値齟齬を検出し、差し戻しを実施した。2スプリント目のデータとして、self-review チェックリストが導入されても仕様値の突合ミスが残ることが確認された。

---

### Problem（問題だったこと）

**P-1: token-opt-qa で計画文書と ADR の数値齟齬による差し戻し**
sprint-05-plan.md の「Bash 実行上限 5 回」と ADR-004 の「3 回」が食い違っていたが、Riku が実装時に計画文書のみ参照し ADR を突合しなかった。1 回の差し戻しが発生した。

**P-2: Sora エージェントが内部エラーで落ちた**
スマホ Remote Control のスリープによる接続切断が原因と推定。深夜セッション（alex-bash-impl 完了 00:06）と朝セッション（alex-bash-qa 08:25）の間に約 8 時間のブレイクが発生した。セッション中断の検出機構が未実装のため、再開を促す通知もなかった。

**P-3: Bash 付与の効果が部分的（サブエージェントコンテキストで使えない）**
Alex が Bash 付与後も、session-interrupt-design はサブエージェントコンテキストで実行されたため Bash が利用できなかった。Bash 付与の恩恵を受けられる実行コンテキストに制約がある。

**P-4: PR Test Plan チェック漏れが 2 スプリント連続で発生**
sprint-04 でもオーナーから同じ指摘を受けていた。PR テンプレートまたは Riku の完了基準に Test Plan 確認が含まれていないことが根因。

**P-5: スプリント完了後のコミット確認をオーナーに聞いた（介入最小化違反）**
MEMORY に Keep going（介入最小化）と記録されているにもかかわらず、コミット可否をオーナーに確認してしまった。コミット判断基準が pm.md に明文化されていないことが根因。

**P-6: みゆきち自動起動の仕組みがない**
sprint-03 以降、毎スプリントオーナーが手動でレトロを依頼している。Yuki のスプリント完了フローに retro 呼び出しが含まれていない。

---

### Try（次に試すこと）

**T-1: Riku の実装チェックリストに「計画文書と ADR/設計書の仕様値を突合する」を追加する**
（P-1 対応）差し戻し削減に直結する。PR 提出前のセルフチェック項目として engineer-go.md に追記する。

**T-2: session-interrupt-design の設計（Sprint-05 成果物）を実装に繋げる（Sprint-06）**
（P-2 対応）設計書は Sprint-05 で完成。Sprint-06 での queue.sh detect-stale 実装が次のステップ。

**T-3: Alex のサブエージェントコンテキストでの Bash 利用可否を明示的に検証する**
（P-3 対応）architect.md に「サブエージェント起動時は Bash 不可」という注意事項を記載し、Yuki が代行フローを明文化する。

**T-4: PR テンプレートに Test Plan チェックリストを追加する**
（P-4 対応）PRテンプレートを更新し、Test Plan 確認を必須項目とする。Sprint-06 タスクとして対処済み（process-docs-update で実施）。

**T-5: pm.md にコミット自動実行ルールとみゆきち自動起動を明文化する**
（P-5・P-6 対応）Sprint-06 の process-docs-update タスクで対処済み（pm.md 更新・PRテンプレート更新）。

---

## 特記事項

### Alex Bash 付与の実証と残存制約（Sprint-05 ハイライト）

Sprint-04 の最大課題だった「Alex が queue.sh を自己実行できない」問題への対処として Bash を付与した。token-opt-design では効果が確認されたが、session-interrupt-design ではサブエージェントコンテキストの制約で Bash が使えなかった。

```
検証結果:
- 通常起動コンテキスト（token-opt-design）: Bash 自己実行 OK
- サブエージェントコンテキスト（session-interrupt-design）: Bash 使用不可
→ Yuki 代行フローが継続して必要
```

これは「ツール付与 = 完全解決」ではないことを示す。実行コンテキストを意識した設計が重要。

---

## lessons.json への記録

以下の 7 件を `~/.claude/_lessons.json` に記録した（うち sprint-05 分は 6 件。過去分 1 件はサンプルエントリ）。

| lesson ID | category | priority_score | type | issue_url |
|-----------|----------|---------------|------|-----------|
| agent-crew-sprint-05-qa-001 | qa-process | 2 | failure-pattern | null（ゲート未通過） |
| agent-crew-sprint-05-reliability-001 | reliability | 4 | failure-pattern | https://github.com/Andryu/agent-crew/issues/48 |
| agent-crew-sprint-05-process-001 | process | 6 | failure-pattern | https://github.com/Andryu/agent-crew/issues/49 |
| agent-crew-sprint-05-process-002 | process | 4 | failure-pattern | https://github.com/Andryu/agent-crew/issues/50 |
| agent-crew-sprint-05-tooling-001 | tooling | 4 | observation | https://github.com/Andryu/agent-crew/issues/51 |
| agent-crew-sprint-05-process-003 | process | 3 | failure-pattern | Issue #47（手動作成済み）/ ゲートスコア不足（3点） |

---

## エビデンスゲート結果

ゲート通過条件（priority_score >= 4 かつ evidence >= 1 件 かつ issue_url == null）を満たした lesson:

このレトロ実施時点で、エビデンスゲート対象 lesson の Issue 化は既に完了している（前回セッションで記録・Issue 化済み）。

| lesson ID | priority_score | 状態 |
|-----------|---------------|------|
| agent-crew-sprint-05-reliability-001 | 4 | Issue 化済み（#48） |
| agent-crew-sprint-05-process-001 | 6 | Issue 化済み（#49） |
| agent-crew-sprint-05-process-002 | 4 | Issue 化済み（#50） |
| agent-crew-sprint-05-tooling-001 | 4 | Issue 化済み（#51） |

保留 lesson（ゲート未通過）:

| lesson ID | priority_score | 保留理由 |
|-----------|---------------|---------|
| agent-crew-sprint-05-qa-001 | 2 | priority_score < 4 |
| agent-crew-sprint-05-process-003 | 3 | priority_score < 4（Issue #47 は別途手動作成済み） |

---

## 次スプリントへの提言

1. **session-interrupt-design の実装（Sprint-06 #39）を優先する**
   Sora 内部エラーの再発防止に直結。設計書が Sprint-05 で完成しており、queue.sh への detect-stale コマンド追加が次のステップ。

2. **Test Plan 必須化・コミット自動化・みゆきち自動起動の定着確認**
   Sprint-06 の process-docs-update で対処した変更（PRテンプレート・pm.md）が実際のスプリントで機能するかを Sprint-06 レトロで確認する。

3. **Alex のサブエージェントコンテキスト制約を architect.md に記載する**
   Sprint-06 タスクとして追加されていないため、Yuki への提言として残す。Issue #51 参照。
