# Sprint-07 + Sprint-08 合同レトロスペクティブ

実施日: 2026-04-24
担当: みゆきち（retro エージェント）
対象: Sprint-07（レトロ未実施）+ Sprint-08（完了直後）

---

## スプリントサマリー

### Sprint-07

| 指標 | 値 |
|------|-----|
| タスク数 | 5（実装3 / QA2） |
| 完了数 | 5（全DONE） |
| QA APPROVED | 2 / 2 |
| リトライ | 0回 |
| BLOCKED | 0件 |
| 主な成果物 | detect-stale修正・architect.mdサブエージェント制約・signals-jsonl設計書 |

Sprint-06 レトロで合意した Try 3件（for+shift修正・--slack明示・date -u統一）をすべて完了した。前スプリントの技術的負債解消に集中した計画が機能した。

### Sprint-08

| 指標 | 値 |
|------|-----|
| タスク数 | 5（実装2 / QA2 / 計画1） |
| 完了数 | 5（全DONE） |
| QA APPROVED | 1 / 2（signals-qa は summary が "test" のままで実質未評価） |
| リトライ | 0回（キュー上） |
| BLOCKED | 0件（キュー上） |
| 特記 | `_emit_signal` バグ検出・engineer-go 無応答停止（Issue #64） |

---

## うまくいったこと (Keep)

### K-1. Sprint-07: 前スプリント Try の完全消化

Sprint-06 で指摘された3件の Bash 品質問題（for+shift誤用・--slack無音処理・TZ依存）を Sprint-07 でリトライ0で全て修正した。retro → Try → 次スプリントで確実に反映するサイクルが定着しつつある。

### K-2. Sprint-07: architect.md サブエージェント制約の明文化

Issue #51（Sprint-05 T-3 からの持ち越し）を Sprint-07 で解決。サブエージェントコンテキストでの Bash 不可制約が文書化され、同様の混乱が再発しにくい構造になった。

### K-3. Sprint-08: pm.md 分割の品質

pm.md 681行を 196行 + 142行 + 181行の3ファイルに分割し、Sora QA で CRITICAL/MAJOR ゼロ・MINOR 4件のみで APPROVED。大規模リファクタリングをクリーンに実施できた。

### K-4. Sprint-08: _emit_signal バグを発見・修正した

`${4:-{}}` の Bash 構文バグ（シェルが `}` を誤解釈してサイレント失敗）を Sprint-08 の実装・テストフェーズで発見し、Sprint-08 内で修正まで完了した。設計書作成（Sprint-07）→実装（Sprint-08）の2スプリント型で取り組んだことで実装時の検証が十分に行われた。

### K-5. Sprint-08: engineer-go 停止時の親Claude直接実装による回避

engineer-go サブエージェントが internal error で無応答停止した際、親 Claude が直接実装することでスプリントを止めずに完了させた。サブエージェント障害に対するフォールバック手段が有効だった。

---

## 改善が必要なこと (Problem)

### P-1. Sprint-07 レトロが実施されなかった

Sprint-07 完了後にレトロが実施されないまま Sprint-08 に突入した。振り返りが欠落するとパターン学習の連鎖が途切れ、problems が次スプリントの計画に反映されない。Sprint-06 で「みゆきち自動起動を明文化した」はずが、Sprint-07 完了時に実行されなかった。

### P-2. `${4:-{}}` 構文バグのサイレント失敗

`_emit_signal()` の `${4:-{}}` パターンは Bash のブレース展開と競合し、`set -e` 環境下ではエラーも出さずに失敗する。設計書（signals-jsonl-design.md）のコードサンプル自体に問題のある構文が含まれていたため、実装者がそのままコピーして埋め込んだ。

- 根拠: `queue.sh` コミット履歴でバグ修正前の `${4:-{}}` が確認できる
- 根拠: `_signals.jsonl` に1件しかエントリがなく、Sprint-08 の大半のシグナルが記録されていない

### P-3. engineer-go サブエージェントの無応答停止（Issue #64）

長い実装指示（queue.sh 全体の読み込み + 詳細な実装指示）を渡したとき、Agent tool が `[Tool result missing due to internal error]` で停止した。コンテキストウィンドウ超過またはタイムアウトが原因と推定される。信頼できる自動化の妨げになる。

### P-4. signals-qa の実質未評価

`signals-qa` タスクの summary が "test" のままになっており、QA の内容が記録されていない。シグナルのバグが残ったまま QA が通過した形になっている。QA アクションの品質確認が形骸化するリスクがある。

### P-5. Sprint-08 の `_signals.jsonl` が1件しか記録されていない

signals-impl 完了後に emit テストを繰り返して修正したが、Sprint-08 の本来のタスクシグナル（pm-split, pm-split-qa, signals-impl, signals-qa）は記録されていない。レトロに活用できる素材が乏しい状態になっている。

---

## 試してみること (Try)

### T-1. レトロ自動起動の強制チェック（P-1 対応）

pm.md または retro.md に「スプリント完了時、Yuki は必ず @retro を呼ぶ」を完了基準として追加する。スプリント完了メッセージのテンプレートに `@retro` 呼び出しを含める。

### T-2. 設計書のコードサンプルを実行可能な形式で検証（P-2 対応）

設計書に含まれる Bash コードサンプルは、マージ前に Sora が `bash -n`（構文チェック）または実際の実行でバリデーションを行う。特に `${...}` 展開を含むコードは要注意。

### T-3. サブエージェントへの指示を短く分割（P-3 対応）

engineer-go 等のサブエージェントへの実装指示は 2,000 トークン以下を目安に分割する。queue.sh 全体を読み込ませず、関係する関数部分のみを抜粋して渡す。実装指示が長くなる場合は complexity L から 2つの complexity M に分割する。

### T-4. signals-qa を実質的なテスト実行に変更（P-4 対応）

QA タスクで `signals-qa` を実施する際は、実際に `queue.sh start/done` を実行して `_signals.jsonl` に行が追記されたことを確認する手順をタスク notes に明記する。

---

## 持ち越しバックログ（未採用・継続観察）

| Issue | 内容 | 状態 |
|-------|------|------|
| #64 | engineer-go 無応答停止 | OPEN（P-3 の Try で軽減策） |
| #57 | エージェント定義へのフィードバックループ | Sprint-09 P0 |
| #48 | Sora スリープ切断 | 引き続き保留 |
| #58 | MAX_RETRY を complexity 連動に変更 | Sprint-09 候補 |
| #62 | worktree ベースの限定並列化 | Sprint-09 候補 |

---

## 記録した lesson

| lesson-id | 概要 | priority_score | issue_url |
|-----------|------|---------------|-----------|
| agent-crew-sprint-07-process-001 | Sprint-07 レトロ未実施（振り返りサイクル断絶） | 6 | https://github.com/Andryu/agent-crew/issues/65 |
| agent-crew-sprint-08-tooling-001 | `${4:-{}}` Bash 構文バグのサイレント失敗 | 9 | https://github.com/Andryu/agent-crew/issues/66 |
| agent-crew-sprint-08-reliability-001 | engineer-go サブエージェント無応答停止 | 6 | https://github.com/Andryu/agent-crew/issues/64（既存） |
| agent-crew-sprint-08-process-001 | signals-qa の実質未評価（形骸化） | 4 | https://github.com/Andryu/agent-crew/issues/67 |
