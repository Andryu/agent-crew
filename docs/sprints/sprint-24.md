# Sprint-24 計画書

**期間**: 2026-08-01〜
**ブランチ**: feature/my-company
**ゴール**: 「組織OS Phase 1 — 本社機能と部門の分離」。CEO=オーナー、参謀長(COO)エージェント「Rin」新設、組織憲章・部門ポートフォリオ・プロジェクト憲章テンプレート・週次経営会議プロトコル・本社/部門分離ADR・部門別トークン週次集計スクリプトを整備する。

> **更新**: タスク #1 org-constitution・#4 project-charter-template・#6 coo-persona・#7 weekly-council-protocol は、計画立案と並行してFable（メインセッション）が完了済み。#2 token-report-script（Ren）・#3 org-departments（Alex）・#5 adr-014-separation（Alex）も完了済み。成果物: `docs/org/constitution.md` / `docs/org/templates/project-charter.md` / `.claude/agents/coo.md` / `docs/org/weekly-council.md` / `scripts/token-report.py` / `docs/org/departments.md` / `docs/adr/ADR-014-headquarters-department-separation.md`（いずれも実在確認済み）。残タスクは #8 sprint24-qa（Sora）・#9 sprint24-retro（みゆきち）の2件。

---

## スプリント前チェック結果

- [x] 前スプリントの設計完了タスクとの突合: Sprint-23 全7タスク DONE（QA APPROVED）。Sprint-23 の積み残しは Sprint-22 レトロ補完のみで、本スプリントのスコープ（組織OS）とは独立。重複なし。
- [x] 計画重複タスク: なし。`docs/org/`・`.claude/agents/coo.md`・`scripts/token-report.py` はいずれも新規作成で、既存ファイルとの重複なし（事前に `ls docs/org` `ls .claude/agents` で存在しないことを確認済み）。
- [x] DECISIONS.md 反映: Sprint-23 エントリまで確認。ADR 番号は `ADR-013`（グローバル学習ログ）まで採番済みのため、本スプリントの ADR は `ADR-014` を採番する。
- [x] フック関連タスクの権限: 本スプリントにフック実装タスクはなし（対象外）。ただし新規 `scripts/token-report.py` の実行検証に `Bash(python3 *)` が必要と判断し、スプリント開始前に `.claude/settings.json` の `permissions.allow` へ `Bash(python3 *)` と `Bash(scripts/token-report.py *)` を相対パス形式で追記済み（`agent-crew-sprint-15-tooling-001`・`agent-crew-sprint-17-tooling-001` 準拠）。
- [x] Riku 担当 L タスク: 0件（本スプリントに Riku 担当タスクなし。制限 1件/sprint に適合）。
- [x] pm-learned-rules.md 反映:
  - `agent-crew-sprint-23-planning-001`（priority:6, 負荷分散スコア事前計算）→ 担当ドラフト後に負荷分散スコアを計算した。4タスクをFableが計画外で先行完了したため残タスクの分布が変わったが、再計算後も基準内（下記「担当者負荷分散」節参照）。
  - `agent-crew-sprint-22-process-001`（priority:6, レトロ未実施の再発）→ `sprint24-retro` タスクを `_queue.json` に明示登録し、「完了条件」に「みゆきちによるレトロ完了」を Definition of Done として明記した（Sora の埋め込みルールに依存しきらず、キュー上でも可視化する二重の担保）。
  - `agent-crew-sprint-09-process-001`（priority:9, engineer-go 委譲前トークン推定）→ 各タスクの参照ファイルを1〜2件に絞り、委譲指示を2,000トークン以下に抑える設計とした（下記「タスク詳細」参照）。
  - `agent-crew-sprint-13-process-001`（priority:6, Issue着手条件確認）→ 本スプリントは Issue 起点ではなくオーナー承認済みの直接指示のため対象外（着手条件はオーナーメッセージ本文に既に明記されている「オーナー承認済み・即実行フェーズ」を根拠として採用）。
  - `agent-crew-sprint-08-tooling-001`（priority:9, Bashサンプルは bash -n 検証）→ `scripts/token-report.py` は Python のためこのルール自体は非該当。ただし同種のリスク（サイレント失敗）を避けるため、Ren のタスクに「実データでの実行テスト必須」を明記した。
- [x] 外部リポジトリ global 教訓: `~/.claude/_lessons.json` に agent-crew 以外由来の未処理 global 教訓なし（対象なし）。

### `agent-crew-failure-patterns.md` の再発パターンへの対策

- **「学びが記録されるが想起されない」**: `docs/org/weekly-council.md`（Fable完了済み）に、会議冒頭で `pm-learned-rules.md` と `_lessons.json` の高優先度教訓を確認するステップ（教訓レビュー: 45-50分）を含めた。`.claude/agents/coo.md`（Rin）の行動原則にも「教訓に該当する再発パターンがあればキューに⚠付きで想起させる」を明記済み。
- **「ドキュメントだけでは強制できない」**: レトロスキップの根本対策（Stopフックによる強制）は本スプリントのスコープ外（組織OS設計が主眼）だが、`sprint24-retro` をキュー登録し「完了条件」に明記することで運用面の二重担保とした。フックによる強制自体は「次スプリント候補」に別Issueとして起票することを推奨する（team-lead 合意済み）。

---

## タスク一覧

| # | slug | タイトル | 担当 | 状態 | 依存 | complexity | risk_level | qa_mode |
|---|------|----------|------|------|------|------------|------------|---------|
| 1 | org-constitution | 組織憲章v1（4条: 自動化レベル表/承認ゲート/最小権限/撤退基準） | Fable | **DONE** | なし | M | medium | — |
| 2 | token-report-script | 部門別トークン週次集計スクリプト (`scripts/token-report.py`) | Ren | **DONE** | なし | M | medium | inline |
| 3 | org-departments | 部門ポートフォリオ定義（モード定義・横展開トリガー） | Alex | **DONE** | #1 | M | low | — |
| 4 | project-charter-template | プロジェクト憲章テンプレート | Fable | **DONE** | #1 | S | low | inline |
| 5 | adr-014-separation | ADR-014: 本社機能/部門機能の分離設計 | Alex | **DONE** | #3 | M | medium | — |
| 6 | coo-persona | 参謀長エージェント新設（`.claude/agents/coo.md`, 名前「Rin」） | Fable | **DONE** | #1 #5 | M | medium | inline |
| 7 | weekly-council-protocol | 週次経営会議プロトコル（意思決定キュー形式含む） | Fable | **DONE** | #6 | M | medium | inline |
| 8 | sprint24-qa | Sprint-24 最終QA | Sora | READY_FOR_SORA | #2 #3 #4 #5 #6 #7 | S | low | — |
| 9 | sprint24-retro | Sprint-24 レトロスペクティブ実施（みゆきち） | みゆきち | TODO（#8待ち） | #8 | S | low | — |

> **合計ポイント: 21 pt**（S×3=3 + M×6=18 → 21pt。内訳: complexity M=3pt/S=1pt換算で、Mタスク6件は#1・#2・#3・#5・#6・#7、Sタスク3件は#4・#8・#9）。
>
> うちFableが計画立案と並行して完了したのは #1・#4・#6・#7（M×3 + S×1 = 9+1 = **10pt**分）。Alex・Renが完了した #2・#3・#5（M×3 = **9pt**分）と合わせ、実装系タスクは合計19pt完了済み。残ポイントは #8・#9（S×2 = **2pt**）のみ。

> 補足: #5（adr-014-separation）は本来 #3（org-departments）完了後に着手する設計だが、#6（coo-persona）はFableが#5完了前に先行完了している。Fableは本社/部門分離の設計判断をcoo.md作成時に自ら内包して解決したため実務上の矛盾はなく、#5完了後にAlexがcoo.mdとの整合性確認を実施済み（下記「タスク詳細」参照）。

### 担当者負荷分散（`agent-crew-sprint-23-planning-001` 対応）

計画時点（オリジナル）の分布:

| 担当 | タスク数 |
|------|---------|
| Alex | 3 |
| Riku | 3 |
| Ren | 1 |
| Sora | 1 |
| みゆきち | 1 |

平均1.8・最多3・スコア1.67で基準内だった（承認前の計画立案時点）。

**実行時点（Fableが4タスクを計画外で先行完了した後）の残タスク分布**:

| 担当 | 残タスク数 |
|------|-----------|
| Alex | 2（org-departments, adr-014-separation） — 完了済み |
| Ren | 1（token-report-script） — 完了済み |
| Sora | 1（sprint24-qa） |
| みゆきち | 1（sprint24-retro） |
| Riku | 0（当初予定の3タスクがすべてFableに先行完了されたため担当タスクなし） |

残タスク平均 = 5タスク / 4エージェント（稼働中） = 1.25。最多担当数 = 2（Alex）。
**負荷分散スコア = 2 / 1.25 = 1.6**（基準 <=2.0 に適合）。Riku は本スプリントで稼働なしだが、これは負荷の偏りではなく計画外の先行完了によるものであり、次スプリント計画時に「Rikuへの割当がなかった」ことを埋め合わせで過剰配分する必要はない。

### Riku 担当 L タスク確認

Riku 担当タスク: なし（本スプリントで稼働なし）
L タスク件数: **0件**（制限 1件/sprint に適合）

---

## 並列化

- **phase-1（並列実行済み）**: `token-report-script`（Ren, 依存なし）と `org-departments`（Alex, #1はDONE済みのため着手可）は異なる担当のため同時に進められ、両方完了済み。
- **phase-2（完了）**: `adr-014-separation` は #3（org-departments）完了後、Alexが引き続き着手し完了。
- **phase-3**: `sprint24-qa`（Sora）は実装系タスク全件（#1〜#7）完了後に着手。QA対象には既にDONEの全7タスクを含める（Fable・Alex・Ren各成果物の最終検証）。
- **phase-4**: `sprint24-retro`（みゆきち）は QA 完了後、Sora の完了報告に `@retro` を含めて自動起動（`agent-crew-sprint-11-process-001` 準拠）。

---

## タスク詳細と着手条件

### org-constitution（DONE — Fable）
- 成果物: `docs/org/constitution.md`（62行）。第1条自動化レベル(L0-L3)・第2条承認ゲート・第3条最小権限・第4条撤退基準、各条にEnforcement併記。内容確認済み。

### token-report-script（DONE — Ren）
- 成果物: `scripts/token-report.py`（316行）。`~/.claude/projects/<encoded-path>/*.jsonl` を走査し部門（リポジトリ）別に週次トークン消費を集計。team-leadより動作確認済みと報告あり。実データでの実行結果はSora QAで最終確認する。
- 参照データ構造: 各行JSONの `message.usage` に `input_tokens`/`output_tokens`/`cache_creation_input_tokens`/`cache_read_input_tokens`を含む。`timestamp`・`cwd`フィールドあり。部門マッピングは「agent-crew系=プロダクト部門固定+他は未分類」の簡易実装。

### org-departments（DONE — Alex）
- 成果物: `docs/org/departments.md`（94行）。部門ポートフォリオ定義（プロダクト=アクティブ/投資=アイドル/動画・ゲーム=未開設）とモード遷移条件、横展開トリガーを記載。

### project-charter-template（DONE — Fable）
- 成果物: `docs/org/templates/project-charter.md`（44行）。MVP定義/成功指標(数値3つまで)/撤退基準/期限の4項目 + Go/No-Go提出前チェックリスト（差別化検証項目含む）。内容確認済み。

### adr-014-separation（DONE — Alex）
- 成果物: `docs/adr/ADR-014-headquarters-department-separation.md`（129行）。本社機能（Yuki/Rin/`docs/org/`）と部門機能（既存agent-crewの各エージェント）の分離、組織OSテンプレート化→複製方式の技術的実現方法を含む。
- **追加スコープ対応**: `.claude/agents/coo.md`（Fableが先行完了）との整合性確認を含めて実施済み。coo.mdの「Yukiとの役割分担表」とADR-014の分離設計に矛盾がないかはSora QAで最終確認する。

### coo-persona（DONE — Fable）
- 成果物: `.claude/agents/coo.md`（69行）。「Rin」ペルソナ定義。責務: 意思決定キュー生成・部門状態ボード・トークン会計・横展開トリガー監視・経営会議進行・憲章の門番。Yukiとの役割分担表（視座/対面相手/成果物/やらないこと）で指揮・実装をしないことを明記済み。内容確認済み。

### weekly-council-protocol（DONE — Fable）
- 成果物: `docs/org/weekly-council.md`（43行）。60分議事次第、判断はキューのものだけ・保留2回まで等のルール、教訓想起ステップ・会議不成立条件（横展開トリガー②判定基準）を明記済み。内容確認済み。

### sprint24-qa（READY_FOR_SORA）
- 目的: 実装系タスク全7件（org-constitution・token-report-script・org-departments・project-charter-template・adr-014-separation・coo-persona・weekly-council-protocol）を対象に最終QA。
- 確認項目:
  - `scripts/token-report.py` は実データでの実行結果を確認する（Bash不可の場合は `CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）`、`agent-crew-sprint-11-reliability-002` 準拠）
  - `coo.md`（Rin）と `pm.md`（Yuki）の役割重複記述がないか確認する
  - ADR-014 と coo.md の整合性（上記「追加スコープ対応」）が確認されているか
  - 本計画書のポイント集計（合計21pt）に算数不整合がないか
- 着手条件: なし（全実装タスク完了済み、即着手可）

### sprint24-retro
- 目的: みゆきちによるスプリント振り返り。`_lessons.json` への記録、`pm-learned-rules.md` 更新（priority_score>=3のみ、フィルタ確認必須）、Issue化（`issue_url` 重複チェック必須）。
- 着手条件: sprint24-qa 完了後。Sora の完了報告に `@retro` を含めて即起動（オーナー確認不要）。
- レトロで必ず記録すべき観察: 「計画立案と並行してメインセッションが4タスクを先行完了した」ことによる計画とのズレ・良かった点/改善点（並行作業の是非・キュー更新の手戻りコスト等）、および計画書のポイント集計に算数ミスがあった点（QA MINOR指摘）。

---

## 変更ファイル予定

| ファイル | 変更種別 |
|---------|---------|
| `.claude/settings.json` | permissions.allow に `Bash(python3 *)`・`Bash(scripts/token-report.py *)` 追記（完了済み） |
| `docs/org/constitution.md` | 新規作成（完了済み） |
| `docs/org/departments.md` | 新規作成（完了済み） |
| `docs/org/templates/project-charter.md` | 新規作成（完了済み） |
| `docs/org/weekly-council.md` | 新規作成（完了済み） |
| `docs/adr/ADR-014-headquarters-department-separation.md` | 新規作成（完了済み） |
| `.claude/agents/coo.md` | 新規作成（Rin、完了済み） |
| `scripts/token-report.py` | 新規作成（完了済み） |
| `.claude/_queue.json` | Sprint-24 タスク状態記録（更新済み） |
| `docs/sprints/sprint-24.md` | 本ファイル |
| `docs/DECISIONS.md` | Sprint-23・Sprint-24 エントリ追記 |
| `~/.claude/_lessons.json` | Sprint-24 lesson 追記（レトロ時） |
| `.claude/agents/pm-learned-rules.md` | Sprint-24 lesson 反映（priority_score>=3のみ、レトロ時） |

---

## 完了条件

- [x] `docs/org/constitution.md` が4条構成（自動化レベル表/承認ゲート/最小権限/撤退基準）で作成されている
- [x] `docs/org/departments.md` にモード定義・横展開トリガー3条件が明記されている
- [x] `docs/adr/ADR-014-headquarters-department-separation.md` が作成されている
- [x] `.claude/agents/coo.md`（Rin）にYukiとの役割分担が明記されている
- [x] `docs/org/templates/project-charter.md` にMVP定義・数値成功指標・撤退基準・期限の4項目が含まれている
- [x] `docs/org/weekly-council.md` に意思決定キュー形式と教訓確認ステップが含まれている
- [x] `scripts/token-report.py` が新規作成され、team-leadより動作確認済みと報告あり（実データでの実行結果はSora QAで最終確認する）
- [ ] Sora QA: APPROVED（または APPROVED_WITH_NOTE の場合、NOTE内容を本完了条件に追加し実施確認する）
- [ ] **みゆきちによるレトロスペクティブ完了**（`agent-crew-sprint-22-process-001` 対応。Definition of Done に明示）

---

## トークン消費見積もり

Fable・Alex・Ren完了分（#1〜#7）は既に消費済みのため、本見積もりは残タスク（#8・#9）のみを対象とする。

| タスク | complexity | 推定トークン |
|--------|------------|------------|
| sprint24-qa | S | 15,000 |
| sprint24-retro | S | 15,000 |

推定合計 = (15,000 × 2) × 1.5 = **45,000 tokens**

300,000 tokens 未満 → **1バッチで処理可能**（`pm-estimation.md` 準拠。当初計画時点の427,500トークン見積もりは、実装系タスク全件が既に完了したことで解消された）。

---

## 次スプリント候補

- **レトロ強制のStopフック化（別Issue起票）**: `agent-crew-failure-patterns.md` の「2. レトロスペクティブのスキップが再発する」（ドキュメントだけでは強制できない）への恒久対策。`_queue.json` へのキュー登録と完了条件への明記だけでは構造的強制にならないため、Stopフックまたは同等の機構による強制実行を次スプリント以降の候補としてIssue化する（team-lead合意済み）。
- ADR-014完了後、`coo.md`・`departments.md`・`constitution.md`間の相互参照リンクが正しく張られているか（Fable先行完了分とAlex実装分の間で参照切れがないか）の横断チェックを次スプリント冒頭のチェックリストに追加することを推奨する。
- 計画書のポイント集計（S/M/L換算）はタスク数が多いスプリントで手計算ミスが起きやすい（本スプリントでQA MINOR指摘）。次スプリント以降、`jq`でタスク一覧のcomplexityを機械集計してから計画書に転記する運用を検討する。

---

## 確認事項

- [x] pm-learned-rules.md 反映: 上記「スプリント前チェック結果」参照。特に `agent-crew-sprint-23-planning-001`（負荷分散）と `agent-crew-sprint-22-process-001`（レトロ未実施再発）を反映済み。
- [x] レトロスキップの根本対策（Stopフックによる強制実行）は本スプリントのスコープ外。「次スプリント候補」に別Issue起票の推奨を明記済み（team-lead合意）。
- [ ] `coo.md`（Rin）と `pm.md`（Yuki）の役割重複リスク: coo.md本文に役割分担表が既に明記されているが、QA（Sora）で最終確認する。
- [x] 部門マッピング（リポジトリ→部門）の厳密な定義は投資・動画部門の発足まで不要と判断し、`token-report-script` では「プロダクト部門固定+未分類」の簡易実装にとどめる。将来の部門追加時に拡張する前提。
- [x] Fable・Alex・Renによる実装系タスク7件の完了を `_queue.json`・本計画書に反映済み（team-lead指示対応）。
- [x] ポイント集計の算数不整合をQA MINOR指摘に基づき修正済み（合計21pt、内訳を本文に明記）。

残タスクはSora（sprint24-qa）とみゆきち（sprint24-retro）のみ。
