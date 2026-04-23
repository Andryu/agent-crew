# Sprint-07 計画

作成日: 2026-04-23
作成者: Yuki（PM エージェント）
依拠情報:
- docs/retro/sprint-06.md（みゆきち レトロ）
- GitHub Issues（open: #51, #36, #23, #22, #39）
- scripts/queue.sh detect-stale 実装済み（Sprint-06成果物）

---

## スプリントゴール

**Sprint-06 で検出された Bash スクリプトの品質問題（detect-stale の for+shift 誤用・--slack 未実装フラグの無音処理・TZ依存）を根絶し、サブエージェントのコンテキスト制約を設計文書に明文化する。あわせてphase-2知性強化の第一歩として `_signals.jsonl` の設計を着手する。**

---

## 背景・判断根拠

### P0: detect-stale の Bash スクリプト品質問題（Sprint-06 Sora MINOR指摘 × 2）

Sora が APPROVED としつつも2件の MINOR を記録した。

1. `for` + `shift` の誤用（getopts / while+case が正しい）
2. `--slack` フラグを受け付けるが処理が未実装で引数を渡しても何も起きない

どちらも次のスプリントで修正する方針を retro で合意済み（Try-1, Try-2）。
あわせて TZ 計算の CI 環境依存性（Sora INFO）も `date -u` 統一で解消する（Try-3）。

実装コスト S・既存テストが通れば即 APPROVED できる見込み。

### P1: サブエージェントの Bash 利用不可制約の明文化（Issue #51）

Sprint-05 レトロ T-3「architect.md に『サブエージェント起動時は Bash 不可』という注意事項を記載」が Sprint-06 で未実施のまま持ち越された。設計判断の記録コストが低く、次スプリントで解消すべき。

### P2: _signals.jsonl 設計（Issue #23）

phase-2 知性強化バックログの中核。タスク完了・Sora QA 結果・retry_count などのイベントを JSONL に記録し、将来の自己改善ループへの接続を設計する。実装は次スプリント以降に委ねる設計フェーズのみ。

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity |
|---|------|---------|------|------|-----------|
| 1 | `bash-quality-fix` | detect-stale: for+shift修正・--slack未実装フラグ明示・date -u統一 | Riku | なし | S |
| 2 | `bash-quality-qa` | detect-stale品質修正 QA | Sora | #1 | S |
| 3 | `subagent-constraint-doc` | architect.md にサブエージェントBash不可制約を明記 | Alex | なし | S |
| 4 | `subagent-constraint-qa` | サブエージェント制約ドキュメント QA | Sora | #3 | S |
| 5 | `signals-jsonl-design` | _signals.jsonl 設計書の作成（Issue #23） | Alex | なし | M |

> タスク #1/#3/#5 は互いに独立しているが、並列実行禁止ルールにより直列実行する。

---

## 実行順序

```
bash-quality-fix → bash-quality-qa
subagent-constraint-doc → subagent-constraint-qa
signals-jsonl-design
```

直列実行: bash-quality-fix → bash-quality-qa → subagent-constraint-doc → subagent-constraint-qa → signals-jsonl-design

---

## 完了基準

- 全 5 タスク DONE
- QA 対象 2 件（bash-quality-qa / subagent-constraint-qa）APPROVED
- detect-stale が getopts または while+case パターンで実装されている
- `--slack` 未実装時に `ERROR: --slack is not yet implemented` を stderr 出力して exit 1 する
- `date -u` または TZ=UTC 統一で TZ 依存を排除
- architect.md にサブエージェントコンテキスト制約セクションが追加されている
- _signals.jsonl 設計書が docs/spec/ に作成されている

---

## リスク

| リスク | 対応 |
|--------|------|
| queue.sh の detect-stale 修正がリグレッションを起こす | Sora が既存 show/next コマンドの動作を確認 |
| signals-jsonl 設計が大きくなりすぎる | Alex に「Phase-1: スキーマ定義のみ」にスコープを絞るよう指示 |

---

## 関連 Issue

- #51 — Bash不可コンテキスト問題
- #39 — セッション中断検出（detect-stale 残課題）
- #23 — _signals.jsonl
- #36 — トークン最適化（今スプリントではスコープ外、次スプリント候補）
