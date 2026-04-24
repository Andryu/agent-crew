# ADR-008: queue.sh → queue.py 段階移行

## Status

Accepted（2026-04-24）

## Context

`scripts/queue.sh` は Sprint-01 から継続的に拡張されてきた 1030 行の Bash スクリプトである。
現状で以下の本質的な問題を抱えており、スプリントをまたぐたびに修正コストが増加している。

### 既知の問題

| 問題 | 深刻度 | 根本原因 |
|------|--------|---------|
| Issue #66: `${4:-{}}` バグ（Bash 変数展開がネストした JSON の `}` を閉じ括弧と誤解釈する） | Priority 9 | JSON を Bash 文字列で組み立てることの構造的限界 |
| `set -e + \|\| true` パターンによるサイレント失敗 | 高 | Bash エラー制御の表現力不足 |
| ユニットテストが書けない | 高 | Bash 関数は独立したテストハーネスを持てない |
| 1030 行で関数合成の上限が近い | 中 | 可読性・保守性の臨界点 |
| タイムゾーン変換の環境依存（`date -j` vs `date -d`） | 中 | macOS/Linux 差異 |

### 移行しない場合のリスク

- Issue #66 のような「Bash では原理的に直せない」バグが今後も発生し続ける
- 関数数の増加とともにデバッグコストが指数的に増加する
- Sora（QAエージェント）がテストを書けないためリグレッションを人手で確認し続ける

---

## Decision

`scripts/queue.py` を新規作成し、**`queue.sh` と並走する形で段階移行**する。

技術スタックは以下の通り:
- Python 3.11+
- `typer[all]`（CLIフレームワーク）
- `pydantic v2`（JSONスキーマ型保証）
- `pytest`（テストフレームワーク）

追加依存は `typer[all]` のみとし、標準ライブラリ（`fcntl`, `json`, `pathlib`, `datetime`）で実装できる部分は外部ライブラリを使わない。

---

## 選択肢と比較

### オプション A: Python + typer + pydantic（採用）

**メリット**
- pydantic により JSON スキーマが型として表現される（`${4:-{}}` 問題が構造的に再発しない）
- pytest でユニットテストが書ける（ロジック単体・ファイルモック・並行性テスト）
- `fcntl.flock` による OS レベルのファイルロック（`mkdir` ロックより堅牢）
- Python の例外処理が Bash の `set -e + || true` より遥かに明示的
- typer により `--help` が自動生成され、ドキュメントとコードが一致する

**デメリット**
- Python 3.11 がインストールされていない環境では動かない
- `typer[all]` の依存（`rich`, `click`）が増える

**トレードオフ**: 環境依存が増えるが、agent-crew は macOS 開発環境での使用を前提としており Python 3.11 は既に利用可能。

### オプション B: Node.js + zx

**メリット**: Bash に近い感覚でシェルコマンドが呼べる

**デメリット**: JSON 操作は Python + pydantic に劣る。型保証が弱い。既存の JS 資産がない。

### オプション C: Go（queue.sh を Go で書き直す）

**メリット**: シングルバイナリ、高速、型安全

**デメリット**: スプリント内で完成させるには実装コストが高い。テストまで含めると S→M 規模になる。将来のフェーズで検討余地あり。

### オプション D: Bash のまま修正を続ける

**デメリット**: Issue #66 の本質的解決が不可能。テストが書けない問題は残存する。1030 行を超えると保守コストが許容範囲を超える。

---

## Consequences

### 良くなること

- JSON の組み立てに文字列フォーマットを使わない（pydantic の `.model_dump_json()` を使う）
- ユニットテストが pytest で書ける
- コマンドの追加コストが低下する（typer の `@app.command()` で完結）
- エラーメッセージが例外 traceback で追跡可能

### 悪くなること（受け入れるトレードオフ）

- `queue.sh` と `queue.py` の並走期間中、変更を両方に反映する必要がある
- `typer[all]` の依存が追加される（`pyproject.toml` または `requirements.txt` の管理が必要）

### 変わらないこと

- `.claude/_queue.json` のスキーマは一切変更しない（完全後方互換）
- `_signals.jsonl` への emit 仕様も変更しない
- 外部インターフェース（コマンド名・引数・終了コード・stdout フォーマット）は `queue.sh` と同一

---

## ファイル構造

```
scripts/
├── queue.sh          # 既存（削除しない・並走）
└── queue.py          # 新規作成（Phase 1 全コマンド実装）

tests/
└── test_queue_py.py  # pytest ユニットテスト（10ケース以上）
```

`queue.py` の内部モジュール構造（単一ファイル、関数グループで区切る）:

```python
# scripts/queue.py
#
# セクション構成:
#   1. Pydantic モデル定義（Task, QueueFile, SignalEvent）
#   2. ファイルロック・アトミック書き込みユーティリティ
#   3. タイムスタンプ・リスク計算ヘルパー
#   4. typer コマンド実装（start/done/handoff/parallel_handoff/qa/retry/block/show/next/graph/detect_stale/retro）
#   5. エントリポイント（if __name__ == "__main__": app()）
```

単一ファイルを選択した理由: 1030 行規模のスクリプトであり、パッケージ構造を持つほどの複雑さではない。モジュール分割は将来の Go 移行時に行う。

---

## Pydantic モデル定義

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------- タスクイベント ----------

class TaskEvent(BaseModel):
    ts: str                          # ISO 8601（例: "2026-04-24T02:23:38+0000"）
    agent: str
    action: Literal[
        "start", "done", "handoff", "qa", "block", "retry"
    ]
    msg: str


# ---------- タスク ----------

TaskStatus = Literal[
    "TODO",
    "IN_PROGRESS",
    "DONE",
    "BLOCKED",
    "READY_FOR_ALEX",
    "READY_FOR_RIKU",
    "READY_FOR_MINA",
    "READY_FOR_SORA",
    "READY_FOR_YUKI",
]

Complexity = Literal["S", "M", "L"]

RiskLevel = Literal["low", "medium", "high"]

QaResult = Literal["APPROVED", "CHANGES_REQUESTED"]


class Task(BaseModel):
    slug: str
    title: str
    status: TaskStatus
    assigned_to: str
    complexity: Optional[Complexity] = None
    risk_level: Optional[RiskLevel] = None
    parallel_group: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)
    qa_mode: Optional[str] = None
    created_at: str
    updated_at: str
    notes: Optional[str] = None
    retry_count: int = 0
    qa_result: Optional[QaResult] = None
    summary: Optional[str] = None
    events: list[TaskEvent] = Field(default_factory=list)


# ---------- キューファイル全体 ----------

class QueueFile(BaseModel):
    sprint: str
    tasks: list[Task]


# ---------- signals.jsonl の1行 ----------

SignalAction = Literal[
    "task_started",
    "task_done",
    "task_blocked",
    "qa_result",
    "retry",
    "handoff",
]


class SignalEvent(BaseModel):
    ts: str
    sprint: str
    slug: str
    agent: str
    action: SignalAction
    payload: dict = Field(default_factory=dict)
```

**設計上の注意点**:
- `TaskStatus` の `READY_FOR_*` は現状のエージェント数に固定している。新エージェント追加時はここを更新する（Bash では暗黙的に許容していた問題を型で明示する）
- `QueueFile` は `tasks` フィールドを list で持ち、dict-by-slug ではなくリスト順を保持する（既存 JSON スキーマとの互換）
- `Signal` の `payload` は `dict` とし、action ごとの型付けは Phase 2 以降に委ねる（今は柔軟性を優先）

---

## コマンドインターフェース（typer）

```python
import typer

app = typer.Typer()


@app.command()
def start(slug: str) -> None:
    """タスクを IN_PROGRESS に遷移する（depends_on 全 DONE チェックあり）"""


@app.command()
def done(
    slug: str,
    agent: str,
    summary: str = typer.Argument(default="完了"),
) -> None:
    """タスクを DONE に遷移し、summary と events を記録する"""


@app.command()
def handoff(slug: str, next_agent: str) -> None:
    """次タスクを READY_FOR_<AGENT> に遷移する"""


@app.command("parallel-handoff")
def parallel_handoff(
    pairs: list[str] = typer.Argument(..., help="slug:agent 形式で複数指定"),
) -> None:
    """複数タスクを単一ロック内で一括ハンドオフする"""


@app.command()
def qa(
    slug: str,
    result: str = typer.Argument(..., help="APPROVED | CHANGES_REQUESTED"),
    summary: str = typer.Argument(default=""),
) -> None:
    """qa_result を記録する（Sora 専用）"""


@app.command()
def block(slug: str, agent: str, reason: str) -> None:
    """タスクを BLOCKED に遷移する"""


@app.command()
def retry(slug: str) -> None:
    """retry_count を増やして READY_FOR_RIKU に戻す（上限超過で BLOCKED）"""


@app.command()
def show(slug: Optional[str] = None) -> None:
    """タスク一覧または指定タスクの詳細を表示する"""


@app.command()
def next() -> None:
    """次に実行可能な READY_FOR_* タスクを1件返す"""


@app.command()
def graph(save: bool = typer.Option(False, "--save")) -> None:
    """Mermaid 依存グラフを stdout に出力する"""


@app.command("detect-stale")
def detect_stale(
    threshold: int = typer.Option(60, "--threshold", help="分"),
    slack: bool = typer.Option(False, "--slack"),
) -> None:
    """中断タスク（IN_PROGRESS >= N 分）を検出して stderr に警告する"""


@app.command()
def retro(
    save: bool = typer.Option(False, "--save"),
    decisions: bool = typer.Option(False, "--decisions"),
) -> None:
    """スプリント完了メトリクスを集計する"""
```

**Bash との終了コード互換**:

| 状況 | `queue.sh` exit code | `queue.py` 実装方法 |
|------|---------------------|-------------------|
| 正常終了 | 0 | デフォルト |
| slug not found | 6 | `typer.Exit(6)` |
| 依存未解決 | 9 | `typer.Exit(9)` |
| ロック取得失敗 | 2 | `typer.Exit(2)` |
| retry 上限超過 | 8 | `typer.Exit(8)` |

---

## ファイルロック設計

Bash では `mkdir` によるアトミックロックを使用していた。Python では `fcntl.flock` を使う。

```python
import fcntl
import contextlib
from pathlib import Path


@contextlib.contextmanager
def queue_lock(queue_file: Path, timeout_secs: float = 5.0):
    """
    fcntl.flock による排他ロック。
    - ロックファイル: <queue_file>.lock
    - タイムアウト: デフォルト 5 秒
    - コンテキストマネージャとして使用（with queue_lock(path): ...）
    """
    lock_path = queue_file.with_suffix(".lock")
    ...
```

`fcntl.flock` を採用する理由:
- プロセス終了時に OS が自動解放する（`mkdir` ロックはクラッシュ時に残留する）
- タイムアウト付きの `select` と組み合わせられる
- Windows では動作しないが、agent-crew は macOS 専用のため問題なし

---

## アトミック書き込み設計

```python
def atomic_write(queue_file: Path, queue_data: QueueFile) -> None:
    """
    1. tempfile.NamedTemporaryFile で同一ディレクトリに一時ファイルを書き込む
    2. pydantic の model_dump_json(indent=2) でシリアライズ（文字列フォーマット不使用）
    3. os.replace() でアトミックに置換する（POSIX rename セマンティクス）
    """
```

Bash の `atomic_write` との違い: `printf '%s\n'` → `tmp` → `mv` の流れは同じだが、JSON 生成に文字列結合を使わない点が本質的な改善。

---

## 移行戦略

### Phase 1（Sprint-09）: 並走実装

```
queue.sh  ─── 既存のまま維持（削除しない）
queue.py  ─── 全コマンドを新規実装
```

エージェントは引き続き `queue.sh` を呼ぶ。`queue.py` は並走するが、実際の queue 操作には使わない。
Sora が `tests/test_queue_py.py` の全ケースを APPROVED すれば Phase 2 に進む。

### Phase 2（Sprint-10 候補）: 並走運用・エージェントへの段階展開

```
queue.sh  ─── 残存（フォールバック用）
queue.py  ─── エージェントの queue 操作に使い始める（Yuki が queue.py を優先呼び出し）
```

移行の判断基準:
1. `pytest tests/test_queue_py.py` が全パス
2. `queue.py show` と `queue.sh show` の出力が同一
3. `queue.py` で `.claude/_queue.json` を読み書きし、`queue.sh` でも正しく読める（双方向互換）

### Phase 3（Sprint-11 以降）: queue.sh 廃止

```
queue.py  ─── 唯一の queue 操作手段
queue.sh  ─── アーカイブ（scripts/queue.sh.bak または削除）
```

廃止の前提条件:
- Phase 2 での並走期間で問題が報告されないこと（2 スプリント以上）
- `queue.py --help` がすべてのコマンドを正しく列挙できること

---

## テスト方針（pytest）

テストファイル: `tests/test_queue_py.py`

### テストカテゴリと最低ケース数

| カテゴリ | テストケース例 | 最低件数 |
|--------|-------------|---------|
| Pydantic モデル | 正常な JSON を `QueueFile.model_validate()` でパースできる | 3 |
| `start` コマンド | depends_on 未解決でエラー / 正常遷移 / IN_PROGRESS 重複でエラー | 3 |
| `done` コマンド | DONE への正常遷移 / events に done アクションが追記される | 2 |
| `handoff` コマンド | READY_FOR_RIKU への遷移 | 1 |
| `qa` コマンド | APPROVED 記録 / CHANGES_REQUESTED 記録 / 重複 qa でエラー | 3 |
| `retry` コマンド | retry_count インクリメント / MAX_RETRY 超過で BLOCKED | 2 |
| アトミック書き込み | 書き込み後の JSON が pydantic でパースできる | 1 |
| スキーマ互換 | queue.sh が生成した JSON を queue.py が正しく読める | 1 |
| ファイルロック | ロック保持中に別プロセスが timeout で失敗する | 1 |

合計: 17 ケース以上（必須最低 10 ケース）

### テスト設計の方針

```python
import pytest
import json
import tempfile
from pathlib import Path

# fixtureで一時ファイルを使い、実際の .claude/_queue.json に触れない
@pytest.fixture
def tmp_queue(tmp_path: Path) -> Path:
    queue_file = tmp_path / "_queue.json"
    # テスト用の最小限 QueueFile を書き込む
    ...
    return queue_file
```

- 実際の `.claude/_queue.json` には触れない（`tmp_path` フィクスチャを使う）
- コマンドは typer の `CliRunner` ではなく内部関数を直接テストする（ユニットテストの観点から）
- `queue.sh` との互換テストのみ `subprocess.run` を使う

---

## Riku への引き継ぎ

### 実装上の重要注意点

1. **`${4:-{}}` 問題の再発防止**: JSON の組み立てに f-string や `%` フォーマットを使わない。必ず `pydantic.BaseModel.model_dump()` または `json.dumps()` を使う。

2. **終了コードの互換**: 各コマンドの失敗パターンで `typer.Exit(<code>)` を返し、Bash と同じ exit code を維持する（エージェントの `if [[ $? -ne 0 ]]` が壊れないため）。

3. **`_signals.jsonl` への emit**: `done` コマンド完了時に `.claude/_signals.jsonl` に `SignalEvent` を JSONL 形式で追記する。既存の Bash 実装を参照して同じフォーマットにする。

4. **ファイルパスの環境変数**: `QUEUE_FILE` 環境変数を優先し、未設定時は `.claude/_queue.json` をデフォルトにする（Bash と同じ挙動）。

5. **typer の `next` コマンド**: Python の組み込み `next()` 関数と名前衝突する。typer では `name="next"` を明示的に指定する。

```python
@app.command(name="next")
def cmd_next() -> None:
    ...
```

6. **`retro` コマンドの `ts_to_epoch`**: Bash では macOS/Linux 差異を `date -j` / `date -d` で吸収していた。Python では `datetime.fromisoformat()` + `dateutil.parser.parse()` で統一する（`python-dateutil` は `typer[all]` の依存に含まれないため、標準ライブラリの `datetime.fromisoformat()` で対応できる範囲に限定する）。

---

## Mina への引き継ぎ

このタスクは UX 設計を必要としない純粋な内部インフラ移行である。ただし、将来的に `queue.py` の出力（`show`, `retro`）を Web UI でビジュアライズする場合、`QueueFile` モデルがそのまま REST API レスポンスの型として使えることを考慮した設計にしている。
