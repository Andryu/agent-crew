# Sprint-10 レトロスペクティブ

実施日: 2026-04-24
担当: みゆきち（retro エージェント）
対象: Sprint-10（queue.sh → queue.py 委譲 Phase 2 + Issue #58 MAX_RETRY complexity連動）

---

## スプリントサマリー

| 指標 | 値 |
|------|-----|
| タスク数 | 5（設計1 / 実装2 / QA2） |
| 完了数 | 5（全DONE） |
| QA APPROVED | 2 / 2 |
| QA差し戻し率 | 0% |
| リトライ | 0回 |
| BLOCKED | 0件 |
| テスト数 | 18 → 23（+5件） |
| _signals.jsonl 記録数 | sprint-10 分: 16件（全タスク分が記録されている） |
| 主な成果物 | docs/spec/delegate-design.md・queue.py 委譲実装・complexity連動MAX_RETRY実装 |

---

## うまくいったこと (Keep)

### K-1. _signals.jsonl が Sprint-10 全タスク分で正常に記録された

Sprint-08 の emit バグ修正・Sprint-09 の観察（_signals.jsonl 未記録）を経て、Sprint-10 ではすべての task.start / task.done / task.handoff / qa.approved シグナルが記録されている。修正が実際に機能していることが確認できた。

### K-2. 設計書（delegate-design.md）の品質が高く、実装がスムーズに進んだ

Alex が作成した `docs/spec/delegate-design.md` は互換リスク・コマンドルーティング表・必須対応事項・ロールバック手順を網羅しており、Riku の実装作業が最小限の手戻りで完了した。設計フェーズへの投資が実装フェーズの品質に直結したパターン。

### K-3. QA（Sora）が MINOR 指摘を適切に記録した

`delegate-qa` で Sora が `emit_signal` のグローバル変数参照問題を MINOR として指摘した。APPROVED を出しながら問題点を記録するバランスが適切だった。QA プロセスが「形骸化」から「実質的な検証」に改善されていることが確認できる（Sprint-08 P-4 対応の効果）。

### K-4. テストスイートの拡充（18→23件）

Sprint-10 の実装に伴い pytest が 18件から 23件に増加した。complexity連動MAX_RETRY のテストが追加されており、regression を防ぐ自動テストが着実に積み上がっている。

### K-5. complexity連動MAX_RETRY がクリーンに実装された

Issue #58 の実装（S=2 / M=3 / L=5 の上限、null はデフォルト3にフォールバック）が complexity S タスクとして計画通り完了した。MAX_RETRY 変更のような「動作変更を伴う実装」に対してすぐに専用 QA タスクが続く構成が機能した。

---

## 改善が必要なこと (Problem)

### P-1. Sprint-10 の作業の大半が Sprint-09 で完了済みだったことが実装着手後に判明した

`delegate-impl` の実装を開始した Riku が、queue.sh ディスパッチ委譲・queue.py init 実装・complexityバリデーション・qa冪等性ガードがすでに Sprint-09 で完了済みであることを着手後に発見した。実装タスクの実際の作業量が計画より大幅に少なくなり、Riku の `summary` が「init コマンド追加・テスト追加完了」という最小限の記録になった。

- 根拠: _queue.json の delegate-impl.summary が「init コマンド追加・テスト追加完了」のみ
- 根拠: _signals.jsonl の delegate-impl start → done が5秒（23:13:39 → 23:13:44）

### P-2. スプリント計画時に「前スプリントで何が完了したか」の確認が不十分

P-1 の根本原因。Yuki がスプリント計画を立てた時点で queue.py の実装状態を確認していなかったため、Sprint-09 完了済みの内容を Sprint-10 タスクとして計画した。_queue.json（スプリント管理）と実際のコード状態のズレが検出されなかった。

### P-3. delegate-qa の QA 時点でのテスト数不一致（20件 vs 実際の23件）

`delegate-qa` の summary に「pytest 20/20 pass」と記録されているが、Sprint-10 完了時点での実際のテスト数は 23件。max-retry-complexity タスクで 3件追加されたためで、時系列上は正しい。ただし QA が実施された時点のテスト数と最終的なテスト数が異なると、レポートの一貫性が損なわれる。

---

## 試してみること (Try)

### T-1. スプリント計画前に「直前スプリントの実装完了状態」を確認するステップを追加（P-1・P-2 対応）

Yuki がスプリント計画を作成する前に、前スプリントで完了したタスクの `notes` と実際のコード状態を突合する。特に「前スプリントで計画していた implementation issue」と「実際に残っている実装」を照合することで、重複タスクの計画を防ぐ。

具体的アクション: pm.md の計画手順に「前スプリントの DONE タスクの実装内容を確認し、重複計画を防ぐ」チェック項目を追加する。

### T-2. 実装タスクの最短完了時間に閾値を設けて alert を出す（P-1 対応）

タスクの start → done が 30秒以下の場合、「実際に作業が行われたか確認」の注意ラベルを付ける。_signals.jsonl を使って検出可能。

### T-3. QA タスクの summary にテスト数を実行時点の最新値で記録する（P-3 対応）

QA タスクの summary には「QA実施時点の pytest 結果」を記録する。後続タスクで追加されたテスト数と混同しないよう、「pytest N件 pass (QA時点)」と明示するフォーマットを Sora のチェックリストに追加する。

---

## 持ち越しバックログ（未採用・継続観察）

| Issue | 内容 | 状態 |
|-------|------|------|
| #64 | engineer-go 無応答停止 | OPEN（Sprint-10では発生なし） |
| #69 | lesson フィードバックループ未整備 | OPEN |
| #70 | _signals.jsonl スモークテスト | Sprint-10で改善確認、継続観察 |
| retro `--save`/`--decisions` | queue.py への委譲が未完 | Bashに残す決定（delegate-design.md §4.6） |
| `parallel-handoff` | queue.py 未実装 | 使用頻度低・Bash維持 |

---

## 記録した lesson

| lesson-id | 概要 | priority_score | issue_url |
|-----------|------|---------------|-----------|
| agent-crew-sprint-10-process-001 | スプリント計画時の前スプリント実装状態確認漏れ | 4 | https://github.com/Andryu/agent-crew/issues/72 |
