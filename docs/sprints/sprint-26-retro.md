# Sprint-26 レトロスペクティブ

- 実施日: 2026-08-02
- 担当: みゆきち（retro エージェント）
- スプリント: sprint-26（組織の足腰: Enforcement実装とSDD仕様積層の制度化、ブランチ feat/sprint-26、PR #143 Draft）

---

## ルーブリックスコア

| 評価軸 | スコア | 合格基準 | 判定 |
|--------|--------|---------|------|
| 仕様明確度 | 0.93 | >= 0.8 | PASS |
| QA合格率 | 1.00 | >= 0.9 | PASS |
| ブロック率 | 0.00 | <= 0.1 | PASS |
| 負荷分散（ポイントベース・公式） | 1.43 | <= 2.0 | PASS |
| 負荷分散（タスク数ベース・補助） | 1.14 | 参考値 | — |

> FAIL 軸: なし。全4軸PASS。ただし仕様明確度（0.93）はsprint26-qaのretry_count=1が要因。この1件はQA再判定（CHANGES_REQUESTED→修正→APPROVED）を記録するためのretryであり、実装のやり直しではない（詳細は Problem 節・agent-crew-sprint-26-tooling-001 参照）。

### enforce-retro-stop.sh 実戦検証（ステップ6.5）

本スプリントの `retro-stop-hook-live-check`（#12）タスクで実施済みの結果を引用する。

- 発動確認（隔離環境）: PASS — 一時ディレクトリに疑似gitリポジトリ＋疑似`_queue.json`（実装タスクDONE・レトロタスクTODO）を用意し、引数なし起動・Claude Codeが渡すstdin JSON形式を模した起動の両方でStopフックの警告がstderrに出力されることを確認した。
- 誤検知チェック（実リポジトリ）: なし — sprint-26進行中（非DONEタスクが残存する状態）の実リポジトリで実行し、警告が出力されないことを確認した。
- 発見事項: `scripts/enforce-retro-stop.sh` はstdin（Claude CodeがStopフックに渡す `session_id`・`transcript_path`・`hook_event_name`・`stop_hook_active` 等のJSON）を一切読み取っておらず、判定は `git rev-parse --show-toplevel` によるcwd特定と `.claude/_queue.json` / `docs/sprints/<sprint>-retro.md` のファイル存在確認のみに基づく。将来Claude Code側のstdin形式が変わっても本スクリプトの動作に影響はないが、セッション文脈情報は現状活用されていない。

---

## スプリント概要

- タスク数: 14（全DONE）
- retry_count合計: 1（sprint26-qaのQA再判定によるもの。実装差し戻しではない）
- BLOCKEDタスク: 0
- QA対象: 4タスク（sdd-qa・audit-scan-qa・subagent-stop-enforce-qa・sprint26-qa、いずれもAPPROVED）
- sprint26-qaは初回CHANGES_REQUESTED（MAJOR1件: 本レトロの担当者=みゆきち自身のretro.md追記漏れ）→ 修正後APPROVED

### 担当者内訳

| エージェント | タスク数 | ポイント |
|-------------|---------|---------|
| Alex | 4 | 10 |
| Riku | 4 | 10 |
| Sora | 4 | 6 |
| みゆきち | 2 | 2 |

総タスク数=14、稼働担当数=4。ポイントベース: 最多10pt（Alex/Riku同率）/平均7pt=1.43。

---

## 成功パターン（Keep）

### 実装者による設計書内不整合の能動的検知・是正

Alex作成の `subagent-stop-enforce-design.md` に、§4のコード内コメントと§7のQA手順とで `QUEUE_FILE` の参照方法（環境変数優先か固定パスか）に不整合があったが、Riku（実装担当）が実装時にこれを検知し、実装意図と整合するよう修正した。Soraの再QAで整合性が確認され、CRITICAL/MAJORなしでAPPROVEDとなった。設計→実装の橋渡し工程で、実装者が設計書の内部矛盾を受動的に転記せず能動的に是正した成功例であり、今後もRikuへの委譲前チェックリストにこの観点を明記することを推奨する（`agent-crew-sprint-26-design-001`）。

---

## 失敗パターン（Problem）

### queue.py の qa_result 上書き不可仕様によるretry_count汚染（MEDIUM）

queue.pyの仕様上 `qa_result` は上書きできず、`done` 側にも重複記録のガードがない。そのためQA再判定（CHANGES_REQUESTED→修正→APPROVED）を記録する正規経路は `retry` コマンドしか存在せず、Soraがsprint26-qaの再判定を記録するためにretryを使った結果、`retry_count` が「QA再判定回数」の意味で1に増加した。retro.mdステップ6の仕様明確度スコアはこの区別ができず、実装のやり直しとQA再判定を同一のリトライ数としてカウントしてしまう。`qa --force` オプションの追加、またはdone側のガード改善をバックログ化・Issue起票することを推奨する（`agent-crew-sprint-26-tooling-001`）。

### vaultのADR索引と実リポジトリの乖離（MEDIUM）

vault側のADR索引（`~/Workspace/Obsidian/decisions/agent-crew-adr-index.md`）が実リポジトリの状態とズレていた。sdd-quality-loop-adr関連3文書がマスターワークツリーに未コミットのまま存在し、索引には記載があったがリポジトリ本体（origin/main）には未反映だった。この同期漏れが、Sprint-26計画時の事前チェック（ステップ0.8）で「sdd-quality-loop-adrは現行リポジトリに実在しない」という前提相違を引き起こした根因。索引に未コミット文書を記載する場合は「未コミット」と明記するルール、または機械チェック（`git log --all -- <path>`）を運用に組み込むことを推奨する（`agent-crew-sprint-26-process-001`）。

### 新設監査機構が新設監査対象をすり抜ける自己参照（MEDIUM・sprint26-qaでMAJOR検出）

sprint26-qaでMAJORとして検出: 新設した `audit-scan.sh`（Kai定常スキャン）が、同一スプリントで新設されたSubagentStopフック（`enforce-queue-done-stop.sh`）をhooks判定パターンにマッチさせられず、UNKNOWN/WARNING扱いにしてしまう自己参照課題があった。判定パターンを「先頭トークン`*.sh`全般」への一般化に修正し、実機再実行でWARNING消滅・PASS扱いを確認した（Sora再判定）。同一スプリント内で「監査対象となる新規コンポーネント」と「監査を行う新規スキャナ」を同時に新設する場合の一般的リスクとして記録する（`agent-crew-sprint-26-reliability-001`）。

### みゆきち自身のretro.md追記漏れ（MAJOR・sprint26-qaで検出・自己言及的な不具合）

みゆきち（本エージェント）が `retro-stop-hook-live-check` タスクのnotesに明記されていた「retro.mdの完了条件への手順追記」要求を見落とし、実戦検証（stderr警告出力の確認）のみを実施してドキュメント反映を欠落させた。sprint26-qaでMAJORとして差し戻され、`.claude/agents/retro.md` にステップ6.5「enforce-retro-stop.sh実戦検証（スプリント中1回・完了条件）」を新設し解消した。notesに複数の実施事項が含まれる場合、片方のみで完了報告してしまうリスクがあったため、完了報告前に notes 原文を再読し箇条書きで照合する運用をみゆきち自身の手順に追加した（`agent-crew-sprint-26-process-003`）。

### gh issue create の権限拒否（新規発見・今回のレトロで初検出）

本レトロのステップ4（Issue化）で `gh issue create` を実行しようとしたところ、`.claude/settings.json` の `permissions.allow` には `Bash(gh issue create *)` が登録されているにもかかわらず、Auto Modeの分類器により「Blocked by classifier」として拒否された。設定ファイル上の許可と、実行時のAuto Mode分類器判定が別レイヤーで動作しており、settings.jsonの許可だけでは実行を保証しない可能性がある。今回はteam-leadへ代行を依頼する形で対応した。lesson化・原因調査は次スプリント以降の検討事項とする（今回は`_lessons.json`への新規lesson登録は見送り、観察記録として本文書にのみ残す）。

---

## 記録した Lesson

| lesson_id | 概要 | priority | status |
|-----------|------|---------|--------|
| agent-crew-sprint-26-tooling-001 | queue.pyのqa_result上書き不可仕様によるretry_count汚染 | 6 | open |
| agent-crew-sprint-26-process-001 | vaultのADR索引と実リポジトリの乖離 | 4 | open |
| agent-crew-sprint-26-design-001 | Alexの設計書内不整合をRikuが実装時に検知・修正（成功パターン） | 1 | open |
| agent-crew-sprint-26-reliability-001 | 新設監査機構が新設監査対象をすり抜ける自己参照 | 4 | open |
| agent-crew-sprint-26-process-003 | みゆきち自身のretro.md追記漏れ（notes見落とし） | 4 | open |

合計: 5件

> 注: 当初 `agent-crew-sprint-26-process-002` として記録しようとしたところ、同IDが `verify-query-rule-doc`（Issue #141対応）で既に `pm-learned-rules.md` に直接記載済みであることが判明し、ID衝突を回避するため `agent-crew-sprint-26-process-003` に修正した。この直接記載は `_lessons.json` を経由しないイレギュラーな経路であり、次スプリント以降のID採番前に `pm-learned-rules.md` 側の既存IDも確認する運用が望ましい。

---

## Issue 化結果

エビデンスゲート（priority_score >= 4 かつ evidence 1件以上かつ issue_url == null）通過:

| lesson_id | 判定 | 理由 |
|-----------|------|------|
| agent-crew-sprint-26-tooling-001 | 起票推奨 | priority=6・evidenceあり |
| agent-crew-sprint-26-process-001 | 起票推奨 | priority=4・evidenceあり |
| agent-crew-sprint-26-reliability-001 | 起票推奨 | priority=4・evidenceあり |
| agent-crew-sprint-26-process-003 | 起票推奨 | priority=4・evidenceあり |
| agent-crew-sprint-26-design-001 | 対象外 | priority=1（成功パターンのため評価対象外） |

> `gh issue create` がAuto Mode分類器によりブロックされたため、上記4件は実際にはIssue作成できていない。team-leadへ代行を依頼した。

### 過去スプリント（sprint-23〜25）の未Issue化積み残し（新規発見・報告事項）

`_lessons.json` 全体に対するエビデンスゲートを実行したところ、sprint-23〜25の以下12件がゲート通過条件を満たしながら `issue_url == null` のまま残存していることを確認した（`gh issue list --label lessons-learned` で照合し、該当するIssueが見つからないことを確認済み）。

- agent-crew-sprint-23-planning-001（priority 6）
- agent-crew-sprint-23-design-001（priority 4）
- agent-crew-sprint-24-planning-001（priority 4）
- agent-crew-sprint-24-planning-002（priority 4）
- agent-crew-sprint-24-design-001（priority 6）
- agent-crew-sprint-24-tooling-001（priority 4）
- agent-crew-sprint-24-tooling-002（priority 6）
- agent-crew-sprint-25-reliability-001（priority 6）
- agent-crew-sprint-25-tooling-001（priority 6）
- agent-crew-sprint-25-process-001（priority 6）
- agent-crew-sprint-25-planning-001（priority 4）
- agent-crew-sprint-25-tooling-002（priority 4）

これらは今回のsprint-26スコープ外のため今回はIssue化を実施しなかったが、意図的な保留か過去レトロでの見落としかは不明であり、team-leadの判断を仰ぐべき事項として報告する。

---

## pm-learned-rules.md 更新結果

- 追加: 4件（`.claude/agents/pm-learned-rules.md`、priority_score >= 3 の新規lessonすべて）
  - `agent-crew-sprint-26-tooling-001`: [みゆきち] queue.pyのqa_result上書き不可仕様に伴うretry_count汚染を認識する
  - `agent-crew-sprint-26-process-001`: [Yuki] vaultのADR索引はコミット済みドキュメントのみを記載する
  - `agent-crew-sprint-26-reliability-001`: [Alex] 監査機構と監査対象を同一スプリントで新設する場合はドッグフーディングを設計に含める
  - `agent-crew-sprint-26-process-003`: [みゆきち] タスクnotesに複数の実施事項がある場合は完了報告前に原文を再読し箇条書きで照合する
- スキップ（重複）: 0件
- スキップ（priority < 3）: 1件（`agent-crew-sprint-26-design-001`、priority=1）

---

## Issue 起票推奨（オーナー確認後、team-lead経由で起票）

1. **`agent-crew-sprint-26-tooling-001`**（priority 6）: queue.py に qa --force オプション、または done側の再QA記録ガード改善。
2. **`agent-crew-sprint-26-process-001`**（priority 4）: vault ADR索引の未コミット注記ルール・機械チェックの導入。
3. **`agent-crew-sprint-26-reliability-001`**（priority 4）: 監査機構と監査対象の同時新設時のドッグフーディング手順の恒久ルール化。
4. **`agent-crew-sprint-26-process-003`**（priority 4）: タスクnotes複数事項チェックの運用定着。
5. **過去スプリント積み残し12件のIssue化要否判断**（新規報告事項）: sprint-23〜25の未Issue化lessonをまとめてIssue化するか、意図的保留として棚卸しするかのteam-lead判断。

---

## 次スプリントへの改善優先事項

1. **gh issue create の権限拒否原因調査**: settings.jsonのpermissions.allowに登録済みのコマンドがAuto Mode分類器で拒否される事象が発生した。みゆきちのサブエージェント権限とteam-lead権限の差異、またはclassifierの追加制約の有無を次スプリントで調査する。
2. **queue.pyのQA再判定記録手段の改善**: `qa --force` またはdone側ガード改善を実装し、retry_countの意味的汚染を解消する。
3. **lesson_id採番前のpm-learned-rules.md確認の徹底**: `_lessons.json` だけでなく `pm-learned-rules.md` に直接記載されたlesson_id（`_lessons.json`を経由しない直接記載）が存在する場合があるため、新規lesson_id採番前に両ファイルを確認する運用を明文化する。
4. **過去スプリント（23〜25）の未Issue化lesson12件の棚卸し**: 意図的保留か見落としかを判断し、対応方針を確定する。
