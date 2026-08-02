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

`invest-dept-charter`完了時にqueue.pyの`auto_close_issue`がnotes内の参考記述「PR #151」を誤認し、オーナーの戦略レビュー待ちだったPR #151を誤クローズするインシデントが発生した。Alexが即座に`gh pr reopen 151`で復旧し、Yukiが`_queue.json`の残タスクを全件機械点検して同型の誤爆リスク3件（`queue-qa-reguard-design`・`governance-doc-149-150`・`lessons-issue-sync-fix`）を事前に無害化した。さらに調査によりSprint-26中にもIssue #139/#140/#141が同機構で早期クローズされていたことが判明した（最終状態は妥当でreopen不要と判定）。Issue #152として起票し、進行中だったIssue #144の設計・実装スコープに統合、`close_issue`専用フィールド＋`close_linked_issue`関数への置き換えでnotes正規表現参照を完全廃止し、pytest 40件全パスでQA承認まで同一スプリント内に完結させた（`agent-crew-sprint-27-reliability-001`、Issue #152クローズ済み）。

### architect.mdセルフチェック制度の即日効果

`governance-doc-149-150`（Issue #150）で導入したばかりの設計完了時セルフチェック（条件分岐の網羅性・文書内§間の整合性）が、同一スプリント内の別タスク`queue-qa-reguard-design`で即座に機能した。Alexが自己チェックの過程で既存pytest 7件がdoneコマンド側の新設QAガードと衝突する矛盾を自力で検出し、diff付きで修正方針を設計書に明記した（`agent-crew-sprint-27-design-001`）。

### その他の機械的突合・点検の有効性

Riku（`lessons-issue-sync-fix`）が想定10件を上回る16件のissue_url同期是正を`gh issue list`との機械突合で完遂し、Sora（`invest-dept-hq-deploy-qa`）は実機実行によるsymlink実体解決・diff範囲・push状況の確認で計画通りのQAを実施した。Tomoの別リポジトリ（alpha-predict-jp）への初デプロイも、計画notesの手順通り既存資産無傷・push保留で完遂した。

---

## 失敗パターン（Problem）

### 二重指揮の衝突（最重要教訓）

team-lead(Fable)がスプリント進行中にPM(Yuki)を経由せずRiku(実装担当)へ直接タスク指示（R11差分実装の着手指示）を出し、チームが既に合意していた方針（R11はフォローアップとして別途扱う）と衝突した。YukiがRikuへの指示を2回差し戻す事態となり、Rikuは矛盾する2つの指揮系統の板挟みになった。原因はteam-leadの越権であることを本人が承認済み。最終的にR11はIssue #154として追補タスク化し決着した。スプリント進行中のタスクレベル指示がPMを経由しないルートで発生しうる構造的リスクとして最重要度で記録する（`agent-crew-sprint-27-process-001`、Issue #155）。明文化先（pm.mdの起動プロトコル節か、team-lead向け組織文書か）は次スプリントで確定する。

### 命名往復（issue_ref vs close_issue）

`queue-qa-reguard-impl`実装時、issue_ref(Yukiの当初理解・Rikuの初期実装)とclose_issue(Alexの設計書の最終命名)のあいだで2往復の同期修正が発生した。設計と実装が並行に近い形で進んだ結果、命名確定前に実装が着手され、summary文言の訂正がSora QAの指摘を待つ形になった（実装内容自体はQA時点で最終版と一致）（`agent-crew-sprint-27-process-002`）。

### macOS readlink -f非対応（複数担当が独立に重複発見）

symlinkの実体解決に`readlink -f`を使う検証手順が、macOS標準のBSD readlinkでは`-f`オプション非対応であるため機能しない。Tomo(`invest-dept-hq-deploy`)とSora(`invest-dept-hq-deploy-qa`)の両方が独立に同一問題を発見し、それぞれpython3のrealpathで代替検証を行う重複コストが発生した（`agent-crew-sprint-27-reliability-002`、Issue #156）。

### pm.mdステップ0.7のsource_repo URL形式不一致

外部リポジトリ由来lesson確認で当初3件を「外部由来」と誤検出した。原因は`_lessons.json`のsource_repoがHTTPS形式で保存されているのに対し、`git remote get-url origin`はSSH形式（`git@github.com:...`）を返すための文字列不一致。実際に突合した結果、全件がagent-crew自身が起源であり真の外部由来lessonは存在しなかった（実害なし、`agent-crew-sprint-27-tooling-001`）。

---

## 記録した Lesson

| lesson_id | 概要 | priority | scope |
|-----------|------|---------|-------|
| agent-crew-sprint-27-reliability-001 | auto_close_issueの自由記述マッチ誤爆パターン（恒久対応済み・一般原則） | 6 | project |
| agent-crew-sprint-27-process-001 | 二重指揮の衝突（team-lead越権、最重要） | 9 | project |
| agent-crew-sprint-27-process-002 | 命名往復（issue_ref vs close_issue） | 2 | project |
| agent-crew-sprint-27-reliability-002 | macOS readlink -f非対応 | 6 | global |
| agent-crew-sprint-27-tooling-001 | pm.mdステップ0.7のsource_repo URL形式不一致 | 2 | global |
| agent-crew-sprint-27-design-001 | architect.mdセルフチェック制度の即日効果（成功パターン） | 1 | project |

合計: 6件

---

## Issue化結果

エビデンスゲート（priority_score >= 4 かつ evidence 1件以上かつ issue_url == null）通過:

| lesson_id | 判定 | 理由 |
|-----------|------|------|
| agent-crew-sprint-27-process-001 | Issue化 | priority=9・evidenceあり |
| agent-crew-sprint-27-reliability-002 | Issue化 | priority=6・evidenceあり |
| agent-crew-sprint-27-reliability-001 | 対象外（見送り） | priority=6・evidenceありだがIssue #152が既に同一内容をカバーしており重複のため既存Issueにissue_urlを紐付け |

- 作成: 2件
  - https://github.com/Andryu/agent-crew/issues/155: [lesson] スプリント進行中のタスク指示はPM経由に一本化する（team-lead越権防止）
  - https://github.com/Andryu/agent-crew/issues/156: [lesson] symlink検証手順にmacOS(BSD readlink)非対応を明記する
- 保留: 2件（priority_score < 4）

### 保留 lesson（バックログ候補）

- `agent-crew-sprint-27-process-002`（priority 2）: 命名往復。優先度が低いため見送り。
- `agent-crew-sprint-27-tooling-001`（priority 2）: source_repo URL形式不一致。優先度が低いため見送り。ただしpm.mdステップ0.7の改善は次スプリントの軽微タスクとして推奨。

### 付随対応

- Issue #152（auto_close_issue誤爆インシデント）: 実装は`agent-crew-sprint-27-reliability-001`の対応としてIssue #144に統合済みだったがOPENのまま残っていたため、本レトロで確認しクローズした。

---

## ルール書き出し結果

- 追加: 3件（`.claude/agents/pm-learned-rules.md`）
  - `agent-crew-sprint-27-reliability-001`: [Riku / Alex] 自由記述フィールドへの正規表現マッチで自動アクションを実行する設計を避ける
  - `agent-crew-sprint-27-process-001`: [Yuki / team-lead] スプリント進行中のタスクレベル指示はPM経由に一本化する
  - `agent-crew-sprint-27-reliability-002`: [全エージェント] symlink検証手順ではmacOS(BSD readlink)の非対応を前提にする
- スキップ（重複）: 0件
- スキップ（priority < 3）: 2件（`agent-crew-sprint-27-process-002`・`agent-crew-sprint-27-tooling-001`、いずれもpriority=2）

---

## その他の対応事項

- **DECISIONS.md本体への転記漏れ解消**: sprint-26分（積み残し申し送り）とsprint-27分の両方を`docs/DECISIONS.md`に追記した。

---

## 次スプリントへの改善優先事項

1. **二重指揮の衝突の恒久対策**（最優先・Issue #155）: 「スプリント進行中のタスクレベル指示はPM経由に一本化、team-leadは方針決定のみ」を明文化する。pm.mdの起動プロトコル節に追記するか、team-lead向けの組織文書を新設するかを次スプリント冒頭で判断する。
2. **macOS readlink非対応の横展開**（Issue #156）: 既存の手順書（install.sh関連の検証手順等）を棚卸しし、`readlink -f`を使用している箇所にmacOS非対応の注記を追加する。
3. **pm.mdステップ0.7のsource_repo URL正規化**（`agent-crew-sprint-27-tooling-001`）: SSH/HTTPS両形式に対応する比較ロジックを実装する。
4. **設計と実装の並行時の命名同期**（`agent-crew-sprint-27-process-002`）: 実装着手後に命名変更が生じた場合、summary等の記録も含めて設計書の最終命名と即座に突合するQA項目を検討する。
