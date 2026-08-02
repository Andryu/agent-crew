# Sprint-26 計画書 — 組織の足腰: Enforcement実装とSDD仕様積層の制度化

- 作成: Yuki（PMオーケストレーター）
- ブランチ: `feat/sprint-26`（origin/main起点、チェックアウト済み）
- 前提: PR #136（Sprint-25）マージ済み。ダッシュボード実データ接続（`feature/dashboard-live`）は別セッション並走中でありスコープ重複なし。

---

## ゴール

組織憲章第3条の Enforcement「Kai定常スキャン」を「将来整備」から実運用へ移行し、Sprint-25 レトロで積み残した3件のIssue（#139/#140/#141）を解消する。あわせて、個人開発の規模に合わせた軽量な機能仕様書（1機能1ファイルの living document）運用を制度化し、実装完了時の更新をチェックリストで強制する。

---

## 事前チェック結果（pm.md ステップ0〜0.8）

- **ステップ0（ブランチ最新化）**: `feat/sprint-26` は `origin/main` と同期済み（`git fetch origin` 実施、差分なし）。
- **ステップ0.5（pm-learned-rules.md）**: 全件確認済み。今スプリントに反映したルールは「確認事項」節を参照。
- **ステップ0.6（経営会議判断）**: `docs/org/council/2026-08-01-queue.md` が最新。記載の3件（Sprint-25テーマ承認・レトロIssue一括承認・Phase2優先）はいずれも Sprint-25 向けの判断であり、Sprint-25 で反映済み。Sprint-26 向けの新規会議・判断事項は現時点でなし。
- **ステップ0.7（外部リポジトリ教訓）**: `_lessons.json` を機械チェックしたところ `source_repo: "agent-crew"` の3件が「外部由来」として検出されたが、`git remote get-url origin` の実値（`git@github.com:Andryu/agent-crew.git`）とのフォーマット不一致による誤検知と判明（`source_repo` はリポジトリ短縮名で記録されており、自リポジトリ由来）。該当3件（flock/mkdirロック関連）は既に Sprint-24/25 で `pm-learned-rules.md` に反映済み（`agent-crew-sprint-24-tooling-002` / `agent-crew-sprint-25-tooling-001`）。真の外部リポジトリ由来 lesson は現時点でなし。
- **ステップ0.8（docs/org/ 相互参照チェック）**: 全参照パス（`docs/org/templates/project-charter.md` / `docs/org/weekly-council.md` / `.claude/agents/coo.md` / `docs/adr/ADR-014-*.md` / `docs/org/constitution.md` / `docs/org/departments.md`）の実在を確認済み、破損リンクなし。
- **ステップ1（前スプリント実装完了状態の突合）**: Sprint-25 の9タスクは全件 `DONE`。設計→実装の対応漏れ・計画重複（elapsed<60秒のタスク）は検出されなかった。
- **ステップ2（DECISIONS.md / retro確認）**: `docs/DECISIONS.md` は sprint-16 で更新が途絶えており、以降の記録は `docs/sprints/sprint-XX-retro.md` に移行済み（運用実態として問題なし、当スプリントでの是正対象にはしない）。`docs/sprints/sprint-25-retro.md` の「次スプリントへの改善優先事項」4件をタスク化した（下記タスク一覧参照）。
- **ステップ2.5（フック権限事前登録）**: 新規スクリプト `scripts/audit-scan.sh` 用に `Bash(scripts/audit-scan.sh *)` を `.claude/settings.json` の `permissions.allow` へ追加済み。他の必要パターン（`scripts/queue.sh`・`scripts/sprint-points.sh`・`chmod`・`bash`・`Write(**)` 等）は Sprint-17/25 までに登録済みで不足なし。

---

## 確認事項

- [ ] pm-learned-rules.md 反映: 主要ルールを以下の通りタスク設計へ反映した。
  - `agent-crew-sprint-25-planning-001`（負荷分散はポイントベース公式）: 本計画書のスコア判定に適用済み（下記参照）。
  - `agent-crew-sprint-23-planning-001`（Riku比率50%超は再配分検討）: Riku担当比率は10pt/28pt=35.7%で基準未満、対応不要。
  - `agent-crew-sprint-11-reliability-001`（LタスクはRiku1件まで）: 今回Riku担当にLタスクなし（M×3+S×1）、対応不要。
  - `agent-crew-sprint-25-reliability-001`（symlink/配布系は自己参照ガード＋実機QA）: `sdd-templates-impl`（templates/department/への同梱）・`audit-scan-impl` に適用し、QAタスクの notes に実機実行検証を明記した。
  - `agent-crew-sprint-25-process-001`（queue.sh done即時実行）: Issue #139 として本スプリントのタスクに設定済み。
  - `agent-crew-sprint-13-process-001`（Issue着手条件の確認）: 対象なし（#139/#140/#141 いずれも前提条件の記載がない改善タスク）。
- [ ] 経営会議判断の反映: 対象なし（2026-08-01キューはSprint-25向け判断で反映済み、Sprint-26向け新規判断なし）。
- [ ] docs/org/ 相互参照チェック: 実施済み（問題なし、破損リンクなし）。
- [ ] 前スプリントの設計完了タスクとの突合: 実施済み（Sprint-25全9タスクDONE、計画重複なし）。
- [ ] 計画重複タスク: なし。
- [ ] DECISIONS.md 反映: sprint-25-retro の「次スプリントへの改善優先事項」4件（負荷分散境界値監視・queue.sh done再発防止・retro.md実行検証徹底・retro-stop-hookの実戦検証）を全てタスク化した。
- [ ] フック関連タスクの権限: 登録済み（`Bash(scripts/audit-scan.sh *)` を追加）。
- [x] **オーナー判断によるスコープ修正を反映済み**: Kiro式3点セット（requirements/design/tasks）の必須化は行わない方針に変更。個人開発の規模に合わせ、①1機能1ファイル（`docs/spec/<機能名>.md`）の living document 方式（テンプレートは「概要/ユースケース/仕様（現在の正）/変更履歴」の軽量構成）、②本体は更新を強制（Rikuの実装完了チェックリストに「変更した機能の仕様書を更新したか」を追加、Soraの QA チェックリストに「仕様書と実装の差分がないか」を追加）、③既存機能のうち仕様書が無い主要機能の初期作成は本スプリントでは対応せずバックログ化、の3方針で `sdd-adr-design`・`sdd-templates-impl`・`sdd-qa` を修正した。
- [x] **sdd-quality-loop-adr の実在確認（訂正）**: 前回「実在しない」と報告したが、team-lead確認により実在が判明。マスターワークツリー（`~/Workspace/agent-crew/docs/adr/` 等）に**未コミットのまま**置かれていた3文書（`docs/adr/sdd-quality-loop-adr.md`【Status: Proposed】/ `docs/spec/sdd-quality-loop-design.md` / `docs/spec/sdd-quality-loop-proposal.md`）で、team-leadが `feat/sprint-26` にコピー済み。内容は「Kiro 3点セット前提 + `/spec-postmortem` スキルによる品質改善還流ループ（postmortem→根因分析→テンプレ/agent定義への改善PR還流）」のADR/設計/提案書。**対応方針**: 新規ADR起票ではなく、この既存3文書を軽量機能仕様書方式（オーナー決定）に沿って改訂する。Contextの前提記述を「3点セット」から「`docs/spec/<機能名>.md` の軽量機能仕様書」に置き換え、Decision本体（postmortem→根因タクソノミー分類→改善diff提案→真実源リポへのPR還流という仕組み自体）は方式に関わらず有効なため維持する。Statusを Proposed→Accepted に変更し、旧3点セット前提の記述は削除せず「改訂履歴」セクションを新設して残す（`sdd-adr-design` タスクの notes 参照）。
- [x] **レトロ教訓候補（メモ）**: vaultのADR索引（`~/Workspace/Obsidian/decisions/agent-crew-adr-index.md`）が実態とズレていた。sdd-quality-loop-adr関連3文書がマスターワークツリーに未コミットのまま存在し、索引には記載があったがリポジトリ本体（origin/main）には未反映だった。索引と実体（未コミットファイル）の同期漏れが、今回の「実在しないと誤判定」の根因。`sprint26-retro` タスクの notes に記録済み、lesson化を検討する。

---

## タスク一覧

| # | slug | タスク | 担当 | 依存 | complexity | risk_level | qa_mode |
|---|------|--------|------|------|------------|------------|---------|
| 1 | sdd-adr-design | 既存3文書（ADR/design/proposal）を軽量機能仕様書方式に改訂・Accepted化 | Alex | なし | M | low | — |
| 2 | sdd-templates-impl | 機能仕様書テンプレート実装＋Riku/Soraチェックリスト追記 | Riku | #1 | M | low | inline |
| 3 | sdd-qa | 機能仕様書テンプレート・ADR整合性QA | Sora | #2 | S | low | — |
| 4 | audit-scan-design | Kai定常スキャン設計（憲章第3条Enforcement） | Alex | なし | M | medium | — |
| 5 | audit-scan-impl | audit-scan.sh実装＋Kai職務追記＋憲章第3条更新 | Riku | #4 | M | medium | inline |
| 6 | audit-scan-qa | audit-scan.sh実機実行QA | Sora | #5 | S | medium | — |
| 7 | subagent-stop-enforce-design | queue.sh done実行漏れ構造対策 設計（Issue #139） | Alex | なし | M | high | — |
| 8 | subagent-stop-enforce-impl | queue.sh done実行漏れ構造対策 実装（Issue #139） | Riku | #7 | M | high | inline |
| 9 | subagent-stop-enforce-qa | queue.sh done強制フックQA（Issue #139） | Sora | #8 | S | high | — |
| 10 | loadbalance-formula-doc | 負荷分散ポイントベース公式化の反映（Issue #140） | Riku | なし | S | low | inline |
| 11 | verify-query-rule-doc | 検証クエリ実行検証必須化ルール明文化（Issue #141） | Alex | なし | S | low | inline |
| 12 | retro-stop-hook-live-check | enforce-retro-stop.sh実戦検証をレトロ完了条件に組込み | みゆきち | なし | S | low | inline |
| 13 | sprint26-qa | Sprint-26横断QA（複数文書整合性・憲章相互参照） | Sora | #3,#6,#9,#10,#12 | M | medium | — |
| 14 | sprint26-retro | Sprint-26レトロスペクティブ | みゆきち | #13 | S | low | — |

> **合計ポイント: 28 pt**（S×7件=7pt + M×7件=21pt）※ `scripts/sprint-points.sh --md` による機械検算済み。

### 負荷分散スコア（ポイントベース・公式指標）

| 担当 | タスク数 | ポイント |
|------|---------|---------|
| Alex | 4 | 10 |
| Riku | 4 | 10 |
| Sora | 4 | 6 |
| みゆきち | 2 | 2 |

- 負荷分散スコア（ポイントベース・公式）= 最多10pt / 平均7pt = **1.43**（基準 <=2.0、PASS）
- 負荷分散スコア（タスク数ベース・補助）= 最多4件 / 平均3.5件 = **1.14**（参考）
- Riku担当比率 = 10pt / 28pt = 35.7%（基準50%未満、再配分不要）
- Riku担当タスクはM×3・S×1のみでLタスクなし（Lタスク1件上限ルールに抵触なし）

---

## トークン消費見積もり（ADR-004 Section 4準拠）

| complexity | 件数 | 単価 | 小計 |
|-----------|------|------|------|
| M | 7 | 40,000 | 280,000 |
| S | 7 | 15,000 | 105,000 |

推定合計 = 385,000 × 1.5（バッファ）= **577,500 tokens**。300,000tokensを超えるため2バッチ以上に分割する。

### バッチ分割案

1. **バッチ1（設計）**: Alex担当4件（#1, #4, #7, #11）を並列実施
2. **バッチ2（実装）**: Riku担当4件（#2, #5, #8, #10）を対応する設計完了後に並列実施
3. **バッチ3（QA）**: Sora担当のinline QA 3件（#3, #6, #9）＋みゆきち担当（#12）を並列実施
4. **バッチ4（最終統合）**: sprint26-qa（#13）→ sprint26-retro（#14）

各バッチ間は30分以上の間隔を推奨（pm-estimation.md基準）。

---

## 並列化できるもの

- タスク #1・#4・#7・#11（Alex担当の設計4件）は相互に依存がなく同時に進められる。
- タスク #2・#5・#8・#10（Riku担当の実装、対応する設計完了後）は相互依存がなく並列可能。ただしengineer-go委譲前チェックリスト（1指示あたり2,000トークン以下・参照ファイル3件以下）を厳守し、1バッチあたりの起動数上限3〜4件に収める。
- タスク #3・#6・#9・#12（QA・レトロ準備）は対応する実装完了後、相互に依存なく並列可能。

---

## 実装時の注意事項（委譲前チェックリスト適用）

- Riku担当の各実装タスクは M(3pt) 止まりで L への該当なし。ただし `subagent-stop-enforce-impl`（risk_level: high）は過去に2回連続再発したパターンの恒久対策であるため、委譲指示は「既存hookへの差分」に絞り込み、`subagent_stop.sh`・`task_completed.sh` 全文を丸ごと渡さないこと。
- `audit-scan-impl` と `sdd-templates-impl` はいずれもファイル配布・テンプレート同梱を伴うため、`agent-crew-sprint-25-reliability-001` に基づき自己参照ガード・上書き防止の実装要否をAlex設計段階で判定し、該当する場合はQAで実機実行検証を必須とする。
- `subagent-stop-enforce-design` の成果物（設計書）に含まれるBashコードサンプルは `bash -n` でのバリデーションを行うこと（`agent-crew-sprint-08-tooling-001`）。

---

## 完了条件

- 全14タスクが `DONE`、QA対象6タスク（#3, #6, #9, #13、および #2/#5/#8/#10のinline QA）が `APPROVED` または `APPROVED_WITH_NOTE`。
- `docs/org/constitution.md` 第3条の「将来整備」注記が解除され、実際の運用方法に置換されている。
- Issue #139・#140・#141 がクローズ可能な状態になっている。
- `sprint26-retro`（みゆきち）完了後、`enforce-retro-stop.sh` の実戦検証結果（警告が実際に出力されたか）がレトロ文書に記録されている。

実装は開始していません。上記計画のご確認をお願いします。
