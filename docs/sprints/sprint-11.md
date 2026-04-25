# Sprint-11 計画書

**期間**: 2026-04-24 〜  
**ブランチ**: `feat/sprint-11`  
**作成**: Yuki

---

## ゴール

queue.sh のレガシー Bash 実装を削除し、queue.py を唯一の正統実装にする。
あわせて `graph` コマンドを queue.py へ移植し、queue.sh を「シェルエントリポイント専用の薄いラッパー」に完成させる。

---

## 背景・判断根拠

- Sprint-10 で queue.sh → queue.py 委譲が安定稼働し、全テストが通過した
- 現在 queue.sh の cmd_start/done/handoff 等はまだ Bash 実装が残ったままで、委譲層の下に冗長なコードが存在する
- `graph` コマンドのみ委譲対象外で Bash 実装が残っており、Python への移植が次ステップとして明示されていた
- Issue #69「lesson → スプリント計画へのフィードバックループ欠如」への対処として、pm.md 計画チェックリストの更新も実施する

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | risk_level | qa_mode |
|---|------|---------|------|------|------------|------------|---------|
| 1 | `legacy-delete-design` | レガシー削除戦略設計（削除範囲・安全確認・ロールバック手順） | Alex | なし | M | medium | — |
| 2 | `graph-py-design` | graph コマンド Python化 設計（queue.py への移植仕様） | Alex | なし | M | medium | — |
| 3 | `legacy-delete-impl` | queue.sh レガシー Bash 実装の削除 | Riku | #1 | L | high | inline |
| 4 | `legacy-delete-qa` | レガシー削除 QA（退行・互換テスト） | Sora | #3 | M | — | — |
| 5 | `graph-py-impl` | graph コマンドの queue.py への移植 | Riku | #2 #4 | M | medium | inline |
| 6 | `graph-py-qa` | graph Python実装 QA | Sora | #5 | S | — | — |
| 7 | `feedback-loop-doc` | pm.md 計画チェックリスト更新（Issue #69 対処） | Alex | なし | S | low | end_of_sprint |

> **合計ポイント: 19 pt**（S×1=1 + M×4=12 + L×1=5 + 設計2件を含む）

> 推定トークン消費: 405,000 tokens（270K × 1.5）→ **2バッチ構成**

> `qa_mode` 列: `—` は設計・QAタスク（対象外）を意味する。

---

## バッチ構成

### Batch 1（タスク #1 〜 #4）

依存グラフ:
```
#1 legacy-delete-design → #3 legacy-delete-impl → #4 legacy-delete-qa
#2 graph-py-design （#3 とは並列実行可能だが、安全のため直列）
#7 feedback-loop-doc（任意タイミングで独立実行可能）
```

### Batch 2（タスク #5 〜 #6）

- Batch 1 全完了後に開始
- `graph-py-impl` → `graph-py-qa` の順に実行

---

## タスク詳細

### #1 legacy-delete-design（Alex）

**目的**: 削除すべき Bash 実装の範囲と安全確認手順を設計する

成果物: `docs/spec/legacy-delete-design.md`

記載内容:
- 削除対象の関数一覧（cmd_start, cmd_done, cmd_handoff, cmd_qa, cmd_block, cmd_retry, cmd_show, cmd_next, cmd_detect_stale の旧 Bash 実装部分）
- 削除しないもの: cmd_graph（#2 で別途 Python 化）、cmd_retro（queue.py 未実装）、cmd_parallel_handoff、シェルエントリポイント・ロック・ヘルパー関数
- 削除後の queue.sh の期待する構造（委譲ディスパッチのみ残る形）
- Python 非対応環境のフォールバック動作の方針（現状維持 or 削除）
- ロールバック手順
- 完了確認: `pytest tests/test_queue_py.py -v` 全パス + smoke test 一覧

**完了基準**: 設計書が存在し、削除範囲・安全確認手順・完了基準が明示されている

---

### #2 graph-py-design（Alex）

**目的**: queue.sh の cmd_graph 相当の機能を queue.py に移植するための仕様を設計する

成果物: `docs/spec/graph-py-design.md`

記載内容:
- queue.sh cmd_graph の現行実装の整理（Mermaid 生成ロジック、`--save` オプション、出力先パス）
- queue.py への移植仕様（Click サブコマンド `graph`、引数・オプション定義）
- テスト仕様: `test_queue_py.py` への追加ケース
- queue.sh からの委譲方法（`python scripts/queue.py graph "$@"` に変更）

**完了基準**: 設計書が存在し、移植仕様・テストケース・委譲方法が定義されている

---

### #3 legacy-delete-impl（Riku）

**目的**: legacy-delete-design.md に基づき、queue.sh のレガシー Bash 実装を削除する

変更対象:
- `scripts/queue.sh`（削除対象関数の Bash 実装を削除、委譲ディスパッチのみ残す）
- `tests/test_queue_py.py`（必要に応じてテストケース追加）

実装方針（legacy-delete-design.md に従う）:
- 設計書で指定された関数の旧 Bash 実装コードブロックを削除
- 委譲ディスパッチ（`python scripts/queue.py <cmd> "$@"`）は維持
- フォールバック方針に従い Python 非対応時の処理を更新
- pytest 全パスを確認してから完了

**完了基準**:
- queue.sh から指定の Bash 実装コードブロックが削除されている
- `python -m pytest tests/test_queue_py.py -v` 全パス
- `scripts/queue.sh start <slug>` が正常動作する

---

### #4 legacy-delete-qa（Sora）

**目的**: レガシー削除後の退行がないことを確認する

確認項目:
- pytest 全パス確認（`python -m pytest tests/test_queue_py.py -v`）
- queue.sh 経由で主要コマンドが正常動作するか（smoke test: start / done / handoff / qa / block / retry / show / next）
- exit code が期待値と一致しているか（正常: 0、エラー: 非0）
- `_signals.jsonl` が委譲後も正しく書き込まれるか
- graph / retro コマンドが引き続き Bash 実装として動作するか

---

### #5 graph-py-impl（Riku）

**目的**: graph-py-design.md に基づき、queue.py に `graph` コマンドを追加する

変更対象:
- `scripts/queue.py`（graph Click サブコマンド追加）
- `scripts/queue.sh`（cmd_graph を `python scripts/queue.py graph "$@"` に変更）
- `tests/test_queue_py.py`（graph コマンドのテストケース追加）

**完了基準**:
- `scripts/queue.sh graph` が queue.py の graph を呼び出している
- `scripts/queue.sh graph --save` が docs/graphs/ に .md を保存する
- pytest 全パス

---

### #6 graph-py-qa（Sora）

**目的**: graph コマンドの Python 実装が期待通り動作することを確認する

確認項目:
- `scripts/queue.sh graph` が Mermaid ブロックを出力するか
- `scripts/queue.sh graph --save` が docs/graphs/<sprint>.md を生成するか
- pytest の graph テストケースが全パスするか

---

### #7 feedback-loop-doc（Alex）

**目的**: Issue #69「lesson → スプリント計画へのフィードバックループ欠如」に対処する

変更対象: `.claude/agents/pm.md`（計画チェックリストへの追記）

追記内容:
- スプリント計画作成前の確認手順に「前スプリントの DONE タスク実装状態の突合」を追加
- `~/.claude/_lessons.json` の priority_score >= 4 の未対処 lesson をスプリント計画に反映するステップを追加

**完了基準**: pm.md の計画手順に上記2点が明示的に記載されている

---

## 並列化できるもの

- #1 `legacy-delete-design` と #2 `graph-py-design` は互いに独立しているため並列実行可能
- #7 `feedback-loop-doc` はいつでも独立実行可能

---

## Quality Gate

スプリント完了条件:
1. 全タスクの `status == "DONE"`
2. QA対象の全タスクで `qa_result == "APPROVED"`
3. `python -m pytest tests/test_queue_py.py -v` 全パス（最終確認）
