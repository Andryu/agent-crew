# Sprint-11 レトロスペクティブ

実施日: 2026-04-24
担当: みゆきち（retro エージェント）
対象: Sprint-11（queue.sh レガシーBash実装削除 + graph コマンドPython化 + フィードバックループ改善）

---

## スプリントサマリー

| 指標 | 値 |
|------|-----|
| タスク数 | 7（設計3 / 実装2 / QA2） |
| 完了数 | 7（全DONE） |
| QA APPROVED | 2 / 2 |
| QA差し戻し率 | 0% |
| リトライ | 0回 |
| BLOCKED | 0件 |
| テスト数 | 23 → 27（+4件） |
| queue.sh 行数削減 | 1090行 → 404行（63%削減） |
| 主な成果物 | queue.sh レガシー削除・queue.py graph コマンド・docs/spec/feedback-loop-doc.md |

---

## うまくいったこと (Keep)

### K-1. queue.sh が 63% 削減され軽量なシンラッパーに変換された

`legacy-delete-impl` により queue.sh が 1090行から 404行になった。
Sprint-09 で委譲完了後も残っていたデッドコード（acquire_lock・cmd_start 等の約700行）が
安全に削除され、queue.py が単一の信頼源となった。
設計書（legacy-delete-design.md）が削除対象一覧・ロールバック手順・完了確認手順を
網羅していたことで、実装が確実かつ最小手戻りで完了した。

### K-2. graph コマンドの Python 化が完了し pytest が 23→27 件に増加した

`graph-py-impl` により queue.py に `graph` Click サブコマンドが追加された。
Mermaid flowchart 出力・`--save` オプション（docs/graphs/<sprint>.md 生成）・
queue.sh からの委譲がすべて正常動作することを Sora が確認（27/27 pass）。
テストスイートの蓄積により回帰リスクが着実に低下している。

### K-3. フィードバックループ設計書（feedback-loop-doc.md）が仕組みとして完成した

Issue #69 / #72 への対処として Alex が設計した `docs/spec/feedback-loop-doc.md` は、
Yuki のスプリント計画前確認フローをコマンド付きで定義している。
「確認する」という抽象指示から「実行するコマンド」への具体化が、
今後のスプリントで同種の計画重複を防ぐ構造的な解決策となった。

### K-4. QA 差し戻し率 0% を維持

7タスク中2件の QA タスクがいずれも初回 APPROVED。
Sprint-10 から続く QA 品質改善（Sora の summary 記録義務化）の効果が継続している。

---

## 改善が必要なこと (Problem)

### P-1. Riku がレート制限に到達し legacy-delete-impl 完了後にセッション中断した

Riku が `legacy-delete-impl`（L タスク）を完了した直後にレート制限（"You've hit your limit"）
に遭遇し、後続の引き継ぎがメインセッション代行になった。実装成果物への影響はなかったが、
L タスクを処理した後に Riku が利用不能になるパターンが発生した。

- 根拠: Sprint-11 概要「Riku がレート制限に遭遇し legacy-delete-impl 完了後に中断」

### P-2. Sora が Bash 実行上限でスモークテストを静的検証に差し替え、キュー更新も不可能になった

`legacy-delete-qa` と `graph-py-qa` で Sora が Bash 実行上限に達し、
予定していたスモークテスト（smoke test コマンドの実行）を静的コードレビューで代替した。
さらにキュー更新（`queue.sh qa` コマンド）も実行できず、メインセッションが代行した。
QA エージェントが実際のコマンドを実行せずに APPROVED を出す状態が発生しており、
Sprint-08 で記録した「QA 形骸化」問題（agent-crew-sprint-08-process-001）が
ツール制約起因で再現した。

- 根拠: Sprint-11 概要「Sora が Bash 実行上限でスモークテストを静的検証で代替、キュー更新もできずメインセッションが代行」

### P-3. Sora がスプリント完了時のレトロ起動をスキップした（5スプリント連続の繰り返し）

Sprint-11 完了後にレトロが自動起動されず、オーナーが手動でみゆきちを呼んだ。
Sprint-05 / Sprint-07 / Sprint-08 / Sprint-09 でも同様の問題が記録されており、
pm.md への追記という対策が効果を発揮していないことが確定した。
「pm.md に書かれていても、Sora が参照するエージェント定義に埋め込まれていなければ実行されない」
ことが本質的な問題である。

- 根拠: Sprint-11 完了後にオーナーが手動でみゆきちを呼んだ（今回の起動経緯）
- 根拠: agent-crew-sprint-07-process-001 に同じ失敗パターン記録済み（issue_url: #65）

---

## 試してみること (Try)

### T-1. Riku の担当タスクで L が複数連続しないよう計画時に制約を設ける（P-1 対応）

Yuki のスプリント計画時に「Riku の L タスクは1スプリント1件まで」のルールを追加する。
L+L の組み合わせが必要な場合は M+M に分割するか、2スプリントに分散する。
レート制限到達後のフォールバック手順（Sora / 親Claude が代行）を pm.md に明記する。

### T-2. Sora の QA 手順に「Bash 不可の場合は CHANGES_REQUESTED を返す」を追加する（P-2 対応）

Sora のエージェント定義に以下のフォールバックルールを追加する:

> Bash 実行が不可能な場合、QA 結果を APPROVED にしてはいけない。
> `CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）` を返してメインセッションに通知する。

メインセッションが実際に検証を代行した場合は `_queue.json` の該当タスクに
`performed_by: main-session` フラグを記録して後から識別できるようにする。

### T-3. レトロ起動を pm.md ではなく Sora のエージェント定義に直接埋め込む（P-3 対応）

`sora.md`（または完了報告フォーマットを定義するファイル）に以下を直接記載する:

> スプリント完了報告の最終行には必ず `@retro` を含めること。
> 全タスクが DONE になった時点でこのルールが適用される。

pm.md の参照に依存した「確認のための確認」ではなく、
Sora が必ず目にする自分のエージェント定義への組み込みが必要。

---

## 持ち越しバックログ（未採用・継続観察）

| Issue | 内容 | 状態 |
|-------|------|------|
| #64 | engineer-go 無応答停止 | OPEN（Sprint-11 では発生なし） |
| #65 | retro 自動起動 | OPEN（Sprint-11 でも再発） |
| parallel-handoff | queue.py 未実装 | 使用頻度低・Bash維持 |

---

## 記録した lesson

| lesson-id | 概要 | priority_score | issue_url |
|-----------|------|---------------|-----------|
| agent-crew-sprint-11-reliability-001 | Riku レート制限中断と後続フォールバック | 4 | null |
| agent-crew-sprint-11-reliability-002 | Sora Bash上限によるQA代替と形骸化再発 | 6 | null |
| agent-crew-sprint-11-process-001 | Sora レトロ起動スキップ（5スプリント連続） | 8 | null |
