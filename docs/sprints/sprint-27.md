# Sprint-27 計画書 — 投資部門の開設準備 + 教訓台帳の信頼性回復

- 起案日: 2026-08-02
- ブランチ: `feat/sprint-27`（`origin/main` の 923edcd から分岐）
- 対応する経営会議判断: `docs/org/council/2026-08-02-queue.md`（第2回週次経営会議、委任決裁 #1〜#3）
- 対応Issue: #144 / #149 / #150

## ゴール

ADR-014 Phase 3 前半（投資部門テンプレート複製＋プロジェクト憲章起案）を実地で初運用し、
`_lessons.json` の issue_url 同期漏れを是正して教訓台帳の信頼性を回復する。
投資部門のアクティブ化そのものの Go/No-Go はオーナーの戦略レビュー（PR #151, `docs/org/strategy-2026H2.md`）
に統合されており、本スプリントは「準備」までとする。

## タスク一覧

| # | タスク | 担当 | 依存 | complexity | qa_mode |
|---|--------|------|------|------------|---------|
| 1 | invest-dept-charter: 投資部門プロジェクト憲章の起案（Draft） | Alex | なし | S | inline |
| 2 | queue-qa-reguard-design: Issue #144 設計（qa --force / done側ガード） | Alex | なし | S | — |
| 3 | governance-doc-149-150: Issue #149・#150 の文書反映 | Alex | なし | S | inline |
| 4 | invest-dept-hq-deploy: alpha-predict-jp への組織OSデプロイ実地初運用 | Tomo | なし | M | — |
| 5 | lessons-issue-sync-fix: `_lessons.json` issue_url 同期是正 | Riku | なし | S | inline |
| 6 | queue-qa-reguard-impl: Issue #144 実装 | Riku | #2 | M | — |
| 7 | invest-dept-hq-deploy-qa: デプロイ実機QA | Sora | #4 | M | — |
| 8 | queue-qa-reguard-qa: Issue #144 実装QA | Sora | #6 | S | — |
| 9 | sprint27-qa: 横断QA（憲章・部門文書・queue.py整合） | Sora | #1,#3,#5,#7,#8 | M | — |
| 10 | sprint27-retro: レトロスペクティブ | みゆきち | #9 | S | — |

> **合計ポイント: 18 pt**（S×6件=6pt + M×4件=12pt）

| 担当 | タスク数 | ポイント |
|------|---------|---------|
| Sora | 3 | 7 |
| Riku | 2 | 4 |
| Alex | 3 | 3 |
| Tomo | 1 | 3 |
| みゆきち | 1 | 1 |

負荷分散スコア（ポイントベース・公式指標）= 最多担当7pt ÷ 平均3.6pt = **1.94**（基準 <= 2.0、PASS）。
参考: タスク数ベース（補助指標）= 3 ÷ 2 = 1.5。
（`scripts/sprint-points.sh --md` 実行結果、2026-08-02）

### タスク詳細・notes

**#1 invest-dept-charter（Alex, S）**
`docs/org/templates/project-charter.md` に基づき投資部門の憲章を起案する。MVP定義は
`docs/org/strategy-2026H2.md`（PR #151, feat/strategy-2026h2, 未マージ）の「投資部門MVP」節
（月次成績レポート自動生成→経営会議自動掲載、撤退基準: 3ヶ月連続で判断に使われなければアイドルに戻す）
を仮置きする。ヘッダーに「オーナーの戦略レビューでMVP確定後に有効化（Draft）」と明記すること。
成果物: `alpha-predict-jp` 側 or `docs/org/` 配下のいずれに置くか要判断（部門ネイティブ文書のため
前者が妥当。#4のデプロイ後に部門リポジトリ側 `docs/adr/` 等に配置する案も検討）。

**#2/#6 queue-qa-reguard-design / impl（Issue #144）**
`scripts/queue.py` の `qa` コマンドは `qa_result` 上書き不可（L287-289）。QA再判定の正規経路が
`retry` のみのため `retry_count` が「QA再判定回数」で汚染される（sprint26-qa で実害確認済み）。
設計方針候補: (a) `qa --force` オプション追加（既存 qa_result を上書き、events に再判定である旨を記録）、
(b) `done` コマンド側で qa_result が None のまま done しようとした場合にエラーとするガード。
どちらか一方、または両方を Alex が設計し Riku が実装する。pytest 追加必須。

**#3 governance-doc-149-150（Alex, S）**
Issue #149: `pm.md` の計画手順（スプリント計画フォーマット節）に「タスク分解直後の担当ドラフト段階で
`scripts/sprint-points.sh --md` を実行し負荷分散スコアを確認する」ことを明記する（現状は完了後の集計のみ
明文化されており、ドラフト段階での実行が義務化されていない）。
Issue #150: `.claude/agents/architect.md` に設計完了時のセルフチェック項目（条件分岐の網羅性・
文書内§間の整合性）を追加する。

**#4 invest-dept-hq-deploy（Tomo, M）— 別リポジトリへの書込みタスク**
対象パス: `~/Workspace/claude-agent-teams/finace/alpha-predict-jp`（`orca` 登録済み、git管理下、
現在 `main` ブランチ・作業ツリー概ねクリーン。ただし `src/config.py.bak` が untracked のため
このタスクでは触れないこと）。

手順:
1. `templates/department/` の実体ファイルのうち alpha-predict-jp に未存在のものだけをコピーする。
   - `.claude/agents/pm.md` → 新規作成（alpha-predict-jp に `.claude/agents/` 自体が存在しないため新規ディレクトリ作成）
   - `.claude/_queue.json` → 新規作成（既存なし、確認済み）
   - `docs/sprints/` → 新規作成（既存なし、確認済み）
   - `docs/adr/` は **コピーしない**。alpha-predict-jp には既に実質的なADR群（0002〜0013等）が
     存在するため、テンプレートの `.gitkeep` を持ち込む必要はない。
   - `.claude/skills/` も中身は空テンプレートのため上書き・追加不要（既存3スキルに触れない）。
2. `bash <agent-crewの絶対パス>/install.sh --dry-run --only=hq-agents go ~/Workspace/claude-agent-teams/finace/alpha-predict-jp`
   を必ず先に実行し、生成予定物（`.claude/agents/{coo,retro,security,doc-reviewer}.md` の symlink と
   `docs/org` symlink）が新規作成であって既存ファイルの上書きでないことを確認する。
   （alpha-predict-jp 側に `.claude/agents/` `docs/org` は現状存在しないため衝突しない見込みだが、
   dry-run で必ず裏取りすること — agent-crew-sprint-25-reliability-001 準拠）
3. dry-run 結果に問題なければ `--dry-run` を外して実行する。
4. **自己参照ガードの確認**: install.sh には配布先が `agent-crew` 自身のパスと一致する場合に
   エラーで停止するガードが実装済み（該当箇所: 引数パース部、`REPO_DIR` との比較）。今回は
   TARGET_DIR が別リポジトリのため発火しないはずだが、実行結果のログでガードが誤発火/不発火して
   いないことを目視確認する。
5. **権限は最小限**: `alpha-predict-jp` 内で行うのは上記ファイル作成・symlink 作成のみ。
   モデル・データ・スクリプト等の既存ファイルには一切触れない。`git add` は新規作成ファイルのみを
   個別指定し、`git status` で untracked の `src/config.py.bak` 等を巻き込んでいないか確認してから
   コミットする。
6. **push しない**: `alpha-predict-jp` は実運用中の別プロダクトのリポジトリのため、コミットは
   ローカルブランチ（例: `feat/hq-agents-deploy`）に留め、`origin` への push はオーナー確認後に行う
   （agent-crew 側の「スプリント完了後は自動push」ルールは agent-crew 自身にのみ適用され、
   他プロダクトリポジトリには適用しない）。
7. **失敗時の復元手順**: 新規作成ファイル・symlink のみのため、問題があれば作成したファイル・
   symlink を `rm` するだけで復元可能（既存ファイルの上書きが発生しない設計のため）。
   念のため作業前に `git status` の出力をタスク notes に記録しておくこと。

**#7 invest-dept-hq-deploy-qa（Sora, M）**
コードレビューのみで済ませず実機実行で確認する（agent-crew-sprint-25-reliability-001 準拠）。
確認項目: (a) dry-run と実実行の出力差分が期待通りか、(b) 生成された symlink が実際に
`agent-crew`（本リポジトリ）側の実体を指しているか（`readlink` で確認）、(c) alpha-predict-jp の
既存ファイル（3スキル・settings.json・settings.local.json・CLAUDE.md 等）が一切変更されていないか
（`git status` / `git diff` で確認）、(d) 自己参照ガードが今回発火していないことの確認、
(e) `alpha-predict-jp` 側の変更が push されずローカルブランチに留まっていることの確認。

**#5 lessons-issue-sync-fix（Riku, S）**
`~/.claude/_lessons.json` で `issue_url == null` だが実際には GitHub Issue が起票済みの
lesson_id を特定し `issue_url` を書き戻す。特定方法: `gh issue list` の本文（`lesson: <lesson_id>`
の記述）と `_lessons.json` の `lesson_id` を突合する。sprint-26-retro.md が列挙した
sprint-23〜25 の12件のうち、経営会議2026-08-02時点で「10件は既に #129〜#141 として起票済み」
と判定されている（未起票は sprint-23 の2件のみで、これは #149・#150 として本スプリント計画時点で
既に起票済み）。実際に `gh issue list` と `_lessons.json` を突合し、対応するIssue番号を
特定した上で `issue_url` フィールドを更新すること（想像で決め打ちしない）。
あわせて `.claude/agents/retro.md` に「Issue化時は `_lessons.json` の `issue_url` を
その場で書き戻す」手順を明記し、今後の再発を防ぐ。

## 並列化できるもの

- #1・#2・#3（Alexの3設計タスク）は相互依存なく並列可能。
- #4（Tomo）・#5（Riku）は #1〜#3 と並行して着手可能（依存なし）。
- #6（Riku, #2完了後）は #4・#5 と並行できる。

## 確認事項

- [ ] pm-learned-rules.md 反映: `priority_score >= 6` の未対処エントリのうち、Issue化・実装未了は
      agent-crew-sprint-26-tooling-001（#144として本スプリントに反映済み）のみ。その他の
      priority>=6エントリ（sprint-24/25由来）は既に対応済み（`status`欄なしのため形式上openだが
      DECISIONS.md記録上は実装完了）。sprint-25-reliability-001（symlink自己参照ガード・実機QA）は
      タスク#4/#7のnotesに明示反映した。
- [ ] 経営会議判断の反映: 2026-08-02第2回経営会議の委任決裁3件（投資部門準備着手/積み残し起票/Issue #144）
      すべてタスク化済み（#1・#4が準備着手、#5が起票関連の後処理、#2・#6がIssue #144）。
- [ ] 計画重複タスク: なし（sprint-26は全14タスクDONE、実装済み内容と本スプリントタスクに重複なし）。
- [ ] DECISIONS.md 反映: sprint-26のDECISIONS.md本体への追記は未実施（`docs/sprints/sprint-26-retro.md`
      のみに記録されている）。本スプリントのタスクスコープには含めず、次回レトロ時にみゆきちへ
      「DECISIONS.md本体への転記」を申し送り事項として引き継ぐ。
- [ ] フック関連タスクの権限: 対象なし（本スプリントにフック新設タスクなし）。
- [ ] docs/org/ 相互参照チェック: 実施済み（`constitution.md` → `departments.md` / `templates/project-charter.md` /
      `weekly-council.md`、`departments.md` → `.claude/agents/coo.md` / `ADR-014` / `constitution.md` /
      `templates/project-charter.md`、`weekly-council.md` → `docs/org/council/YYYY-MM-DD-queue.md`(パターン)、
      `coo.md` → 同上3件。すべて実在確認済み、一方向連携の問題なし）。
- [ ] 外部リポジトリ由来のlesson確認: `~/.claude/_lessons.json` の `source_repo` 判定で当初3件を
      「外部由来」と誤検出したが、原因は `source_repo` が `https://github.com/Andryu/agent-crew`
      形式で保存されているのに対し、`git remote get-url origin` は `git@github.com:Andryu/agent-crew.git`
      (SSH形式)を返すための文字列不一致（誤判定）。全件 `agent-crew` 自身が起源であり、真の外部
      リポジトリ由来lessonは存在しない。pm.mdステップ0.7のスクリプト例はURL形式の正規化
      （SSH/HTTPS両対応）が必要という気づきを得た。次回改善候補として記録。
- [x] 監査スキャン（audit-scan.sh）: 本計画書作成後に `--sprint sprint-27` で実行済み（下記参照）。

## 事前チェック結果

- `scripts/audit-scan.sh --sprint sprint-27` 実行結果（2026-08-02、対象コミット923edcd）: **総合判定 PASS**
  - permissions.allow 整合性: PASS（本スプリントの新規タスクに `permissions.allow` へ追加すべき新規
    コマンドパターンはなし。既存の `Write(**)` / `Bash(git *)` / `Bash(gh issue *)` 等で足りる。
    alpha-predict-jp 側への書込みは Bash 経由のファイル操作であり、agent-crew の
    `permissions.allow` はスコープ外＝当該プロジェクト側の権限設定に従う）
  - symlink 健全性: PASS（該当なし）
  - hooks 構文・生存確認: WARNING 1件（`enforce-retro-stop.sh` 内の `echo` コマンドが未知形式として
    検知されたのみで、既知の偽陽性。sprint-26でも同様のWARNINGが出ており実害なし）

## インシデント記録（Sprint-27実行中・2026-08-02）

**#1 queue.py auto_close_issue によるPR誤クローズ**

Alexが `invest-dept-charter` タスクを `queue.sh done` した際、`scripts/queue.py` の
`auto_close_issue` 関数がタスク notes 内の参照テキスト「PR151」（本編集前は「PR #151」表記）を
Issue番号だと誤認し、`gh issue close 151` を実行してオーナーの戦略レビュー待ちだった PR151
（feat/strategy-2026h2）を誤ってクローズした。Alexが即座に `gh pr reopen 151` で復旧し、
状況説明コメントを追加。実害はレビュー体験への一時的な混乱のみで、レビュー内容自体への影響はなし。

根本原因: `re.search(r'#(\d+)', task.notes or "")` が notes 内で最初に出現する任意の
「#数字」に無条件でマッチし、Issue/PRの区別なく `gh issue close` を実行する設計。
Issue152として起票し、`queue-qa-reguard-design`（Issue144設計）のスコープに是正方針を統合した
（risk_levelをmediumからhighへ引き上げ）。

**再発防止（本スプリント内で即時対応済み）**: `_queue.json` の残タスク（当時IN_PROGRESS/未着手だった
`queue-qa-reguard-design` / `governance-doc-149-150` / `lessons-issue-sync-fix`）のnotesを
点検したところ、同型の誤爆リスク（Issue144の時期尚早クローズ、Issue149のみクローズされ
Issue150が取り残される非対称挙動、無関係なIssue129の誤クローズ）が実際に存在することを確認し、
`#<数字>` 表記を安全な表記（例: `Issue144`）に置換して恒久修正までのブリッジとした。

**教訓化の申し送り**: sprint27-retro にて lesson として記録すること。特に「サブエージェントへの
指示文・notes内の自由記述に含まれる `#<数字>` 表記が、実行系のパターンマッチによって意図しない
副作用（自動クローズ等）を引き起こしうる」という一般化可能な教訓であり、pm-learned-rules.md への
反映を検討する。

---

| バージョン | 日付 | 変更 |
|-----------|------|------|
| v1.0 | 2026-08-02 | Sprint-27 計画初版（Yuki） |
| v1.1 | 2026-08-02 | インシデント記録追加（auto_close_issue誤爆、Issue152起票、_queue.json是正）（Yuki） |
