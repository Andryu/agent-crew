# Sprint-25 レトロスペクティブ

- 実施日: 2026-08-01
- 担当: みゆきち（retro エージェント）
- スプリント: sprint-25（組織OS Phase 2 — テンプレート物理分離、ブランチ feature/my-company、PR #136 Draft）

---

## ルーブリックスコア

| 評価軸 | スコア | 合格基準 | 判定 |
|--------|--------|---------|------|
| 仕様明確度 | 1.00 | >= 0.8 | PASS |
| QA合格率 | 1.00 | >= 0.9 | PASS |
| ブロック率 | 0.00 | <= 0.1 | PASS |
| 負荷分散（ポイントベース・公式） | 2.00 | <= 2.0 | PASS（合格基準ちょうど） |
| 負荷分散（タスク数ベース・補助） | 1.67 | 参考値 | — |

> FAIL 軸: なし。ただし負荷分散（ポイントベース）は合格基準ちょうど（2.00 ≤ 2.00）であり、次スプリントでわずかな偏りでも FAIL に転じる境界値。Riku（M×2=6pt）への集中傾向は継続監視する（詳細は Problem 節参照）。
>
> 本スプリントから負荷分散スコアの公式指標を「タスク数ベース」から「ポイントベース（complexity加重）」に変更した（agent-crew-sprint-25-planning-001、詳細後述）。従来のタスク数ベース(1.67)ではPASSに余裕があるように見えるが、ポイントベースでは境界値ちょうどであり、指標の選び方自体が合否判定に影響することが本スプリントで明らかになった。

---

## スプリント概要

- タスク数: 9（全 DONE）
- retry_count 合計: 0（`_queue.json` 上の記録。ただし後述の通り、inline QA タスクでのCHANGES_REQUESTED→修正のサイクルは retry_count に反映されない構造的な盲点がある）
- BLOCKED タスク: 0
- QA 対象: 2タスク（hq-distribution-qa・sprint25-qa、いずれも APPROVED）
- sprint25-qa は初回 CHANGES_REQUESTED（CRITICAL3件）→ 全件修正・再現テスト後 APPROVED

### 担当者内訳

| エージェント | タスク数 | ポイント | タスク一覧 |
|-------------|---------|---------|-----------|
| Riku | 2 | 6 | hq-install-distribution / hq-template-dir |
| みゆきち | 3 | 5 | retro-mkdir-lock / retro-stop-hook / sprint25-retro |
| Sora | 2 | 2 | hq-distribution-qa / sprint25-qa |
| Ren | 1 | 1 | sprint-points-script |
| Fable | 1 | 1 | org-crossref-check（計画立案と並行して先行完了） |

総タスク数=9、稼働担当数=5。タスク数ベース: 最多3件（みゆきち）/平均1.8=1.67。ポイントベース: 最多6pt（Riku）/平均3pt=2.00。

### 特殊な進行

- レトロ関連の2タスク（retro-mkdir-lock・retro-stop-hook）をみゆきち自身の担当に切り出したことで、Sprint-23・24で連続していたRiku集中を回避した（後述 Keep 参照）。
- オーナーが別ワークツリー（`feature/dashboard-live`）でダッシュボード実データ接続を並走開始した。経営会議判断③（実データ接続は保留維持）への事後修正であり、次回経営会議でRinが記録予定。本スプリントのタスク範囲には影響していない。

---

## 成功パターン（Keep）

### 計画時のjq機械検算とレトロタスクの自己切り出しによる負荷分散改善

Yuki（team-lead）が計画立案時にjqによる機械検算を実施し、合計ポイント計算のズレ（Issue #135の必要性の実証）を計画確定前に検出・修正した。また、レトロ関連の2タスクをRikuではなくみゆきち自身の担当に切り出したことで、Sprint-23（2.29 FAIL）・Sprint-24（2.22 FAIL）と2スプリント連続していたRiku集中を回避し、Sprint-25の負荷分散スコア（タスク数ベース1.67）がPASSした。この2つの実践は次スプリント以降も継続すべき標準手順である。

### QAの実機実行検証によるCRITICALバグ3件の検出

sprint25-qa（Sora）はコードレビューに留まらず、scratchpadへの疑似部門ディレクトリ複製とinstall.shの実際の実行、mkdirロックの2プロセス競合の実機再現という「実際に動かす」検証を行い、コードレビューだけでは気づけなかったCRITICALバグを3件検出した。

1. install.sh の新規symlink関数に自己参照ガードが無い
2. 同関数がsymlink_file相当の上書き保護を持たない
3. みゆきちのmkdirロック実装で、trapの設定順序により他プロセスの正当なロックを破壊しうる

3件とも修正後に再現テストで解消を確認し、APPROVEDとなった。「実機実行によるQA」がコードレビューでは検出不能な重大バグを防いだ実例として、今後もQAの標準手順として維持する。

---

## 失敗パターン（Problem）

### install.sh の新規symlink関数における自己参照ガード欠如・上書き無防備（CRITICAL）

Riku の hq-install-distribution に、配布先が自分自身のパスと一致する場合のガードと、配布先の既存ファイル上書き前チェックが欠如していた。Sora のQA実機実行で発覚し、修正済み。

### みゆきちのmkdirロックにおけるtrap設定順序バグ（CRITICAL）

retro-mkdir-lock の初版実装で、`acquire_lock` 呼び出し前に `trap release_lock EXIT INT TERM` を設定していたため、ロック取得がタイムアウトで失敗した場合にもtrapが発火し、他プロセスが正当に保持しているロックを削除してしまっていた。Sora QAが2プロセス競合を実機再現して発見。修正（trapをacquire_lock成功後に設定 + release_lockに所有権チェックを追加）後、同シナリオの再現テストで解消を確認した。

### queue.sh done未実行によるキューの実態乖離（MAJOR・再発）

Riku（hq-install-distribution・hq-template-dir）とみゆきち（retro-mkdir-lock・retro-stop-hook）が実装完了後に `scripts/queue.sh done` を即時実行せず、`_queue.json` が実態と乖離した。この結果、Soraの後続タスクの `scripts/queue.sh start` が依存タスク未完了エラーでブロックされ、team-leadが手動でqueue更新を指示するまで進行が止まった。**agent-crew-sprint-24-planning-001**（着手・完了のタイミングでの即時反映ルール）がpm-learned-rules.mdに既に記載されていたにもかかわらず、実行フェーズで遵守されなかった。ルールの存在だけでは行動が変わらないことを示す事例であり、次スプリントでは完了報告フォーマットへのチェック項目追加、またはteam-lead側での代行実行を検討する。

### 負荷分散スコアの2定義の併存（Renが発見）

Ren（sprint-points-script実装時）が、負荷分散スコアに「タスク数ベース」（Sprint-25計画書で1.67）と「ポイントベース」（Sora QAで2.0）の2定義が併存していることを発見した。retro.mdはタスク数ベースのjqクエリのみを提示しており、どちらを公式とするか明文化されていなかった。**本レトロで正式決定**: ポイントベース（complexity加重）を公式指標、タスク数ベースを補助指標とする（Sora QAの推奨採用）。retro.mdステップ6を既に更新済み。

### retro.md自身のルーブリック計算式バグ（新規発見・自己言及的な不具合）

retro.mdステップ6の負荷分散スコアjqクエリが `.tasks[].agent` を参照していたが、`_queue.json` の実フィールド名は `.assigned_to` であり、常にタスクが全件「unassigned」扱いとなり負荷分散スコアが常に1.0（偽陽性PASS）を返す不具合があった。本レトロで実際にこのクエリを実行して初めて発覚した。過去のレトロでは字面通り実行せず手計算していたため実害は顕在化していなかったと推定される。retro.mdを `scripts/sprint-points.sh`（Ren作成、`.assigned_to`参照で正しく実装済み）を呼び出す方式に修正済み。

### retry_count集計の構造的盲点（観察のみ、lesson化は見送り）

`_queue.json` の `retry_count` は0だったが、実際には install.sh とmkdirロックの2箇所でQA CHANGES_REQUESTED→修正のサイクルが発生していた。これらは `qa_mode: inline` のタスクであり、正式なQAタスク（Sora担当）を経由しない修正のため `retry_count` に反映されない。ルーブリックの「仕様明確度」スコア(1.00)は実態より高く出ている可能性がある。今回は新規lessonとしては起票せず観察記録に留めるが、次回同様の乖離が見られた場合はlesson化を検討する。

---

## 記録した Lesson

| lesson_id | 概要 | priority | status |
|-----------|------|---------|--------|
| agent-crew-sprint-25-reliability-001 | install.shのsymlink関数に自己参照ガード欠如・上書き無防備（CRITICAL、実機QAで検出） | 6 | implemented |
| agent-crew-sprint-25-tooling-001 | mkdirロックのtrap設定順序バグ（他プロセスのロックを破壊、CRITICAL） | 6 | implemented |
| agent-crew-sprint-25-process-001 | queue.sh done未実行の再発（agent-crew-sprint-24-planning-001の再発） | 6 | open |
| agent-crew-sprint-25-planning-001 | 負荷分散スコアはポイントベースを公式指標とする（正式決定） | 4 | implemented |
| agent-crew-sprint-25-tooling-002 | retro.md自身の`.agent`誤参照バグ（偽陽性PASS） | 4 | implemented |
| agent-crew-sprint-25-process-002 | Yukiのjq機械検算とレトロタスク自己切り出しによる負荷分散改善（成功パターン） | 2 | open |

合計: 6件（うち3件は本レトロ内で即座に修正・実装済み = status: implemented）

既存lessonのステータス更新: `agent-crew-sprint-24-tooling-002`（flock→mkdirロック移行）を `status: implemented` に更新（retro-mkdir-lockタスクで対応完了）。

---

## Issue 化結果

team-lead指示により、本スプリントは `gh issue create` によるIssue化を実施せず、エビデンスゲート通過分をレトロ文書内の「起票推奨」として列挙するに留める。

エビデンスゲート（priority_score >= 4 かつ evidence 1件以上かつ issue_url == null）通過:

| lesson_id | 判定 | 理由 |
|-----------|------|------|
| agent-crew-sprint-25-reliability-001 | 起票推奨 | priority=6・evidenceあり |
| agent-crew-sprint-25-tooling-001 | 起票推奨 | priority=6・evidenceあり |
| agent-crew-sprint-25-process-001 | 起票推奨 | priority=6・evidenceあり |
| agent-crew-sprint-25-planning-001 | 起票推奨 | priority=4・evidenceあり |
| agent-crew-sprint-25-tooling-002 | 起票推奨 | priority=4・evidenceあり |
| agent-crew-sprint-25-process-002 | 対象外 | priority=2（基準 priority >= 4 未満） |

> 注: 上記5件は該当する不具合そのものは本スプリント内で既に修正済み（`agent-crew-sprint-25-process-001` を除く）。Issue化は再発防止の恒久記録・追跡目的であり、オーナー確認後の起票を推奨する。

---

## pm-learned-rules.md 更新結果

- 追加: 5件（`.claude/agents/pm-learned-rules.md`、priority_score >= 3 の新規lessonすべて）
  - `agent-crew-sprint-25-reliability-001`: [Riku] symlink/ファイル配布系の新関数は自己参照ガードと上書き防止を実装し、実機実行でQAする
  - `agent-crew-sprint-25-tooling-001`: [みゆきち] mkdir等のディレクトリロックは、trapをリソース取得成功後に設定し、解放時は所有権チェックを行う
  - `agent-crew-sprint-25-process-001`: [全エージェント] タスク完了後は scripts/queue.sh done を即時実行する（再発防止の再徹底）
  - `agent-crew-sprint-25-planning-001`: [Yuki] 負荷分散スコアはポイントベース（complexity加重）を公式指標とする
  - `agent-crew-sprint-25-tooling-002`: [みゆきち] retro.md内のjqスニペットは必ず実データに対して一度実行してから確定する
- スキップ（重複）: 0件
- スキップ（priority < 3）: 1件（`agent-crew-sprint-25-process-002`）

---

## Issue 起票推奨（オーナー確認後に起票）

1. **`agent-crew-sprint-25-reliability-001`**（priority 6）: symlink/ファイル配布系の実装パターン（自己参照ガード・上書き防止）の恒久ルール化。
2. **`agent-crew-sprint-25-tooling-001`**（priority 6）: mkdirロック実装パターン（trap順序・所有権チェック）の恒久ルール化。
3. **`agent-crew-sprint-25-process-001`**（priority 6）: queue.sh done即時実行の再発防止（完了報告フォーマットへのチェック項目追加、またはteam-lead代行実行の検討）。
4. **`agent-crew-sprint-25-planning-001`**（priority 4）: 負荷分散スコアのポイントベース公式化（pm-estimation.md・過去計画書テンプレートへの反映）。
5. **`agent-crew-sprint-25-tooling-002`**（priority 4）: エージェント定義内のjqスニペットは実行検証必須というレビュー観点の恒久ルール化。
6. **retry_count集計の構造的盲点の解消検討**（lesson化は見送ったが観察記録として残す）: `qa_mode: inline` タスクのCHANGES_REQUESTED→修正サイクルを `_queue.json` にどう反映するか、次スプリントで検討する。

---

## 次スプリントへの改善優先事項

1. **負荷分散（ポイントベース）が境界値ちょうど（2.00）**: Riku（M×2=6pt）への集中傾向を次スプリント計画時に注視する。実装タスクをRiku以外に振れないか検討する余地がある。
2. **queue.sh done即時実行の再発防止**: ルールの存在だけでは行動が変わらなかった。完了報告フォーマットへのチェック項目追加、またはteam-lead側での代行実行フローへの変更を次スプリントで検討する。
3. **retro.md記載手順の実行検証の徹底**: 今回`.agent`誤参照バグが発覚したように、エージェント定義内のコード片は記載するだけでなく実データに対して実行確認する運用を徹底する。
4. **retro-stop-hookの初回実運用確認**: 本レトロの実施自体が、Sprint-25で新規実装したStopフック（`scripts/enforce-retro-stop.sh`）が誤検知なく機能するかの初回動作確認を兼ねている。今回はteam-lead経由でみゆきちが明示的に起動されたため、Stopフックの自動検知が実際に発動したかどうかは別途確認が必要（次回、レトロ未実施のままセッション終了を試みるケースで動作確認することを推奨）。
