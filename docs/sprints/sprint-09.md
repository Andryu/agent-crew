# Sprint-09 計画書

**期間**: 2026-04-24 〜  
**ブランチ**: `feat/sprint-09`  
**作成**: Yuki

---

## ゴール

`scripts/queue.py` を新規作成し、`queue.sh` と並走させる Phase 1 を完了する。
Bash 固有の制約（JSON文字列組み立て・サイレント失敗・テスト不可）を段階的に解消する第一歩。
あわせてレトロ自動起動の確実性を高めるプロセス修正を実施する。

---

## 背景・判断根拠

- `scripts/queue.sh` が 1088 行に肥大化し、JSON を文字列組み立てで処理している
- Issue #66（priority-critical）: `${4:-{}}` 構文バグで `_signals.jsonl` サイレント失敗が発生
  — 根本原因は Bash 自体の制約であり、パッチでは解決不可
- `set -e + || true` パターンによるサイレント失敗が再現しやすい構造
- ユニットテストが書けず、バグ混入を防ぐ手段がない
- Issue #65（priority-high）: Sprint-07 完了後にレトロが発動しなかった。同じ失敗を繰り返している

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | risk_level | qa_mode |
|---|------|---------|------|------|------------|------------|---------|
| 1 | `queue-py-design` | queue.py 設計（ADR・インターフェース定義） | Alex | なし | M | medium | — |
| 2 | `queue-py-impl` | queue.py 実装（Phase 1: 全コマンドのPython実装） | Riku | #1 | L | high | inline |
| 3 | `queue-py-qa` | queue.py QA（テスト・既存スキーマ互換確認） | Sora | #2 | M | — | — |
| 4 | `retro-autostart-fix` | レトロ自動起動の確実化（pm.md 完了基準修正・Issue #65） | Riku | #3 | S | low | inline |
| 5 | `retro-autostart-qa` | レトロ自動起動修正 QA | Sora | #4 | S | — | — |

> **合計ポイント: 13 pt**（S×2=2 + M×2=6 + L×1=5）

---

## タスク詳細

### #1 queue-py-design（Alex）

**目的**: Riku の実装前にインターフェースと方針を確定する

成果物: `docs/spec/queue-py-design.md`

記載内容:
- `typer` + `pydantic` を使ったコマンド設計（サブコマンド一覧）
- `_queue.json` スキーマを pydantic モデルで定義
- `queue.sh` との並走戦略（既存コマンドへの影響ゼロ保証）
- ファイルロック方針（`fcntl.flock` を使用）
- エラーハンドリング方針（例外を ValueError / RuntimeError で分類）
- テスト戦略（pytest + tmp_path フィクスチャ）

**完了基準**: 設計書が存在し、全コマンドのシグネチャが定義されている

---

### #2 queue-py-impl（Riku）

**目的**: `scripts/queue.py` を新規作成。`queue.sh` と同じ JSON スキーマを読み書きし、後方互換を維持する

実装対象コマンド（queue.sh の全コマンドをカバー）:
- `init <sprint>`
- `start <slug>`
- `done <slug> <agent> <summary>`
- `handoff <slug> <agent>`
- `block <slug> <agent> <reason>`
- `qa <slug> APPROVED|CHANGES_REQUESTED <summary>`
- `retry <slug>`
- `show [slug]`
- `next`
- `parallel-handoff <slug1>:<agent1> <slug2>:<agent2>`

技術要件:
- Python 3.11+
- `typer` (CLI フレームワーク)
- `pydantic` (スキーマ検証)
- `fcntl.flock` によるファイルロック（`queue.sh` の flock と同等）
- `scripts/queue.py` として配置、`chmod +x`
- `tests/test_queue_py.py` を同時作成（pytest、10 ケース以上）

**完了基準**:
- `scripts/queue.py init sprint-09` が動作する
- 既存の `_queue.json` を読み込める
- pytest が全パスする

---

### #3 queue-py-qa（Sora）

**目的**: queue.py の品質・互換性を確認する

確認項目:
- pytest 全パス確認（`python -m pytest tests/test_queue_py.py -v`）
- `queue.sh` が生成した `_queue.json` を `queue.py` で読み込めるか
- `queue.py` が生成した `_queue.json` を `queue.sh` で読み込めるか（双方向互換）
- エラーハンドリング: 不正 slug / 不正 status 遷移でクラッシュしないか
- ファイルロックの競合テスト

---

### #4 retro-autostart-fix（Riku）

**目的**: Issue #65 を解消する。スプリント完了後のレトロ自動起動が確実に発動するよう pm.md を修正する

変更対象: `.claude/agents/pm.md`

変更内容:
- 「スプリント完了後の自動フロー」セクションのステップ4に強調を追加
- 完了判定直後の handoff テンプレートに `@retro` 呼び出し例を明示
- Quality Gate 通過直後に「みゆきち起動 = 必須」を明記（オーナー確認不要を再強調）

**完了基準**: pm.md の完了フローセクションに retro 起動が必須であることが明示されている

---

### #5 retro-autostart-qa（Sora）

**目的**: pm.md の修正が意図通りかつ既存ルールと矛盾しないか確認する

確認項目:
- retro 自動起動の記述が完了フローセクションに存在するか
- 既存の「介入最小化原則」と矛盾しないか
- 文言が明確か（「必須」「オーナー確認不要」が明示されているか）

---

## 並列化

今スプリントは全タスクが直列。並列化なし。

---

## トークン消費見積もり

| タスク | complexity | 推定 |
|--------|------------|------|
| queue-py-design | M | 40,000 |
| queue-py-impl | L | 80,000 |
| queue-py-qa | M | 40,000 |
| retro-autostart-fix | S | 15,000 |
| retro-autostart-qa | S | 15,000 |
| **合計 × 1.5** | | **285,000** |

300,000 tokens 未満 → **1 バッチで実行可能**

---

## 除外したバックログ

| Issue | 理由 |
|-------|------|
| #58 MAX_RETRY complexity連動 | queue.sh への修正は Phase 2（queue.py 移行後）に実施する方が自然 |
| #36 トークン最適化 | 今スプリントの主目的と競合しない。次スプリント候補に残す |
| #56 _signals.jsonl 実装 | Sprint-07 で設計完了済み。queue.py 安定後に実装する |

---

## 次スプリント候補

- **Sprint-10**: queue.sh → queue.py 委譲 Phase 2（queue.sh の各コマンドを queue.py に委譲）
- **#58**: MAX_RETRY complexity連動（queue.py の retry コマンドに組み込み）
- **#56**: _signals.jsonl 実装（queue.py に signalsWrite を追加）
