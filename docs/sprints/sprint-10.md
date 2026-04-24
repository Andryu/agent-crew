# Sprint-10 計画書

**期間**: 2026-04-24 〜  
**ブランチ**: `feat/sprint-08`  
**作成**: Yuki

---

## ゴール

`queue.sh` の各コマンドを `queue.py` へ委譲する Phase 2 を完了する。
あわせて Issue #58（MAX_RETRY complexity連動）と Issue #56（`_signals.jsonl` 実装の queue.py への統合）を対応し、
Bash 実装への依存を段階的に削減する。

---

## 背景・判断根拠

- Sprint-09 で queue.py Phase 1（全コマンド実装・pytest 通過）が完了した
- 次ステップは queue.sh の各 `cmd_*` 関数から `python scripts/queue.py <subcommand>` を呼び出す委譲層の実装
- これにより queue.sh は「シェルエントリポイント + Pythonへの薄いラッパー」になる
- Issue #58: `retry` コマンドで MAX_RETRY を complexity に連動させる（S=2, M=3, L=5）
- Issue #56: `_signals.jsonl` の書き込みが queue.py では実装済みだが、queue.sh 経由時のサイレント失敗が未解消
  - queue.sh → queue.py 委譲後は queue.py の emit_signal が呼ばれるため根本解決になる

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | risk_level | qa_mode |
|---|------|---------|------|------|------------|------------|---------|
| 1 | `delegate-design` | 委譲戦略設計（ADR・移行方針・互換リスク洗い出し） | Alex | なし | M | medium | — |
| 2 | `delegate-impl` | queue.sh → queue.py 委譲実装（Phase 2） | Riku | #1 | L | high | inline |
| 3 | `delegate-qa` | 委譲実装 QA（互換・退行テスト） | Sora | #2 | M | — | — |
| 4 | `max-retry-complexity` | MAX_RETRY complexity連動（Issue #58） | Riku | #3 | S | low | inline |
| 5 | `max-retry-qa` | MAX_RETRY変更 QA | Sora | #4 | S | — | — |

> **合計ポイント: 13 pt**（S×2=2 + M×2=6 + L×1=5）

> `qa_mode` 列: `—` は設計・QAタスク（対象外）を意味する。

---

## タスク詳細

### #1 delegate-design（Alex）

**目的**: Riku の実装前に委譲戦略と互換リスクを確定する

成果物: `docs/spec/delegate-design.md`

記載内容:
- 委譲方針: queue.sh の `cmd_start` 等を `python scripts/queue.py start "$@"` に置き換える範囲
- 委譲対象コマンド: `start`, `done`, `handoff`, `parallel-handoff`, `qa`, `block`, `retry`, `show`, `next`, `detect-stale`, `retro`
- 委譲しないコマンド: `graph`（Bash専用処理のため当面維持）
- `init` コマンドの queue.py への追加方針（queue.sh にある `cmd_init` 相当）
- 互換リスク: exit code、stdout/stderr 形式、`_queue.json` スキーマの差異
- フォールバック戦略: `python` が存在しない環境での動作（queue.sh 実装を残す）
- テスト戦略: 委譲前後で同一 JSON が生成されることの確認方法

**完了基準**: 設計書が存在し、委譲範囲・リスク・テスト方針が定義されている

---

### #2 delegate-impl（Riku）

**目的**: queue.sh の各コマンドを queue.py に委譲する薄いラッパーに書き換える

変更対象:
- `scripts/queue.sh`（各 `cmd_*` 関数を Python 呼び出しに変更）
- `scripts/queue.py`（`init` コマンドの追加、`parallel-handoff` コマンドの追加）
- `tests/test_queue_py.py`（新コマンドのテストケース追加）

実装方針（delegate-design.md に従う）:
- `cmd_start()` 等を `python scripts/queue.py start "$@"` のラッパーに変更
- `graph` コマンドは Bash 実装を維持
- Python が利用不可の場合は `WARN: python not available, using bash fallback` を出力して既存実装を使用
- exit code は queue.py のものをそのまま伝播させる

**完了基準**:
- `scripts/queue.sh start <slug>` が内部で queue.py を呼び出している
- `tests/test_queue_py.py` に `init` と `parallel-handoff` のテストが追加されている
- pytest 全パスする

---

### #3 delegate-qa（Sora）

**目的**: 委譲実装の品質・互換性・退行がないことを確認する

確認項目:
- pytest 全パス確認（`python -m pytest tests/test_queue_py.py -v`）
- queue.sh 経由で全コマンドが正常動作するか（smoke test）
- queue.sh と queue.py の exit code が一致しているか（主要エラーケース）
- `_signals.jsonl` が委譲後も正しく書き込まれるか
- graph コマンドが Bash 実装として残っているか

---

### #4 max-retry-complexity（Riku）

**目的**: Issue #58 を解消する。`retry` コマンドの MAX_RETRY を complexity に連動させる

変更対象: `scripts/queue.py`（`retry` コマンド）

変更内容:
- MAX_RETRY 環境変数をデフォルトとして残しつつ、task の `complexity` に応じた上限を適用
  - `S` → max 2
  - `M` → max 3
  - `L` → max 5
- `complexity` が未設定の場合は環境変数 `MAX_RETRY`（デフォルト3）にフォールバック
- `tests/test_queue_py.py` にテストケースを追加

**完了基準**: S/M/L それぞれの retry 上限が異なることが pytest で確認できる

---

### #5 max-retry-qa（Sora）

**目的**: MAX_RETRY complexity連動の品質を確認する

確認項目:
- pytest 全パス確認（retry 上限テスト含む）
- `complexity: S` のタスクが 2 回目の retry で BLOCKED になるか
- `complexity: L` のタスクが 5 回目の retry まで READY_FOR_RIKU に戻るか
- `complexity: null` のタスクが従来通り MAX_RETRY=3 で動作するか

---

## 並列化

今スプリントは全タスクが直列。並列化なし。

---

## トークン消費見積もり

| タスク | complexity | 推定 |
|--------|------------|------|
| delegate-design | M | 40,000 |
| delegate-impl | L | 80,000 |
| delegate-qa | M | 40,000 |
| max-retry-complexity | S | 15,000 |
| max-retry-qa | S | 15,000 |
| **合計 × 1.5** | | **285,000** |

300,000 tokens 未満 → **1 バッチで実行可能**

---

## 除外したバックログ

| Issue | 理由 |
|-------|------|
| #56 `_signals.jsonl` 独立実装 | queue.sh → queue.py 委譲（#2）で根本解決されるため、独立タスク不要 |
| `graph` コマンド Python化 | Bash の Mermaid 生成は複雑で移行リスクが高い。今スプリントの主目的外 |
| #36 トークン最適化 | 今スプリントの主目的と競合しない |

---

## 次スプリント候補

- **Sprint-11**: queue.sh のレガシー実装の削除（委譲が安定稼働後）
- **`graph` Python化**: Mermaid グラフ生成を queue.py へ移植
- **#36 トークン最適化**: エージェント起動コストの削減
