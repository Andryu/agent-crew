# feedback-loop-doc — Sprint間フィードバックループ改善設計書

## 概要

本設計書は Issue #69 / #72 への対処として、Yukiがスプリント計画時に
前スプリントの実装状態を確認する仕組みを設計する。

Sprint-10 の失敗事例（`delegate-impl` の実装が Sprint-09 で完了済みにもかかわらず
Sprint-10 で再計画してしまった）を再発防止するための、構造的な解決策を定義する。

---

## 1. 現状のフィードバックループの課題

### 1.1 現行フロー

```
スプリント完了
    ↓ scripts/queue.sh retro --save --decisions
docs/DECISIONS.md に追記
    ↓
次スプリント計画（Yuki）
    ↓ "新機能の依頼を受けてタスク分解"
_queue.json を作成・タスク一覧を提示
```

### 1.2 確認されている問題

**問題1: DECISIONS.md 参照の形骸化（Issue #69）**

`pm.md` の「スプリント開始前チェック」セクションには
`docs/DECISIONS.md` の参照が記載されているが、確認内容が抽象的で
「計画済みだが未実装」のタスクを検出する手順が明示されていない。

Sprint-10 の失敗パターンとして記録された事例:
> `delegate-impl` の大半が Sprint-09 で完了済みだったことが実装着手後に発覚した。
> Yuki がスプリント計画時に前スプリントの実装完了状態を確認していなかったことが根因。

**問題2: 実装完了状態の突合手順が存在しない（Issue #72）**

前スプリントで「設計したが実装されていない」ものと
「実装されたが計画にはなかったもの」を洗い出す手順がない。
これにより、計画と実際の実装の乖離が放置されやすい。

**問題3: _signals.jsonl の活用不足**

Sprint-10 で `start → done` の elapsed が5秒だったことは
事後的に _signals.jsonl から確認できた。しかし計画時には
このデータを使った「計画重複チェック」が行われていなかった。

### 1.3 フィードバックループの模式図（現行）

```
retro → DECISIONS.md 追記
   ↓
Yuki: DECISIONS.md を「参照する」（どこを・どう見るか不明確）
   ↓
タスク分解（設計済み・実装済みの状態確認なし）
```

---

## 2. 改善設計: Yukiのスプリント計画前確認フロー

### 2.1 設計方針

**「確認手順をコマンドとして明示する」** ことで、
Yuki が毎回同じ手順を踏めるようにする。

確認作業は以下の3ステップからなる:

1. **前スプリントの実装残高確認** — DONE タスクの summary を確認し、
   実際に実装されたものを把握する
2. **前スプリントの設計との突合** — Alex の DONE タスク（設計成果物）に対して
   対応する実装タスクが DONE になっているか確認する
3. **DECISIONS.md の推奨アクション確認** — 「次スプリントへの推奨」を
   新スプリントのタスクに具体的に落とし込む

### 2.2 確認コマンド一覧

スプリント計画前に Yuki が実行するコマンド群:

```bash
# ステップ1: 前スプリントの完了タスク一覧（実装内容を確認）
jq -r '.tasks[] | select(.status == "DONE") |
  .slug + " (" + (.assigned_to // "?") + "): " + (.summary // "（要約なし）")
' .claude/_queue.json

# ステップ2: 設計タスクに対応する実装タスクのマッピング確認
# Alex の DONE タスクを抽出
jq -r '.tasks[] | select(.assigned_to == "Alex" and .status == "DONE") | .slug' \
  .claude/_queue.json

# ステップ3: DECISIONS.md の直近スプリントエントリを確認
grep -A 30 "^## $(jq -r '.sprint' .claude/_queue.json)" docs/DECISIONS.md | \
  grep -A 5 "次スプリントへの推奨"
```

### 2.3 「実装完了状態の突合」チェックリスト

スプリント計画時に Yuki がオーナーへ提示するチェックリストに
以下を追加する:

```markdown
### 前スプリント実装状態の突合（新規追加）

- [ ] 前スプリントで Alex が設計したタスクに対応する実装が完了しているか確認した
      （設計あり・実装なし → 新スプリントの実装候補に追加）
- [ ] 前スプリントで実装されたが計画になかったものがないか確認した
      （_signals.jsonl の task.done イベントを確認）
- [ ] DECISIONS.md の「次スプリントへの推奨」を今回のタスク分解に反映した
      （具体的な反映内容: [例: risk_level: high を最初のフェーズに配置]）
- [ ] 前スプリントで start → done が異常に短かったタスクがないか確認した
      （elapsed < 60秒 は計画重複の疑いがある）
```

### 2.4 elapsed 短時間検出ロジック

_signals.jsonl を用いた計画重複検出:

```bash
# task.start → task.done のペアで elapsed を計算し、短すぎるものをフラグ
python3 - << 'EOF'
import json
from datetime import datetime, timezone
from pathlib import Path

signals = []
signals_file = Path(".claude/_signals.jsonl")
if signals_file.exists():
    for line in signals_file.read_text().splitlines():
        try:
            signals.append(json.loads(line))
        except Exception:
            pass

starts = {s["slug"]: s["ts"] for s in signals if s["type"] == "task.start"}
dones  = {s["slug"]: s["ts"] for s in signals if s["type"] == "task.done"}

THRESHOLD_SECS = 60
for slug, done_ts in dones.items():
    if slug in starts:
        start_dt = datetime.fromisoformat(starts[slug].replace("+0000", "+00:00"))
        done_dt  = datetime.fromisoformat(done_ts.replace("+0000", "+00:00"))
        elapsed  = (done_dt - start_dt).total_seconds()
        if 0 <= elapsed < THRESHOLD_SECS:
            print(f"WARN: {slug} が {elapsed:.0f}秒で完了（計画重複の可能性）")
EOF
```

---

## 3. pm.md への追記箇所の提案

### 3.1 追記対象セクション

**変更対象**: `.claude/agents/pm.md` の「スプリント開始前チェック」セクション（69〜77行）

### 3.2 現行テキスト

```markdown
## スプリント開始前チェック

新スプリントを計画する前に `docs/DECISIONS.md` を確認し、
前スプリントの失敗パターンと推奨アクションをタスク設計に反映する。

- 直前スプリントの「失敗パターン」に同種のタスクがないか
- 「次スプリントへの推奨」で指摘された事項に対処したか
- risk_level: high のタスクを最初のフェーズに配置したか
```

### 3.3 提案する変更後テキスト

```markdown
## スプリント開始前チェック

新スプリントを計画する前に、以下の手順で前スプリントの状態を確認する。
**確認を省略してタスク分解を始めてはいけない。**

### ステップ1: 前スプリントの実装完了状態の突合

```bash
# 完了タスクと実装内容を確認
jq -r '.tasks[] | select(.status == "DONE") |
  .slug + " (" + (.assigned_to // "?") + "): " + (.summary // "（要約なし）")
' .claude/_queue.json

# elapsed が短すぎるタスクをフラグ（計画重複の可能性）
# ※ docs/spec/feedback-loop-doc.md §2.4 のスクリプトを参照
```

確認内容:
- 設計タスク（Alex担当）に対応する実装タスクが DONE になっているか
- start → done が 60秒未満のタスクがある場合、計画重複を疑って調査する

### ステップ2: DECISIONS.md の確認

```bash
# 最新スプリントエントリを確認
tail -n 40 docs/DECISIONS.md
```

確認内容:
- 「失敗パターン」に今回のタスクと同種のものがないか
- 「次スプリントへの推奨」を具体的にタスク設計に落とし込んだか
- risk_level: high のタスクを最初のフェーズに配置したか

### ステップ3: 確認結果をスプリント計画案に明記する

スプリント計画案の「確認事項」セクションに以下を追加すること:

- [ ] 前スプリントの設計完了タスクとの突合: 実施済み（結果: [一行で]）
- [ ] 計画重複タスク: なし / あり（[slug]: [対処]）
- [ ] DECISIONS.md 反映: [具体的に何を反映したか]
```

### 3.4 変更の意図

| 変更点 | 理由 |
|--------|------|
| コマンドを明示 | 「確認する」という抽象指示では実行されないため |
| **確認を省略しない**を明記 | チェックを任意扱いにしない |
| elapsed チェックを追加 | Sprint-10 の失敗を検出できる仕組みを作る |
| 確認結果の明記を義務化 | 確認したことをオーナーが検証できるようにする |

---

## 4. 将来の拡張（今スプリントのスコープ外）

### 4.1 自動突合スクリプトの実装

現在は手動コマンドで確認しているが、
`scripts/queue.sh preflight` のようなコマンドで自動化できる。

```bash
# 将来の実装例
scripts/queue.sh preflight   # スプリント計画前チェックを自動実行
```

### 4.2 _signals.jsonl の sprint フィールド活用

現在 _signals.jsonl にはスプリント名が記録されているが、
クロススプリント分析（「スプリントXで設計したものをスプリントYで実装した」）
は手動になっている。将来的に queue.py の retro コマンドに
「前スプリント対比」レポートを追加することで自動化できる。

---

## 5. Riku への実装依頼事項（今スプリント）

本タスクはドキュメント設計のみのため、実装は最小限とする。

**必須**: pm.md の「スプリント開始前チェック」セクションを §3.3 の内容で更新する。

```bash
# 更新対象ファイル
.claude/agents/pm.md  # 69〜77行を §3.3 の内容に置き換える
```

これは設計書（Alex）ではなく実装（Riku担当）とする理由:
- pm.md はエージェント定義ファイルのため、実装タスクとして扱う
- 本設計書（feedback-loop-doc.md）がその仕様書となる

---

## 6. 完了確認

- [ ] `docs/spec/feedback-loop-doc.md` が作成されている（本ファイル）
- [ ] pm.md の「スプリント開始前チェック」セクションに §3.3 の内容が反映されている
- [ ] pm.md 更新後に Yuki が次スプリント計画時に実際に手順を踏めることを
      スプリント計画案の「確認事項」セクションで検証する
