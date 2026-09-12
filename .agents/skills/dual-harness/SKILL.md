---
name: dual-harness
description: Claude CodeとCodexの間で実装・レビュー・handoffを行うときに使う。利用枠の切替、作業状態の引き継ぎ、別ハーネスによるレビューが必要な場合に適用し、会話履歴のコピーや未承認の自動切替には使わない。
---

# Dual Harness

Claude CodeとCodexを併用するときは、能力の優劣を仮定せず、工程と利用枠で役割を分ける。

## 標準ルート

1. Claude CodeでSPEC、対象ファイル、禁止事項、検証コマンド、Definition of Doneを確定する。
2. Codexで明示された対象だけを実装し、検証する。
3. fresh Claude Codeで仕様準拠をレビューし、必要なら別のfresh reviewerが品質をレビューする。

## handoff

- 会話履歴を別ハーネスへコピーしない。repo、Git差分、テスト結果、短い作業状態を渡す。
- handoff本文は、目的、現在地、次の一手、未決事項、検証方法、落とし穴を含める。
- Evidenceはスクリプトで生成し、HEAD、git status、diff、変更ファイル、テスト出力、exit codeを含める。
- handoffとEvidenceが矛盾したらEvidenceを優先する。

## 利用枠・失敗時の規律

- quota到達後にhandoffを書く前提にしない。工程の節目でcheckpointを作る。
- quota、認証、ネットワーク、timeoutは別の失敗として記録する。
- 自動的に別ハーネスを起動しない。明示的な人間承認または個別の自動化仕様がある場合だけ切り替える。
