# graph-py-design — cmd_graph の queue.py 移植設計書

## 概要

`scripts/queue.sh` の `cmd_graph` 関数（Mermaid依存グラフ生成）を
`scripts/queue.py` に移植する。

legacy-delete-design でも述べた通り、`cmd_graph` は現在 Bash 実装のまま残っており、
`queue.py` には未実装である。本設計書は移植の詳細を定義する。

---

## 1. 現行の `cmd_graph` 実装分析

### 1.1 機能概要

`_queue.json` を読み込み、タスクの依存関係を Mermaid `flowchart LR` 形式で出力する。

**入力**: `_queue.json`（`QUEUE_FILE` 環境変数）
**出力**: STDOUT に Mermaid コードブロック

### 1.2 処理ステップ

1. **スプリント名取得**: `.sprint` フィールドを読む
2. **ノード定義生成**: 各タスクを以下の形式で出力する
   ```
   <slug>["<slug>\n(<assigned_to> · <status>)"]:::<classname>
   ```
   クラス名（状態→CSS class）のマッピング:
   - `READY_FOR_*` → `ready`
   - `IN_PROGRESS` → `in_progress`
   - `DONE` → `done`
   - `BLOCKED` → `blocked`
   - その他（`TODO` など） → `todo`

3. **エッジ定義生成**: `depends_on[]` を走査して `dep --> slug` を生成
4. **classDef 出力**: 5つのカラー定義を固定文字列で出力
5. **`--save` フラグ**: `docs/graphs/<sprint>.md` にファイルを保存

### 1.3 オプション

| フラグ | 動作 |
|--------|------|
| `--save` | `docs/graphs/<sprint>.md` にMarkdown形式で保存 |
| （なし） | STDOUTに出力のみ |

### 1.4 現行実装の行数内訳

```
cmd_graph 全体: 75行（685–759行）
  - フラグパース: 5行
  - スプリント名取得: 3行
  - ノード生成（jq）: 12行
  - エッジ生成（jq）: 6行
  - Mermaid出力: 12行
  - --save 処理: 25行
  - 重複出力（save時）: 12行
```

---

## 2. Python実装の設計

### 2.1 typer コマンド定義

```python
@app.command()
def graph(
    save: bool = typer.Option(False, "--save", help="docs/graphs/<sprint>.md に保存"),
) -> None:
    """タスク依存関係を Mermaid flowchart LR 形式で出力する"""
    q = load_queue()
    mermaid_lines = _build_mermaid(q)
    output = "\n".join(mermaid_lines)

    print("```mermaid")
    print(output)
    print("```")

    if save:
        _save_graph(q.sprint, output)
```

### 2.2 状態→CSSクラスのマッピング関数

```python
def _status_to_class(status: str) -> str:
    if status.startswith("READY_FOR_"):
        return "ready"
    return {
        "IN_PROGRESS": "in_progress",
        "DONE": "done",
        "BLOCKED": "blocked",
    }.get(status, "todo")
```

### 2.3 Mermaid文字列生成（_build_mermaid）

```python
MERMAID_CLASS_DEFS = [
    "  classDef done fill:#22c55e,color:#fff",
    "  classDef in_progress fill:#f59e0b,color:#fff",
    "  classDef blocked fill:#ef4444,color:#fff",
    "  classDef ready fill:#3b82f6,color:#fff",
    "  classDef todo fill:#e5e7eb,color:#374151",
]

def _build_mermaid(q: QueueFile) -> list[str]:
    lines = ["flowchart LR"]

    # ノード定義
    for task in q.tasks:
        cls = _status_to_class(task.status)
        agent = task.assigned_to or "?"
        label = f"{task.slug}\\n({agent} · {task.status})"
        lines.append(f'  {task.slug}["{label}"]:::{cls}')

    lines.append("")

    # エッジ定義
    for task in q.tasks:
        for dep in task.depends_on:
            lines.append(f"  {dep} --> {task.slug}")

    lines.append("")
    lines.extend(MERMAID_CLASS_DEFS)

    return lines
```

### 2.4 ファイル保存（_save_graph）

```python
def _save_graph(sprint: str, mermaid_body: str) -> None:
    # QUEUE_FILE からプロジェクトルートを推定
    project_root = QUEUE_FILE.parent.parent
    graphs_dir = project_root / "docs" / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    out_file = graphs_dir / f"{sprint}.md"

    content = f"# {sprint} — Mermaid依存グラフ\n\n```mermaid\n{mermaid_body}\n```\n"
    out_file.write_text(content)
    typer.echo(f"OK: graph saved to {out_file}", err=True)
```

---

## 3. queue.sh とのインターフェース互換性

### 3.1 コマンドライン互換

| 呼び出し形式 | 現行（Bash） | 移植後（Python） | 互換性 |
|------------|------------|----------------|--------|
| `queue.sh graph` | Bash cmd_graph | Python graph | 同一 |
| `queue.sh graph --save` | Bash --save | Python --save | 同一 |
| 出力形式（STDOUT） | Mermaid block | Mermaid block | 同一 |
| 保存先 | `docs/graphs/<sprint>.md` | `docs/graphs/<sprint>.md` | 同一 |
| ファイル内容フォーマット | `# <sprint> — Mermaid依存グラフ` | 同一 | 同一 |

### 3.2 queue.sh ディスパッチ変更

移植後、queue.sh の `graph` ケースを Python 委譲に変更する。

**変更前**（現行）:
```bash
case "$cmd" in
  graph)
    cmd_graph "$@"
    ;;
  ...
```

**変更後**:
```bash
_PY_COMMANDS="start done handoff qa block retry show next detect-stale graph"

case "$cmd" in
  parallel-handoff)
    cmd_parallel_handoff "$@"
    ;;
  retro)
    cmd_retro "$@"
    ;;
  ""|help|-h|--help)
    sed -n '2,28p' "$0"
    ;;
  *)
    if printf '%s\n' $_PY_COMMANDS | grep -qx "$cmd"; then
      exec python3 "$(dirname "$0")/queue.py" "$cmd" "$@"
    fi
    echo "ERROR: unknown command: $cmd" >&2
    exit 1
    ;;
esac
```

これにより `cmd_graph` 関数も legacy-delete-design の削除対象に加わる。

### 3.3 出力フォーマットの注意点

Bash 実装と Python 実装でノード定義の生成順序が同一になるよう、
`q.tasks` のリスト順（`_queue.json` の記述順）をそのまま使う。
ソートを加えると Mermaid のレイアウトが変わる可能性があるため避ける。

---

## 4. テスト戦略

### 4.1 ユニットテスト（pytest）

`tests/test_queue_py.py` に以下のテストケースを追加する。

```python
# ---- graph コマンドのテスト ----

def test_graph_outputs_mermaid(tmp_path, runner):
    """graph コマンドが Mermaid コードブロックを出力する"""
    queue_file = tmp_path / "_queue.json"
    queue_file.write_text(json.dumps({
        "sprint": "test-sprint",
        "tasks": [
            {
                "slug": "task-a",
                "title": "Task A",
                "status": "DONE",
                "assigned_to": "Riku",
                "complexity": "S",
                "depends_on": [],
                "retry_count": 0,
                "qa_result": None,
                "events": [],
                "created_at": "2026-04-24",
                "updated_at": "2026-04-24",
            },
            {
                "slug": "task-b",
                "title": "Task B",
                "status": "IN_PROGRESS",
                "assigned_to": "Riku",
                "complexity": "M",
                "depends_on": ["task-a"],
                "retry_count": 0,
                "qa_result": None,
                "events": [],
                "created_at": "2026-04-24",
                "updated_at": "2026-04-24",
            },
        ]
    }))
    env = {"QUEUE_FILE": str(queue_file)}
    result = runner.invoke(app, ["graph"], env=env)
    assert result.exit_code == 0
    assert "```mermaid" in result.output
    assert "flowchart LR" in result.output
    assert "task-a" in result.output
    assert "task-b" in result.output
    assert "task-a --> task-b" in result.output
    assert "classDef done" in result.output


def test_graph_status_classes(tmp_path, runner):
    """各ステータスが正しいCSSクラスにマッピングされる"""
    # READY_FOR_* → ready
    # IN_PROGRESS → in_progress
    # DONE → done
    # BLOCKED → blocked
    # TODO → todo


def test_graph_save(tmp_path, runner):
    """--save フラグで docs/graphs/<sprint>.md が生成される"""
    # ...ファイルが作成され、内容が正しいことを確認


def test_graph_no_edges(tmp_path, runner):
    """depends_on が空の場合エッジなしで正常終了する"""
```

### 4.2 スモークテスト（CLI）

```bash
export QUEUE_FILE=/tmp/test_graph.json
# テストキューを作成（task-a→task-b の依存関係あり）

# 基本出力確認
scripts/queue.sh graph | grep -q "flowchart LR" && echo "PASS: flowchart LR found"
scripts/queue.sh graph | grep -q "task-a --> task-b" && echo "PASS: edge found"
scripts/queue.sh graph | grep -q "classDef done" && echo "PASS: classDef found"

# --save 確認
scripts/queue.sh graph --save
test -f "docs/graphs/test-sprint.md" && echo "PASS: file saved"
grep -q "Mermaid依存グラフ" "docs/graphs/test-sprint.md" && echo "PASS: header found"
```

### 4.3 Bash 実装との出力差分確認

移植後の出力を Bash 実装の出力と比較する（--save ファイルで確認）。

```bash
# Bash 実装で出力
QUEUE_FILE=... bash scripts/queue.sh graph > /tmp/graph_bash.txt

# Python 実装で出力（直接呼び出し）
QUEUE_FILE=... python3 scripts/queue.py graph > /tmp/graph_python.txt

# 差分確認（空白の違いのみ許容）
diff <(sed 's/[[:space:]]*$//' /tmp/graph_bash.txt) \
     <(sed 's/[[:space:]]*$//' /tmp/graph_python.txt)
```

---

## 5. 実装タスクへの引き継ぎ（Riku向け）

### 必須実装事項

1. `queue.py` に `graph` コマンドを追加（`@app.command(name="graph")`）
2. `_status_to_class` ヘルパー関数を追加
3. `_build_mermaid` ヘルパー関数を追加（MERMAID_CLASS_DEFS は定数として定義）
4. `_save_graph` ヘルパー関数を追加

### queue.sh の変更事項

5. `_PY_COMMANDS` 変数に `graph` を追加
6. `case "$cmd"` から `graph)` ケースを削除
7. `cmd_graph` 関数を削除（legacy-delete-impl と合わせて実施）

### 確認事項

- `queue.sh graph` と `python3 scripts/queue.py graph` の出力が同一であること
- `--save` ファイルのパスと内容が同一であること
- `QUEUE_FILE` 環境変数が正しく参照されること

---

## 6. 依存関係

- **前提**: `legacy-delete-design` の方針を踏まえた実装（`legacy-delete-impl`）
- **後続**: `graph` 移植完了後、queue.sh の `cmd_graph` を削除対象リストに追加する
