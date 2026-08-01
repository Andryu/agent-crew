# Sprint-25 計画書

**期間**: 2026-08-01〜
**ブランチ**: feat/sprint-25
**ゴール**: 「組織OS Phase 2 — テンプレート物理分離」。ADR-014 Phase 2（部門テンプレートディレクトリの実体作成 + install.sh への本社機能配布関数追加）を実行し、横展開トリガー条件①（`docs/org/departments.md` 第3条）を充足させる。あわせて第1回経営会議で承認済みのレトロIssue起票8件のうち #128・#133・#134・#135 を本スプリントで消化する。

> **経営会議判断（2026-08-01 第1回, `docs/org/council/2026-08-01-queue.md`）**: 「① Sprint-25テーマ=Phase2: 承認」「② レトロIssue 8件: 一括承認（#128〜#135起票済み）」「③ 優先度: Phase2優先、実データ接続は保留維持」の3件がオーナー確定済み。本計画書はこの判断をそのまま反映する。

> **更新**: タスク #1 org-crossref-check は、計画立案と並行してFable（メインセッション）が完了済み。成果物: `.claude/agents/pm.md`（ステップ0.8新設）。残タスクは #2〜#9 の8件。

---

## スプリント前チェック結果

- [x] 前スプリントの設計完了タスクとの突合: Sprint-24 全9タスク DONE（QA APPROVED_WITH_NOTE、レトロ完了済み）。Sprint-24 の成果物（`docs/org/departments.md` / ADR-014 / `.claude/agents/coo.md` 等）はいずれも本スプリントの前提として実在確認済み。重複タスクなし。
- [x] 計画重複タスク: なし。`templates/department/` は新規作成予定で既存ディレクトリなし（事前に `ls templates/` で確認済み、`department/` は未作成）。`install.sh` の新関数（symlink_hq_file 相当）も既存コードに同等機能なし（`symlink_skill` はスキル専用で本社機能ファイルは対象外であることを install.sh 本文で確認済み）。
- [x] DECISIONS.md 反映: Sprint-15〜24 の失敗パターンを確認。特に Sprint-08/09/12（engineer-go 委譲時のトークン超過）と Sprint-17（フック権限未登録）を本スプリントのタスク設計（下記チェックリスト）に反映。
- [x] フック関連タスクの権限: `retro-stop-hook`（Issue #128）が新規Stopフックを追加する。既存 `.claude/settings.json` の `permissions.allow` には `Bash(bash *)` / `Bash(chmod *)` / `Write(**)` が既に登録済みのため新規スクリプト実行はカバー範囲内。念のため `Bash(scripts/enforce-retro-stop.sh *)` の個別パターンをスプリント開始前に追記した（相対パス形式、`agent-crew-sprint-15-tooling-001` 準拠）。
- [x] docs/org/ 相互参照チェック（Issue #134, 新設ステップ0.8）: 実施済み。`constitution.md` / `departments.md` / `weekly-council.md` / `coo.md` の相互参照は全件実在確認、破損リンクなし。`docs/org/council/YYYY-MM-DD-queue.md` は週次生成パターンのため実在チェック対象外として扱った。
- [x] Riku 担当 L タスク: 0件（本スプリントの Riku 担当タスクは `hq-install-distribution`・`hq-template-dir` の M×2 のみ。制限 1件/sprint に適合）。
- [x] pm-learned-rules.md 反映:
  - `agent-crew-sprint-23-planning-001`（priority:6, 負荷分散スコア事前計算）→ 担当者ドラフト作成後、全タスク・全担当（Fable含む）でスコアを計算（下記「担当者負荷分散」参照）。
  - `agent-crew-sprint-24-planning-002`（priority:4, 負荷分散スコアはFable先行完了タスクも含めて全体計算）→ 本スプリントは Fable の先行完了が `org-crossref-check`（S）1件のみだが、これも含めて計算した。
  - `agent-crew-sprint-24-design-001`（priority:6, 複数文書横断QA）→ `sprint25-qa` の確認項目に「retro-stop-hook のバイパス条件が誤検知なく機能するか」を明記し、単一ファイルQAに閉じない設計とした。
  - `agent-crew-sprint-24-tooling-002`（priority:6, macOSにflockなし）→ Issue #133 としてタスク化（`retro-mkdir-lock`）。
  - `agent-crew-sprint-09-process-001`（priority:9, engineer-go委譲前トークン推定）→ Riku担当2タスクとも参照ファイルを1〜2件に絞り、委譲指示を2,000トークン以下に収める設計とした。
  - `agent-crew-sprint-17-tooling-001`（priority:6, フック実装タスクの権限事前登録）→ 上記「フック関連タスクの権限」参照。
- [x] 外部リポジトリ global 教訓: `~/.claude/_lessons.json` に agent-crew 以外由来の未処理 global 教訓なし（対象なし）。

---

## タスク一覧

| # | slug | タイトル | 担当 | 状態 | 依存 | complexity | risk_level | qa_mode |
|---|------|----------|------|------|------|------------|------------|---------|
| 1 | org-crossref-check | docs/org/ 相互参照チェック（Issue #134） | Fable | **DONE** | なし | S | low | — |
| 2 | hq-install-distribution | install.sh に本社機能配布関数を追加（ADR-014 Phase2） | Riku | TODO | なし | M | medium | inline |
| 3 | hq-template-dir | 部門テンプレートディレクトリの実体作成（ADR-014 Phase2） | Riku | TODO | #2 | M | medium | inline |
| 4 | hq-distribution-qa | 部門テンプレート複製 + symlink配布の検証QA | Sora | TODO | #2 #3 | S | low | — |
| 5 | retro-mkdir-lock | retro.md のロック手順をmkdir化（Issue #133） | みゆきち | TODO | なし | S | low | inline |
| 6 | retro-stop-hook | レトロ強制Stopフックの実装（Issue #128） | みゆきち | TODO | なし | M | **high** | inline |
| 7 | sprint-points-script | 計画書ポイント集計のjq機械化（Issue #135） | Ren | TODO | なし | S | low | inline |
| 8 | sprint25-qa | Sprint-25 最終QA | Sora | TODO | #4 #5 #6 #7 | S | low | — |
| 9 | sprint25-retro | Sprint-25 レトロスペクティブ実施（みゆきち） | みゆきち | TODO | #8 | S | low | — |

> **合計ポイント: 15 pt**（S×1=1[#1, DONE] + M×3=9[#2,#3,#6] + S×5=5[#4,#5,#7,#8,#9] → S計6件=6pt + M計3件=9pt = **15pt**）。`scripts/sprint-points.sh`（本スプリントで新設予定）と同一ロジックの jq クエリで機械検算済み（下記参照）。
>
> Fable が計画立案と並行して完了したのは #1（S=1pt）のみ。残ポイントは 14pt。

```
$ jq '<sprint-points.sh 相当のクエリ>' <<< '[9タスクのslug/assigned_to/complexity配列]'
{
  "total_points": 15,
  "by_complexity": [{"complexity":"M","count":3,"points":9}, {"complexity":"S","count":6,"points":6}],
  "by_agent": [...],
  "load_balance": {"total_tasks":9, "distinct_agents":5, "max_count":3, "avg":1.8}
}
```

### 担当者負荷分散（`agent-crew-sprint-23-planning-001` / `agent-crew-sprint-24-planning-002` 対応）

全タスク・全担当（Fable含む）で計算:

| 担当 | タスク数 | ポイント |
|------|---------|---------|
| みゆきち | 3（retro-mkdir-lock, retro-stop-hook, sprint25-retro） | 5 |
| Riku | 2（hq-install-distribution, hq-template-dir） | 6 |
| Sora | 2（hq-distribution-qa, sprint25-qa） | 2 |
| Ren | 1（sprint-points-script） | 1 |
| Fable | 1（org-crossref-check, DONE） | 1 |

総タスク数=9、稼働担当数=5、平均=9/5=1.8、最多担当数=3（みゆきち）。
**負荷分散スコア = 3 / 1.8 = 1.67**（基準 <=2.0 に適合、PASS）。

Sprint-23（2.29 FAIL）・Sprint-24（2.22 FAIL）と2スプリント連続で発生していた「Riku集中」を、実装タスクの一部（レトロ関連の #133・#128）をみゆきち自身の担当領域として切り出すことで回避した。Riku は当初案でも #133・#128 を担当候補にできたが、両タスクとも「レトロ運用そのもの」を対象とする性質上、レトロ担当者（みゆきち）が自らの手順を修正する方が設計意図に整合すると判断した。

### Riku 担当 L タスク確認

Riku 担当タスク: `hq-install-distribution`（M）・`hq-template-dir`（M）の2件。
L タスク件数: **0件**（制限 1件/sprint に適合）。

### engineer-go 委譲前チェックリスト確認（Issue #64）

| タスク | 参照ファイル数 | 変更ファイル数 | complexity | 判定 |
|--------|--------------|--------------|------------|------|
| hq-install-distribution | 2（ADR-014, install.sh抜粋） | 1（install.sh） | M | OK |
| hq-template-dir | 1（ADR-014決定事項3のツリー図抜粋） | 複数（新規テンプレート一式）* | M | OK（*新規ファイル群は既存ファイル改変を伴わない機械的スキャフォールディングのため許容。委譲時に指示を「install.shの新コンポーネント実行＋固定パターンのファイル作成」に限定し2,000トークン以内に収める） |

---

## 並列化

- **phase-1（並列実行可）**: `hq-install-distribution`（Riku）・`retro-mkdir-lock`（みゆきち）・`retro-stop-hook`（みゆきち）・`sprint-points-script`（Ren）は互いに依存がなく同時に進められる。
- **phase-2**: `hq-template-dir`（Riku）は `hq-install-distribution` 完了後に着手（新設した install.sh コンポーネントを利用するため）。
- **phase-3**: `hq-distribution-qa`（Sora）は `hq-install-distribution`・`hq-template-dir` 両方完了後に着手。
- **phase-4**: `sprint25-qa`（Sora）は実装系タスク全件（#4〜#7）完了後に着手。
- **phase-5**: `sprint25-retro`（みゆきち）は `sprint25-qa` 完了後、Sora の完了報告に `@retro` を含めて自動起動。

---

## タスク詳細と着手条件

### org-crossref-check（DONE — Fable）
- 成果物: `.claude/agents/pm.md` にステップ0.8「docs/org/ 相互参照チェック（Issue #134）」を新設。既存4文書（constitution.md/departments.md/weekly-council.md/coo.md）の相互参照を grep で抽出し全件実在確認、破損リンクなし。ステップ3の確認事項チェックリストにも項目を追加済み。

### hq-install-distribution（TODO — Riku）
- 対象ファイル: `install.sh` のみ。
- 内容: `symlink_skill` 関数（L385-432）を参考に、本社機能ファイル（`coo.md`/`retro.md`/`security.md`/`doc-reviewer.md`。`pm-protocol.md`/`pm-estimation.md` は ADR-014 注記のとおり過渡期はコピーモデル継続のため対象外）を `TARGET_DIR/.claude/agents/` へ、`docs/org/` 一式を `TARGET_DIR/docs/org/` へ symlink する新関数を追加。`--only` に新コンポーネント（例: `hq-agents`）を追加し、usage/help も更新。
- 参照: `docs/adr/ADR-014-headquarters-department-separation.md` 決定事項2（symlink配布モデルの拡張）。
- 着手条件: なし、即着手可。

### hq-template-dir（TODO — Riku）
- 対象: `templates/department/` を新規作成。
- 内容: ADR-014 決定事項3のツリー構成に従う。`.claude/agents/` 配下の本社機能symlinkは #2 で追加した install.sh の新コンポーネントを実行して生成（ロジック二重実装を避ける）。`pm.md` はプレースホルダとしてコピー、`_queue.json` は `templates/_queue.json` をコピー、`docs/adr`・`docs/sprints` は `.gitkeep` 付き空ディレクトリ、`docs/org/` は symlink。
- 着手条件: #2 完了後。

### hq-distribution-qa（TODO — Sora）
- 内容: scratchpad に `templates/department/` を複製し疑似部門ディレクトリとして扱い、`bash install.sh --only=hq-agents <疑似部門パス>` を実行。symlink が agent-crew の実ファイルに正しく解決されるか（`readlink -f`）を確認。Bash 不可の場合は `CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）` を返す（`agent-crew-sprint-11-reliability-002` 準拠）。
- 着手条件: #2・#3 完了後。

### retro-mkdir-lock（TODO — みゆきち）
- 対象ファイル: `.claude/agents/retro.md` のみ。
- 内容: `flock -x -w 10 200` によるロック手順を、`mkdir ~/.claude/_lessons.json.lockdir` 取得 / `rmdir` 解放の mkdir ロックへ置換。`which flock` で存在確認しフォールバックする分岐も検討可（lesson `agent-crew-sprint-24-tooling-002`）。
- 着手条件: なし、即着手可。

### retro-stop-hook（TODO — みゆきち, risk_level: high）
- 内容: 新規 Stop フックスクリプト（例: `scripts/enforce-retro-stop.sh`）を作成し、`_queue.json` の全タスク DONE かつ当該 sprint の `docs/sprints/sprint-XX-retro.md` 未作成の場合に Stop をブロックする。`.claude/settings.json` の `hooks.Stop` 配列は既存3件（`subagent_stop.sh`／`propose-lesson-rules.sh --dry-run`／`privacy-check.sh`）があるため **追記マージ**すること（上書き禁止）。
- risk_level を high とした理由: Stop フックの不具合は全セッションの終了処理をブロックしうる（`pm-estimation.md` の「強制 high にすべきケース」に準ずる新規統合点）。誤検知防止のバイパス条件（レトロ実施済みマーカーの検出）を必ず設計すること。
- 着手条件: なし、即着手可。実装後は必ず Sora の動作確認（`sprint25-qa`）を経ること。

### sprint-points-script（TODO — Ren）
- 対象: `scripts/sprint-points.sh` 新規作成。
- 内容: `.claude/_queue.json` の `tasks[].complexity` を S=1/M=3/L=5 で jq 集計し、担当者別タスク数・ポイント・負荷分散スコアを出力する。本計画書自体、同一ロジックの jq クエリで先行検算済み（合計15pt、負荷分散スコア1.67、上記「タスク一覧」参照）。
- 着手条件: なし、即着手可。

### sprint25-qa（TODO — Sora）
- 目的: `hq-distribution-qa`・`retro-mkdir-lock`・`retro-stop-hook`・`sprint-points-script` を対象に最終QA。
- 確認項目:
  - `retro-stop-hook` の誤検知防止バイパス条件が実際に機能するか（レトロ完了後に正常に Stop が通ることを実機確認）
  - `hooks.Stop` 配列の既存3件が壊れていないか（追記マージの検証）
  - `retro-mkdir-lock` が macOS 環境で実際にロック取得・解放できるか
  - 本計画書のポイント集計（合計15pt）と `sprint-points-script` の出力が一致するか
- 着手条件: 実装系タスク全件完了後。

### sprint25-retro（TODO — みゆきち）
- 着手条件: `sprint25-qa` 完了後、Sora の完了報告に `@retro` を含めて即起動（オーナー確認不要）。
- 観察対象: `retro-stop-hook` が自分自身（このレトロ）を正しく強制起動できたか（初回動作確認を兼ねる）。

---

## 変更ファイル予定

| ファイル | 変更種別 |
|---------|---------|
| `.claude/agents/pm.md` | ステップ0.8新設（完了済み） |
| `.claude/_queue.json` | Sprint-25 タスク登録（完了済み） |
| `install.sh` | 本社機能配布関数・`--only=hq-agents` 追加 |
| `templates/department/` | 新規作成一式 |
| `.claude/agents/retro.md` | ロック手順を mkdir 化 |
| `scripts/enforce-retro-stop.sh` | 新規作成 |
| `.claude/settings.json` | `hooks.Stop` へ追記マージ、`permissions.allow` に `Bash(scripts/enforce-retro-stop.sh *)` 追記 |
| `scripts/sprint-points.sh` | 新規作成 |
| `docs/sprints/sprint-25.md` | 本ファイル |
| `docs/DECISIONS.md` | Sprint-25 エントリ追記（完了時） |
| `~/.claude/_lessons.json` | Sprint-25 lesson 追記（レトロ時） |
| `.claude/agents/pm-learned-rules.md` | Sprint-25 lesson 反映（レトロ時） |

---

## 完了条件

- [x] docs/org/ 相互参照チェック実施・pm.md への恒久化（Issue #134）
- [ ] `install.sh` に本社機能配布関数（`--only=hq-agents` 等）が追加されている
- [ ] `templates/department/` が ADR-014 決定事項3の構成で実体作成されている
- [ ] 疑似部門ディレクトリへの複製 + symlink 検証がSora QAで確認されている
- [ ] `retro.md` のロック手順が mkdir ベースに修正されている（Issue #133）
- [ ] レトロ強制 Stop フックが実装され、誤検知なく機能することがSora QAで確認されている（Issue #128）
- [ ] `scripts/sprint-points.sh` が新規作成され、本計画書の集計結果（15pt, 負荷分散1.67）と一致する（Issue #135）
- [ ] Sora QA: APPROVED（または APPROVED_WITH_NOTE の場合、NOTE内容を本完了条件に追加し実施確認する）
- [ ] **みゆきちによるレトロスペクティブ完了**（`agent-crew-sprint-22-process-001` 対応。Definition of Done に明示）

---

## トークン消費見積もり

| タスク | complexity | 推定トークン |
|--------|------------|------------|
| hq-install-distribution | M | 40,000 |
| hq-template-dir | M | 40,000 |
| hq-distribution-qa | S | 15,000 |
| retro-mkdir-lock | S | 15,000 |
| retro-stop-hook | M | 40,000 |
| sprint-points-script | S | 15,000 |
| sprint25-qa | S | 15,000 |
| sprint25-retro | S | 15,000 |

推定合計 = (40,000×3 + 15,000×5) × 1.5 = (120,000 + 75,000) × 1.5 = **292,500 tokens**

300,000 tokens 未満 → **1バッチで処理可能**（`pm-estimation.md` 準拠）。バッチ内のサブエージェント起動数上限（3〜4件）を踏まえ、phase-1 の4タスク（Riku/みゆきち×2/Ren）を1バッチ目として並列起動し、後続フェーズを2バッチ目とする運用を推奨する。

---

## 次スプリント候補

- **横展開トリガー②・③の継続観察**: Phase2完了により条件①が充足される見込み。②（経営会議2連続キューのみで回る）・③（現行部門2連続無介入ゲート到達）の充足状況を次回経営会議でRinが報告する。
- **保留中のダッシュボード実データ接続**: 経営会議判断#3で「Phase2優先」となり後続スプリントへ保留。次スプリントの候補として引き続き検討する。
- **Phase 3（投資部門への複製デプロイ）**: 横展開トリガー3条件すべて充足後、オーナーのGo/No-Goを経て着手。本スプリントでは対象外。

---

## 確認事項

- [x] pm-learned-rules.md 反映: 上記「スプリント前チェック結果」参照。
- [x] 経営会議判断の反映: 3件すべて反映済み（テーマ承認・Issue一括承認・優先度Phase2優先）。
- [x] docs/org/ 相互参照チェック: 実施済み（結果: 全参照実在確認、破損リンクなし）。
- [x] フック関連タスクの権限: 登録済み（`Bash(scripts/enforce-retro-stop.sh *)` を相対パス形式で追加。既存の `Bash(bash *)`/`Write(**)` でも実質カバーされるが個別パターンとして明示登録）。
- [x] Riku担当Lタスク: 0件（制限適合）。
- [x] 負荷分散スコア: 1.67（基準 <=2.0 に適合、全担当・全タスクで計算）。
- [ ] `retro-stop-hook`（risk_level: high）の誤検知防止設計は実装時にSoraが重点確認する。実装アプローチの技術的妥当性（フック側でのDONE判定ロジック）はteam-lead判断領域として残す。

残タスクは #2〜#9（Riku 2件・みゆきち 3件・Sora 2件・Ren 1件）。実装体制の起動はteam-leadが行う。
