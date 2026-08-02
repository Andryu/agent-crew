# Sprint-27 レトロスペクティブ

- 実施日: 2026-08-02
- 担当: みゆきち（retro エージェント）
- スプリント: sprint-27（投資部門の開設準備 + 教訓台帳の信頼性回復、ブランチ feat/sprint-27）

---

## ルーブリックスコア

| 評価軸 | スコア | 合格基準 | 判定 |
|--------|--------|---------|------|
| 仕様明確度 | 1.00 | >= 0.8 | PASS |
| QA合格率 | 1.00 | >= 0.9 | PASS |
| ブロック率 | 0.00 | <= 0.1 | PASS |
| 負荷分散（ポイントベース・公式） | 1.94 | <= 2.0 | PASS |
| 負荷分散（タスク数ベース・補助） | 1.5 | 参考値 | — |

> FAIL 軸: なし。全4軸PASS。負荷分散スコア1.94は基準ちょうど手前で、計画時点の見積もり（`sprint-points.sh --md`実行結果、2026-08-02）と一致しており計画時点から偏りが把握できていた。

### enforce-retro-stop.sh 実戦検証（ステップ6.5）

本スプリントに実戦検証タスクの新規計上はなし。Sprint-26の `retro-stop-hook-live-check` で実施済みの結果を引用する（引用可の運用に従う）。

- 発動確認（隔離環境）: PASS — 一時ディレクトリの疑似gitリポジトリ＋疑似`_queue.json`（実装タスクDONE・レトロタスクTODO）で、引数なし起動・stdin JSON形式を模した起動の両方でStopフックの警告がstderrに出力されることを確認済み。
- 誤検知チェック（実リポジトリ）: なし — 非DONEタスクが残存する状態の実リポジトリで警告が出力されないことを確認済み。
- 発見事項（Sprint-26時点）: `enforce-retro-stop.sh` はstdinのセッション文脈情報を読み取らず、`git rev-parse --show-toplevel` と `.claude/_queue.json` / `docs/sprints/<sprint>-retro.md` のファイル存在確認のみで判定している。実害なし。

---

## スプリント概要

- タスク数: 10（全DONE）
- retry_count合計: 0
- BLOCKEDタスク: 0
- QA対象: 3タスク（invest-dept-hq-deploy-qa・queue-qa-reguard-qa・sprint27-qa、いずれもAPPROVED）
- インシデント発生・当日中に恒久修正・QA承認まで完結（後述）
- 教訓の宝庫となったスプリントであり、Yuki（PM）から追加の教訓化ポイント（設計書更新の作法・完了タスクへの無断仕様追加・未コミット作業の放置）の申し送りを受け、当初記録の6件から8件へlessonを拡充した。

### 担当者内訳

| エージェント | タスク数 | ポイント |
|-------------|---------|---------|
| Sora | 3 | 7 |
| Riku | 2 | 4 |
| Alex | 3 | 3 |
| Tomo | 1 | 3 |
| みゆきち | 1 | 1 |

総タスク数=10、稼働担当数=5。ポイントベース: 最多7pt（Sora）/平均3.6pt=1.94。

---

## 成功パターン（Keep）

### インシデント発生から根因特定・恒久修正・QA承認までを1スプリント内で完結

`invest-dept-charter`完了時にqueue.pyの`auto_close_issue`がnotes内の参考記述「PR #151」を誤認し、オーナーの戦略レビュー待ちだったPR #151を誤クローズするインシデントが発生した。Alexが即座に`gh pr reopen 151`で復旧し、Yukiが`_queue.json`の残タスクを全件機械点検して同型の誤爆リスク3件（`queue-qa-reguard-design`・`governance-doc-149-150`・`lessons-issue-sync-fix`）を事前に無害化した。さらに調査によりSprint-26中にもIssue #139/#140/#141が同機構で早期クローズされていたことが判明した（最終状態は妥当でreopen不要と判定。Issue #133は無関係でGitHub標準のCloses記法によるものと確定）。Issue #152として起票し、進行中だったIssue #144の設計・実装スコープに統合、`close_issue`専用フィールド＋`close_linked_issue`関数への置き換えでnotes正規表現参照を完全廃止し、pytest 40件全パスでQA承認まで同一スプリント内に完結させた（`agent-crew-sprint-27-reliability-001`、Issue #152クローズ済み）。

### architect.mdセルフチェック制度の即日効果

`governance-doc-149-150`（Issue #150）で導入したばかりの設計完了時セルフチェック（条件分岐の網羅性・文書内§間の整合性）が、同一スプリント内の別タスク`queue-qa-reguard-design`で即座に機能した。Alexが自己チェックの過程で既存pytest 7件がdoneコマンド側の新設QAガードと衝突する矛盾を自力で検出し、diff付きで修正方針を設計書に明記した（`agent-crew-sprint-27-design-001`）。

### その他の機械的突合・点検の有効性

Riku（`lessons-issue-sync-fix`）が想定10件を上回る16件のissue_url同期是正を`gh issue list`との機械突合で完遂し、Sora（`invest-dept-hq-deploy-qa`）は実機実行によるsymlink実体解決・diff範囲・push状況の確認で計画通りのQAを実施した。Tomoの別リポジトリ（alpha-predict-jp）への初デプロイも、計画notesの手順通り既存資産無傷・push保留で完遂した。

---

## 失敗パターン（Problem）

### 二重指揮の衝突（最重要教訓）

team-lead(Fable)がスプリント進行中にPM(Yuki)を経由せずRiku(実装担当)へ直接タスク指示（R11差分実装の着手指示）を出し、チームが既に合意していた方針（R11はフォローアップとして別途扱う）と衝突した。YukiがRikuへの指示を2回差し戻す事態となり、Rikuは矛盾する2つの指揮系統の板挟みになった。原因はteam-leadの越権であることを本人が承認済み。最終的にR11はIssue #154として追補タスク化し決着した。スプリント進行中のタスクレベル指示がPMを経由しないルートで発生しうる構造的リスクとして最重要度で記録する（`agent-crew-sprint-27-process-001`、Issue #155）。明文化先（pm.mdの起動プロトコル節か、team-lead向け組織文書か）は次スプリントで確定する。

### 完了・QA承認済みタスクへの無断な仕様追加

二重指揮の衝突と表裏一体の別論点として、既にQA承認・Issue #144としてクローズ済みの実装(`queue-qa-reguard-impl`)に対し、design.mdの「未実装・フォローアップ」節に記載されていたR11(gh issue viewによるIssue/PR種別事前検証)を、Rikuが無断で追加実装しようとする動きが複数回(2回停止依頼)発生した。team-leadの直接指示という誘因があったとはいえ、実装担当者が完了・クローズ済みタスクへの追加変更を自己判断で進めてしまった点は独立したリスクであり、「完了したタスクへの変更は新規タスクとして起票する」というルール化が必要（`agent-crew-sprint-27-process-003`、Issue #159）。

### 命名往復（issue_ref vs close_issue）とその根本原因

`queue-qa-reguard-impl`実装時、issue_ref(Yukiの当初理解・Rikuの初期実装)とclose_issue(Alexの設計書の最終命名)のあいだで往復の同期修正が発生した。根本原因はAlexが実装完了後に設計書を拡張した際、実装コード(scripts/queue.py)を直接確認せずnotesの古い表記だけを頼りに書き換えたことで、issue_ref→close_issue→issue_ref(逆行・誤り)→close_issue(是正)と同一論点で複数回の往復が発生した点にある。背景にはエージェント間メッセージの非同期性（送信済みメッセージが相手の現在の作業を即座に止められない）があり、Alexが最新の実装状態を把握しないまま作業を進めてしまった。Alex本人も「次回は実装コードの現状を確認してから設計書を更新する」と振り返っている（`agent-crew-sprint-27-process-002`、Issue #158）。

### 未コミット作業の保護漏れ

`_queue.json`側はqueue.sh doneにより完了記録されていたにもかかわらず、Alex・Rikuの実装成果物（queue.py・tests・agent定義・設計書）が長時間git commitされないまま作業ツリーに残存していた。完了記録と実ファイルのコミット状態が分離しており、セッション中断等が発生すれば成果物が失われるリスクがあった（`agent-crew-sprint-27-reliability-003`、Issue #160）。

### macOS readlink -f非対応（複数担当が独立に重複発見）

symlinkの実体解決に`readlink -f`を使う検証手順が、macOS標準のBSD readlinkでは`-f`オプション非対応であるため機能しない。Tomo(`invest-dept-hq-deploy`)とSora(`invest-dept-hq-deploy-qa`)の両方が独立に同一問題を発見し、それぞれpython3のrealpathで代替検証を行う重複コストが発生した（`agent-crew-sprint-27-reliability-002`、Issue #156）。

### pm.mdステップ0.7のsource_repo URL形式不一致（自己言及的な再発を含む）

外部リポジトリ由来lesson確認で当初3件を「外部由来」と誤検出した。原因は`_lessons.json`のsource_repoがHTTPS形式で保存されているのに対し、`git remote get-url origin`はSSH形式（`git@github.com:...`）を返すための文字列不一致。実際に突合した結果、全件がagent-crew自身が起源であり真の外部由来lessonは存在しなかった（実害なし、`agent-crew-sprint-27-tooling-001`）。皮肉にも、本レトロ自身のlesson記録作業でも同型の不一致が再現した。`git remote get-url origin`がSSH形式を返した結果、sprint-27分の新規lesson6件のsource_repoが他エントリ（HTTPS形式）と異なる形式のまま一度登録されてしまい、後から気づいて修正した。ルール化されたばかりの教訓を記録する当人が直後に同じ落とし穴を踏んだ事例として、機械チェック（正規化ロジック）の必要性を裏付けている。

---

## 記録した Lesson

| lesson_id | 概要 | priority | scope |
|-----------|------|---------|-------|
| agent-crew-sprint-27-reliability-001 | auto_close_issueの自由記述マッチ誤爆パターン（恒久対応済み・一般原則） | 6 | project |
| agent-crew-sprint-27-process-001 | 二重指揮の衝突（team-lead越権、最重要） | 9 | project |
| agent-crew-sprint-27-process-002 | 命名往復（設計書更新時の実装コード未確認・メッセージ非同期性が根本原因） | 6 | project |
| agent-crew-sprint-27-reliability-002 | macOS readlink -f非対応 | 6 | global |
| agent-crew-sprint-27-tooling-001 | pm.mdステップ0.7のsource_repo URL形式不一致 | 2 | global |
| agent-crew-sprint-27-design-001 | architect.mdセルフチェック制度の即日効果（成功パターン） | 1 | project |
| agent-crew-sprint-27-process-003 | 完了・QA承認済みタスクへの無断な仕様追加 | 9 | project |
| agent-crew-sprint-27-reliability-003 | 未コミット作業の保護漏れ | 4 | project |

合計: 8件

---

## Issue化結果

エビデンスゲート（priority_score >= 4 かつ evidence 1件以上かつ issue_url == null）通過:

| lesson_id | 判定 | 理由 |
|-----------|------|------|
| agent-crew-sprint-27-process-001 | Issue化 | priority=9・evidenceあり |
| agent-crew-sprint-27-reliability-002 | Issue化 | priority=6・evidenceあり |
| agent-crew-sprint-27-process-002 | Issue化 | priority=6（Yukiの追加情報により2→6へ見直し）・evidenceあり |
| agent-crew-sprint-27-process-003 | Issue化 | priority=9・evidenceあり（Yuki申し送りによる新規lesson） |
| agent-crew-sprint-27-reliability-003 | Issue化 | priority=4・evidenceあり（Yuki申し送りによる新規lesson） |
| agent-crew-sprint-27-reliability-001 | 対象外（見送り） | priority=6・evidenceありだがIssue #152が既に同一内容をカバーしており重複のため既存Issueにissue_urlを紐付け |

- 作成: 5件
  - https://github.com/Andryu/agent-crew/issues/155: [lesson] スプリント進行中のタスク指示はPM経由に一本化する（team-lead越権防止）
  - https://github.com/Andryu/agent-crew/issues/156: [lesson] symlink検証手順にmacOS(BSD readlink)非対応を明記する
  - https://github.com/Andryu/agent-crew/issues/158: [lesson] 設計書更新は実装コードを直接確認してから行う（命名往復の根本対策）
  - https://github.com/Andryu/agent-crew/issues/159: [lesson] 完了・QA承認済みタスクへの仕様追加は新規タスク起票を必須化する
  - https://github.com/Andryu/agent-crew/issues/160: [lesson] タスク完了後の未コミット作業をPMが定期点検する
- 保留: 1件（priority_score < 4）

### 保留 lesson（バックログ候補）

- `agent-crew-sprint-27-tooling-001`（priority 2）: source_repo URL形式不一致。優先度が低いため見送り。ただしpm.mdステップ0.7の改善は次スプリントの軽微タスクとして推奨。本レトロ自身の記録作業でも再発したため、機械チェック（正規化ロジック）の優先度を再考する余地あり。

### 付随対応

- Issue #152（auto_close_issue誤爆インシデント）: 実装は`agent-crew-sprint-27-reliability-001`の対応としてIssue #144に統合済みだったがOPENのまま残っていたため、本レトロで確認しクローズした。
- `agent-crew-sprint-27-process-002`のpriorityは、Yuki（PM）からの追加申し送り（設計書更新時の実装コード未確認・メッセージ非同期性という根本原因の解明）を受けて当初のseverity=1/frequency=2（priority=2）からseverity=2/frequency=3（priority=6）へ見直し、evidenceゲート通過に伴い追加でIssue化した。
- 6件のsprint-27新規lesson登録時、`source_repo`がSSH形式のまま保存される不備（`agent-crew-sprint-27-tooling-001`と同型）が発生していたことに気づき、全件をHTTPS形式に修正した。

---

## ルール書き出し結果

- 追加: 6件（`.claude/agents/pm-learned-rules.md`）
  - `agent-crew-sprint-27-reliability-001`: [Riku / Alex] 自由記述フィールドへの正規表現マッチで自動アクションを実行する設計を避ける
  - `agent-crew-sprint-27-process-001`: [Yuki / team-lead] スプリント進行中のタスクレベル指示はPM経由に一本化する
  - `agent-crew-sprint-27-reliability-002`: [全エージェント] symlink検証手順ではmacOS(BSD readlink)の非対応を前提にする
  - `agent-crew-sprint-27-process-002`: [Alex / 全エージェント] 設計書更新は実装コードを直接確認してから行う
  - `agent-crew-sprint-27-process-003`: [Riku / 全エージェント] 完了・QA承認済みタスクへの仕様追加は新規タスク起票を必須とする
  - `agent-crew-sprint-27-reliability-003`: [Yuki] タスク完了後の未コミット作業を定期的にgit statusで点検する
- スキップ（重複）: 0件
- スキップ（priority < 3）: 1件（`agent-crew-sprint-27-tooling-001`、priority=2）

---

## その他の対応事項

- **DECISIONS.md本体への転記漏れ解消**: sprint-26分（積み残し申し送り）とsprint-27分の両方を`docs/DECISIONS.md`に追記した。sprint-27節はYukiからの追加申し送りを受けて失敗パターン・次スプリント推奨を拡充した。

---

## 次スプリントへの改善優先事項

1. **二重指揮の衝突の恒久対策**（最優先・Issue #155）: 「スプリント進行中のタスクレベル指示はPM経由に一本化、team-leadは方針決定のみ」を明文化する。pm.mdの起動プロトコル節に追記するか、team-lead向けの組織文書を新設するかを次スプリント冒頭で判断する。
2. **完了・QA承認済みタスクへの追加実装ルール**（Issue #159）: engineer各種.mdに「クローズ済みIssue・QA承認済みタスクへの追加実装は新規タスク起票が必須」と明記する。
3. **設計書更新時の実装コード確認ルール**（Issue #158）: architect.md等に「実装完了後の設計書追記時は対象の実装コードを直接確認する」を明記する。
4. **未コミット作業の定期点検**（Issue #160）: PMのスプリント進行手順に、並列フェーズの節目ごとの`git status`確認・中間コミット運用を追加する。
5. **macOS readlink非対応の横展開**（Issue #156）: 既存の手順書（install.sh関連の検証手順等）を棚卸しし、`readlink -f`を使用している箇所にmacOS非対応の注記を追加する。
6. **pm.mdステップ0.7のsource_repo URL正規化**（`agent-crew-sprint-27-tooling-001`）: SSH/HTTPS両形式に対応する比較ロジックを実装する。本レトロ自身での再発を踏まえ、retro.md側のlesson登録手順にも同様の正規化を組み込むことを検討する。
