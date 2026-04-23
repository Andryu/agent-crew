# Sprint-06 レトロスペクティブ

実施日: 2026-04-22
担当: みゆきち（retro エージェント）

---

## スプリントサマリー

| 指標 | 値 |
|------|-----|
| タスク数 | 6（実装3 / QA3） |
| 完了数 | 6（全DONE） |
| QA APPROVED | 3 / 3 |
| リトライ | 0回 |
| BLOCKED | 0件 |
| 内部エラー | 2回（Riku×1、detect-staleテスト中×1） |
| Sora指摘 | MINOR 2件 / INFO 1件 |

---

## うまくいったこと (Keep)

### 1. リトライ0・全タスククリーン完了
Sprint-05 でリトライが発生した spec-mismatch 問題（agent-crew-sprint-05-qa-001）は再発しなかった。
計画文書とADR突合の徹底が有効だったと推定される。

### 2. 2スプリント連続問題（PR Test Plan）の恒久対処
Sprint-04・Sprint-05 と繰り返した PR Test Plan 漏れが、PRテンプレと riku.md の両方に明文化されたことで構造的に解決された。

### 3. みゆきち自動起動の明文化
pm.md への記述追加により、次スプリントからオーナーの手動依頼なしで自動起動できる体制が整った。

### 4. 内部エラーからの自己回復
Riku の内部エラー（slack-notify-simplify実行中）・detect-stale テスト中の内部エラーともに、ファイル変更・キュー操作は完了済みであり再実行で正常動作した。セッション中断後の状態整合性が実用上問題ないことが確認された。

---

## 改善が必要なこと (Problem)

### 1. detect-stale のオプション解析アンチパターン（Sora MINOR指摘）
`for` + `shift` の誤用があった。Bash の getopts / shift パターンの使い方が定着していない。

### 2. `--slack` 未実装の無音処理（Sora MINOR指摘）
`--slack` フラグを受け付けるが実際の通知処理が未実装で、引数を渡しても何も起きない状態だった。未実装機能のフラグを公開する際はエラーまたは警告を出すべき。

### 3. TZ計算のCI環境依存性（Sora INFO）
detect-stale 内のタイムスタンプ計算がローカル TZ 前提であり、CI環境では誤動作するリスクがある。将来課題として記録。

---

## 試してみること (Try)

### 1. Bash スクリプトのオプション解析パターンを riku.md に明示
`getopts` または `while [[ $# -gt 0 ]]` + `case` パターンをサンプルとして記載し、`for` + `shift` の誤用を防ぐ。

### 2. 未実装フラグの明示ルール化
実装予定だが未実装のフラグは `echo "ERROR: --flag is not yet implemented" >&2; exit 1` で明示するか、コメントアウトして公開しない方針をドキュメント化する。

### 3. `--utc` 統一の検討
TZ 依存を避けるため date コマンドに `-u` フラグを追加するパターンを標準化する。Sprint-07 の設計タスクとして Issue 化候補。

---

## 持ち越しバックログ（未採用 Issue）

| Issue | 内容 | Sprint-07 候補 |
|-------|------|---------------|
| #51 | Bash不可コンテキスト問題 | 設計タスクとして採用検討 |
| #48 | Soraスリープ切断問題 | 対策難度高・引き続き保留 |
| #36 | トークン最適化追加対処 | ADR実装済み、追加対処を評価 |
| #22 | 定量ルーブリック | 採用検討 |
| #23 | _signals.jsonl | 採用検討 |

---

## 記録した lesson

| lesson-id | 概要 | priority_score |
|-----------|------|---------------|
| agent-crew-sprint-06-tooling-001 | detect-stale の for+shift 誤用 | 2 |
| agent-crew-sprint-06-tooling-002 | --slack 未実装の無音処理 | 3 |
| agent-crew-sprint-06-reliability-001 | TZ計算のCI環境依存性 | 2 |
| agent-crew-sprint-06-process-001 | 内部エラーからの自己回復（成功パターン） | — |

