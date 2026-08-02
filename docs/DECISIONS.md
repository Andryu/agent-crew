# DECISIONS — agent-crew

スプリント完了時に自動追記される判断・学習・失敗パターンの記録。
次スプリント計画時に Yuki が参照する。

---

## sprint-02 — 2026-04-20

### アーキテクチャ判断
- slack-persona-design: 設計ドキュメント作成完了
- portable-install-design: 設計ドキュメント作成完了
- phase1-parallel-design: 設計ドキュメント作成完了
- phase1-multistack-design: 設計ドキュメント作成完了
- phase1-complexity-design: 設計ドキュメント作成完了
- phase2-intelligence-design: 統合設計ドキュメント作成完了

### 学び
- なし

### 失敗パターン
- なし

### 次スプリントへの推奨
- なし
- 特記事項なし

---

## sprint-10 — 2026-04-24

### アーキテクチャ判断

- **queue.sh → queue.py 委譲方針確定（delegate-design.md §2 §4）**: `graph` / `parallel-handoff` / `retro` の3コマンドは Bash 実装を維持する。`retro --save --decisions` は queue.py に未実装のため、Bash 実装を残す（委譲対象から除外）。委譲はアトミックに行い、ロック方式の競合を防ぐ。
- **complexity連動 MAX_RETRY 確定（Issue #58）**: S=2 / M=3 / L=5。null はデフォルト 3 にフォールバック。queue.py の retry コマンドに実装済み、pytest で検証済み。

### 学び

- _signals.jsonl の全タスクシグナル記録が Sprint-10 で初めて正常確認された。Sprint-08 の `${4:-{}}` バグ修正・Sprint-09 の queue.py 移植が効いている。
- 設計書（delegate-design.md）が互換リスク・コマンドルーティング表・必須対応・ロールバック手順を網羅したことで、Riku の実装が最小手戻りで完了した。設計への投資が実装品質に直結するパターンを確認。
- QA（Sora）が emit_signal グローバル変数参照問題を MINOR として記録しながら APPROVED を出した。Sprint-08 の「QA形骸化」問題が解消されていることを確認。
- テストスイートが 18 → 23 件に増加。回帰テストの蓄積が進んでいる。

### 失敗パターン

- **計画重複**: `delegate-impl` の大半（ディスパッチ委譲・complexity バリデーション・qa冪等性ガード）が Sprint-09 で完了済みだったことが実装着手後に発覚した。Yuki がスプリント計画時に前スプリントの実装完了状態を確認していなかったことが根因。start → done の elapsed 時間が5秒だったことが事後的に確認できた（_signals.jsonl）。

### 次スプリントへの推奨

- Yuki はスプリント計画作成前に、前スプリント DONE タスクの実装状態を確認し「計画済みだが未実装」と「実装済みだが未計画」の両方を洗い出す。
- pm.md の計画手順チェックリストに「前スプリントの実装完了状態の突合」を追加することを検討する（lesson: agent-crew-sprint-10-process-001）。
- engineer-go 停止（Issue #64）は Sprint-10 で発生しなかったが、引き続き大規模タスクでは注意が必要。

---

## sprint-11 — 2026-04-24

### アーキテクチャ判断

- **queue.sh レガシー Bash 実装の削除完了**: Sprint-09 の委譲完了後も残っていたデッドコード（cmd_start / cmd_done 等の関数定義・acquire_lock・共通ヘルパー群）を削除し、queue.sh を 1090行から 404行（63%削減）の軽量シンラッパーに変換した。queue.py が単一の信頼源となった。
- **graph コマンドの Python 化完了**: queue.py に `graph` Click サブコマンドを追加。Mermaid flowchart 出力・`--save` オプション（docs/graphs/<sprint>.md 生成）・queue.sh からの委譲が正常動作。pytest が 23→27件に増加。
- **フィードバックループ設計書の完成（docs/spec/feedback-loop-doc.md）**: Yuki のスプリント計画前確認フローをコマンド付きで定義。elapsed < 60秒の計画重複検出ロジックを含む。

### 学び

- 設計書（legacy-delete-design.md / graph-py-design.md）が削除対象・ロールバック手順・テストケースを網羅したことで、実装が最小手戻りで完了した。Sprint-10 に続き「設計への投資が実装品質に直結する」パターンを再確認。
- queue.sh 63% 削減により、今後の Bash 実装残存コマンド（retro・parallel-handoff）の見通しが改善された。
- テストスイートが 23 → 27 件に拡充。Python 化の進行に伴い自動テストのカバレッジが出向している。

### 失敗パターン

- **Riku レート制限中断**: `legacy-delete-impl`（L タスク）完了直後に Riku がレート制限に到達し、後続引き継ぎがメインセッション代行になった。L タスクを連続して処理した後のレート枯渇リスクへの配慮が計画時に不足していた。
- **Sora Bash 上限による QA 代替**: `legacy-delete-qa` / `graph-py-qa` で Sora が Bash 実行上限に達し、スモークテストを静的検証で代替。キュー更新もメインセッション代行。QA エージェントが実際のコマンドを実行せずに APPROVED を出す状態が発生した（Sprint-08 QA形骸化の再現）。
- **レトロ起動スキップ（5スプリント連続）**: Sora がスプリント完了時のレトロ起動を実行せず、オーナーが手動対応。pm.md への記載という対策が効果を発揮しておらず、Sora のエージェント定義への直接埋め込みが必要と判断。

### 次スプリントへの推奨

- Sora のエージェント定義（sora.md）に「全タスク DONE 時は完了報告末尾に @retro を含める」を直接記載する（pm.md 参照では不十分と確認済み）。
- Sora の QA 手順に「Bash 不可の場合は CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）を返す」を追加し、メインセッション代行時に performed_by フラグを _queue.json に記録する。
- Yuki は Riku の担当タスクで L タスクを1スプリント1件までに制限する計画ルールを pm.md に追加する。
- priority_score >= 6 の未対処 lesson: agent-crew-sprint-11-reliability-002（Sora Bash上限QA）, agent-crew-sprint-11-process-001（レトロ自動起動）を次スプリント計画に反映する。

---

## sprint-15 — 2026-04-26

### アーキテクチャ判断

- **engineer-go 停止バグ対処方針の実装完了（Issue #64）**: 5スプリント積み残しだった根本対策を実装。engineer-go.md にコンテキスト超過防止ルール（参照ファイル3件上限・200行超は offset/limit使用・複雑度L委譲禁止）、pm.md に委譲前チェックリスト（5項目）を追記。
- **lessons → agent .md 自動 PR 提案フロー確立（Issue #59）**: `scripts/propose-lesson-rules.sh` を新規作成。`--dry-run` / `--min-priority` オプション対応。category → エージェントマッピングで自動分類し、重複防止チェックの上 Draft PR を作成する。settings.json Stop hook で `--dry-run` を自動実行（差分レポートを STDOUT 出力）。スプリント完了フローにステップ3.5として組み込み。
- **QA summary 記録義務の明文化（Issue #67）**: qa.md の DoD に「実行コマンドと出力結果を summary に記録する」を追加。完了報告フォーマットのテスト結果セクションを実出力記録必須形式に変更。禁止事項に「テスト実行なしの DONE」を明示。

### 学び

- Phase-1 並列設計（Alex×2 + Riku×1）が計画通り機能し、retry ゼロ・BLOCKED ゼロで全6タスク完了した。設計と実装を同一フェーズで並行処理する計画構造が有効と確認。
- `propose-lesson-rules.sh --dry-run` のスモークテストで 18件の未対処 lesson が検出された。lesson の蓄積量が PR 提案フローの実用水準に達していることを確認。次スプリントでの実際の PR 作成が推奨される。
- `scripts/lessons.sh` が settings.json の permissions に未登録であることが判明（`Bash(scripts/lessons.sh *)` パターンが未許可）。retro ステップでの lesson 記録が実行できなかった。

### 失敗パターン

- **Bash 許可パターンの相対パス限定**: settings.json の `Bash(scripts/queue.sh *)` は相対パスのみ一致し、絶対パス（/Users/...）では権限拒否になる。スプリント開始直後に発生し、相対パスに変更することで即時解消した。
- **lessons.sh が permissions 未登録**: `scripts/lessons.sh` が `permissions.allow` に含まれておらず、retro フェーズでの lesson 記録（`lessons.sh add`）が実行できなかった。DECISIONS.md での代替記録で対応した。

### 次スプリントへの推奨

- settings.json の `permissions.allow` に `Bash(scripts/lessons.sh *)` を追加し、lessons.sh を利用するフローを有効化する。
- `scripts/propose-lesson-rules.sh`（`--dry-run` なし）を実行して、蓄積済み 18件の lesson を対象エージェント .md へ実際に反映する Draft PR を作成する。
- pm-learned-rules.md に Sprint-15 の2件の新規 lesson（Bash絶対パス問題・lessons.sh未登録）を追記する（priority_score=4 のため対象）。

---

## sprint-16 — 2026-04-26

### アーキテクチャ判断

- **lessons.sh を permissions.allow に登録完了（Sprint-15 失敗パターン修正）**: `settings.json` の `permissions.allow` に `Bash(scripts/lessons.sh *)` を追加。retro フェーズでの lesson 記録が正式に自動化フローに組み込まれた。
- **propose-lesson-rules.sh 初の本番実行（Issue #59 完全完了）**: 蓄積済み 20件の lesson（priority_score>=4）を `engineer-go.md`・`pm.md` の「禁止パターン」セクションへ自動反映し、Draft PR #93 を作成した。設計（Sprint-15）→ 実装（Sprint-15）→ 本番実行（Sprint-16）の3スプリントに渡るフローが完結した。
- **pm-learned-rules.md に Bash相対パス・permissions事前登録ルールを追記**: Sprint-15 の失敗パターン2件をルール化し記録。Issue #95・#96 として Issue 化済み。

### 学び

- 後処理スプリント（Sprint-16）を設けることで、Sprint-15 の積み残し（lesson 記録・本番実行）を確実に完了できた。スプリント間のバトンタッチが機能している。
- `propose-lesson-rules.sh` が独立ブランチ（fix/lesson-rules-YYYYMMDD）を作成する設計により、Sprint-16 ブランチ（feat/sprint-16）を汚染せずに lesson PR を並行管理できた。

### 失敗パターン

- なし（retry_count=0、BLOCKED=0）

### 次スプリントへの推奨

- Draft PR #93（fix/lesson-rules-20260426）をオーナーがレビューしてマージする。マージ後、対応 lesson の status を `implemented` に更新する。
- Issue #36（サブエージェントのトークン消費最適化）、Issue #61（TaskCompleted/PreToolUse hookの活用）などのオープン Issue から次スプリントのゴールを選定する。
- `propose-lesson-rules.sh` 実行後にブランチが fix/lesson-rules-YYYYMMDD に切り替わり、feat/sprint-XX ブランチに戻る必要がある（スクリプトは自動で戻るが確認が必要）。次回実行時も同様の挙動を想定すること。

---

## sprint-26 — 2026-08-02

### アーキテクチャ判断

- **軽量機能仕様書ADR（SDD仕様積層）の制度化**: `docs/spec/*.md` による設計→実装のブリッジ工程を正式なワークフローとして確立し、Kai定常スキャン（`scripts/audit-scan.sh`）と queue.sh done漏れの構造的対策（SubagentStopフック `enforce-queue-done-stop.sh`）を同一スプリントで実装した。
- **queue.py の qa_result 上書き不可仕様に伴う retry_count 汚染を発見**: QA再判定（CHANGES_REQUESTED→修正→APPROVED）を記録する正規経路が `retry` コマンドしかなく、意味の異なる2種類のリトライが同一カウンタに混在する構造的問題を特定（`agent-crew-sprint-26-tooling-001`）。
- **負荷分散スコアのポイントベース公式化を pm-estimation.md に反映完了**（Issue #140）。

### 学び

- Alex作成の設計書内不整合（`QUEUE_FILE` 参照方法の齟齬）をRikuが実装時に能動的に検知・是正し、CRITICAL/MAJORなしでAPPROVEDとなった。設計→実装の橋渡しで実装者が受動的に転記せず矛盾を是正する成功パターンを確認（`agent-crew-sprint-26-design-001`）。
- vault側のADR索引（`~/Workspace/Obsidian/decisions/agent-crew-adr-index.md`）が実リポジトリの状態とズレており、未コミット文書を「実在する」と誤判定するリスクが顕在化した（`agent-crew-sprint-26-process-001`）。

### 失敗パターン

- 新設した `audit-scan.sh` が、同一スプリントで新設されたSubagentStopフックを判定パターンにマッチさせられず自己参照的にすり抜ける問題がsprint26-qaでMAJORとして検出された（`agent-crew-sprint-26-reliability-001`）。
- みゆきち自身が `retro-stop-hook-live-check` タスクのnotesに明記された「retro.mdへの手順追記」要求を見落とし、実戦検証のみで完了報告した（`agent-crew-sprint-26-process-003`）。
- `gh issue create` がAuto Mode分類器によりブロックされ、team-leadへの代行依頼で対応した（原因調査は継続課題）。

### 次スプリントへの推奨

- queue.py に `qa --force` オプション、または done側の再QA記録ガード改善を実装する（Sprint-27で対応・Issue #144としてクローズ済み）。
- sprint-23〜25の未Issue化lesson12件の棚卸しを行う（Sprint-27で対応・issue_url同期是正として解消済み）。
- DECISIONS.md本体への本スプリント分の転記（本追記で解消）。

---

## sprint-27 — 2026-08-02

### アーキテクチャ判断

- **queue.py の QA再判定経路とauto_close_issue誤爆の是正（Issue #144 + #152 統合実装）**: `qa --force`（既存qa_resultを上書き、qa_historyへ退避）と `done --skip-qa-guard` によるQA再判定の正規経路を追加し、同時に `close_issue` 専用フィールド＋`close_linked_issue`関数への置き換えでnotes正規表現参照を完全廃止した。pytest 40件全パス。設計→実装→QAが1スプリント内で完結。
- **投資部門テンプレート複製の実地初運用（ADR-014 Phase3前半）**: `alpha-predict-jp` へhq-agents symlink5本・pm.md・`_queue.json`・`docs/sprints/`を新規導入。origin未push（ローカルブランチのみ）で既存資産は無傷。
- **`_lessons.json` の issue_url 同期是正**: sprint-23〜25の未Issue化lesson16件を`gh issue list`との突合で是正し、真の未起票0件を確認。retro.mdにIssue化時の即時書き戻し手順を追記した。
- **Issue #149・#150 の文書反映**: pm.mdへ計画時ポイント集計の義務化、architect.mdへ設計完了時セルフチェック項目を追加。

### 学び

- `governance-doc-149-150` で導入したばかりのarchitect.mdセルフチェック制度が、同一スプリント内の`queue-qa-reguard-design`で即日効果を発揮し、Alexが既存pytest 7件とdoneガードの矛盾を自力検出した（`agent-crew-sprint-27-design-001`）。
- Riku（`lessons-issue-sync-fix`）の16件機械突合、Sora（`invest-dept-hq-deploy-qa`）の実機QA、Yukiのインシデント時の全タスク機械点検（誤爆リスク3件を事前無害化）など、機械的な突合・点検が有効に機能した。

### 失敗パターン

- **auto_close_issueによるPR誤クローズ（インシデント）**: `invest-dept-charter`完了時、notes内「PR #151」を誤認しオーナー戦略レビュー待ちのPR #151を誤クローズ（即時reopenで復旧、実害なし）。調査でSprint-26中にもIssue #139/#140/#141が同機構で早期クローズされていたことが判明（最終状態は妥当）。同スプリント内でIssue #144の実装に統合し恒久対応済み（`agent-crew-sprint-27-reliability-001`、Issue #152）。
- **二重指揮の衝突**: team-leadがPMを経由せずRikuへ直接タスク指示を出し、チーム合意と衝突。PMが2回差し戻し、実装者が板挟みになった（`agent-crew-sprint-27-process-001`、Issue #155）。
- **命名往復**: 設計と実装の並行時にissue_ref/close_issueの命名が2往復し、summary文言の訂正が必要になった（`agent-crew-sprint-27-process-002`）。
- **macOS readlink -f非対応**: symlink実体解決の検証手順でTomo・Soraが独立に同一問題を発見し、重複して回避策を導出した（`agent-crew-sprint-27-reliability-002`、Issue #156）。

### 次スプリントへの推奨

- 「スプリント進行中のタスクレベル指示はPM経由に一本化、team-leadは方針決定のみ」の運用ルールを明文化する（Issue #155）。
- symlink検証手順書へのmacOS(BSD readlink)非対応の明記を横展開する（Issue #156）。
- pm.mdステップ0.7のsource_repo URL正規化（SSH/HTTPS両対応）を実装する（`agent-crew-sprint-27-tooling-001`）。

---
