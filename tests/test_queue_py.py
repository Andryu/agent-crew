"""
tests/test_queue_py.py — queue.py ユニットテスト

queue.sh との互換確認・各コマンドの正常/異常系を検証する。
実際の .claude/_queue.json には触れない（tmp_path フィクスチャを使用）。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# queue.py をインポートできるよう scripts/ を path に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# uv run 経由でないと typer/pydantic が見つからない場合があるため
# 直接インポートを試みる
try:
    import queue as _queue_module  # 標準ライブラリと衝突を避けるため
    from scripts import queue as qmod  # noqa: F401 — 使えない場合は subprocess でテスト
except Exception:
    pass

# ---------- フィクスチャ ----------

MINIMAL_QUEUE = {
    "sprint": "test-sprint",
    "tasks": [
        {
            "slug": "task-a",
            "title": "Task A",
            "status": "TODO",
            "assigned_to": "Riku",
            "complexity": "S",
            "risk_level": "low",
            "parallel_group": None,
            "depends_on": [],
            "qa_mode": "inline",
            "created_at": "2026-04-24",
            "updated_at": "2026-04-24",
            "notes": "Issue #99 のテスト",
            "retry_count": 0,
            "qa_result": None,
            "summary": None,
            "events": []
        },
        {
            "slug": "task-b",
            "title": "Task B",
            "status": "TODO",
            "assigned_to": "Sora",
            "complexity": "M",
            "risk_level": "medium",
            "parallel_group": None,
            "depends_on": ["task-a"],
            "qa_mode": None,
            "created_at": "2026-04-24",
            "updated_at": "2026-04-24",
            "notes": None,
            "retry_count": 0,
            "qa_result": None,
            "summary": None,
            "events": []
        }
    ]
}


@pytest.fixture
def tmp_queue(tmp_path: Path) -> Path:
    queue_file = tmp_path / "_queue.json"
    queue_file.write_text(json.dumps(MINIMAL_QUEUE, indent=2, ensure_ascii=False))
    return queue_file


def run_queue(args: list[str], queue_file: Path) -> subprocess.CompletedProcess:
    """uv run scripts/queue.py <args> を環境変数 QUEUE_FILE 付きで実行する"""
    uv = str(Path.home() / ".local/bin/uv")
    env = {**os.environ, "QUEUE_FILE": str(queue_file)}
    return subprocess.run(
        [uv, "run", "scripts/queue.py"] + args,
        capture_output=True, text=True, env=env
    )


# ---------- Pydantic モデルテスト ----------

def test_model_parse_minimal_queue(tmp_queue):
    """最小限のキューJSONをQueueFileとしてパースできる（show コマンド経由で検証）"""
    result = run_queue(["show"], tmp_queue)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert data[0]["slug"] == "task-a"


def test_model_task_event_fields(tmp_queue):
    """TaskEvent の ts/agent/action/msg フィールドが保持される"""
    data = json.loads(tmp_queue.read_text())
    task = data["tasks"][0]
    task["events"].append({"ts": "2026-01-01T00:00:00+0000", "agent": "Riku", "action": "start", "msg": "着手"})
    tmp_queue.write_text(json.dumps(data, indent=2))
    result = run_queue(["show", "task-a"], tmp_queue)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["events"][0]["action"] == "start"


def test_model_rejects_invalid_json(tmp_path):
    """不正JSONのキューファイルで load_queue がエラー終了する"""
    bad_file = tmp_path / "_queue.json"
    bad_file.write_text("{invalid json")
    result = run_queue(["show"], bad_file)
    assert result.returncode != 0
    assert "ERROR" in result.stderr

# ---------- start コマンドテスト ----------

def test_start_normal(tmp_queue):
    """TODO タスクを start すると IN_PROGRESS になる"""
    result = run_queue(["start", "task-a"], tmp_queue)
    assert result.returncode == 0, result.stderr
    assert "IN_PROGRESS" in result.stdout
    data = json.loads(tmp_queue.read_text())
    task = next(t for t in data["tasks"] if t["slug"] == "task-a")
    assert task["status"] == "IN_PROGRESS"
    assert any(e["action"] == "start" for e in task["events"])


def test_start_dependency_unresolved(tmp_queue):
    """depends_on が未解決のタスクは start できない"""
    result = run_queue(["start", "task-b"], tmp_queue)
    assert result.returncode == 9
    assert "unresolved" in result.stderr


def test_start_duplicate(tmp_queue):
    """IN_PROGRESS のタスクを再度 start するとエラー"""
    run_queue(["start", "task-a"], tmp_queue)
    result = run_queue(["start", "task-a"], tmp_queue)
    assert result.returncode == 11


def test_start_invalid_complexity(tmp_path):
    """complexity が S/M/L 以外のタスクは start できない（exit 10）"""
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["complexity"] = "XL"  # 不正な complexity
    queue_file.write_text(json.dumps(data))
    result = run_queue(["start", "task-a"], queue_file)
    assert result.returncode == 10
    assert "complexity" in result.stderr

# ---------- done コマンドテスト ----------

def test_done_normal(tmp_queue):
    """start → done で DONE に遷移し summary が記録される"""
    run_queue(["start", "task-a"], tmp_queue)
    result = run_queue(["done", "task-a", "Riku", "実装完了"], tmp_queue)
    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout
    data = json.loads(tmp_queue.read_text())
    task = next(t for t in data["tasks"] if t["slug"] == "task-a")
    assert task["status"] == "DONE"
    assert task["summary"] == "実装完了"
    assert any(e["action"] == "done" for e in task["events"])


def test_done_duplicate(tmp_queue):
    """DONE タスクを再度 done するとエラー"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
    result = run_queue(["done", "task-a", "Riku", "再完了"], tmp_queue)
    assert result.returncode == 15

# ---------- handoff コマンドテスト ----------

def test_handoff_sets_ready_for(tmp_queue):
    """handoff で READY_FOR_SORA に遷移する"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
    result = run_queue(["handoff", "task-b", "Sora"], tmp_queue)
    assert result.returncode == 0
    data = json.loads(tmp_queue.read_text())
    task = next(t for t in data["tasks"] if t["slug"] == "task-b")
    assert task["status"] == "READY_FOR_SORA"

# ---------- qa コマンドテスト ----------

def test_qa_approved(tmp_queue):
    """qa APPROVED が正しく記録される"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
    result = run_queue(["qa", "task-a", "APPROVED", "問題なし"], tmp_queue)
    assert result.returncode == 0
    data = json.loads(tmp_queue.read_text())
    task = next(t for t in data["tasks"] if t["slug"] == "task-a")
    assert task["qa_result"] == "APPROVED"


def test_qa_changes_requested(tmp_queue):
    """qa CHANGES_REQUESTED が正しく記録される"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
    result = run_queue(["qa", "task-a", "CHANGES_REQUESTED", "修正必要"], tmp_queue)
    assert result.returncode == 0
    data = json.loads(tmp_queue.read_text())
    task = next(t for t in data["tasks"] if t["slug"] == "task-a")
    assert task["qa_result"] == "CHANGES_REQUESTED"


def test_qa_invalid_result(tmp_queue):
    """不正な qa result でエラー終了する"""
    result = run_queue(["qa", "task-a", "INVALID", ""], tmp_queue)
    assert result.returncode != 0


def test_qa_idempotency_guard(tmp_queue):
    """qa_result が既に設定済みの場合は exit 14 で拒否する"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
    run_queue(["qa", "task-a", "APPROVED", "初回"], tmp_queue)
    result = run_queue(["qa", "task-a", "APPROVED", "重複"], tmp_queue)
    assert result.returncode == 14
    assert "already has qa_result" in result.stderr

# ---------- retry コマンドテスト ----------

def test_retry_increments_count(tmp_queue):
    """retry で retry_count が増加し READY_FOR_RIKU になる"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
    result = run_queue(["retry", "task-a"], tmp_queue)
    assert result.returncode == 0
    data = json.loads(tmp_queue.read_text())
    task = next(t for t in data["tasks"] if t["slug"] == "task-a")
    assert task["retry_count"] == 1
    assert task["status"] == "READY_FOR_RIKU"


def test_retry_blocked_on_max(tmp_path):
    """complexity: None のタスクで MAX_RETRY=1 の環境なら retry 2回目は BLOCKED になる"""
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["complexity"] = None  # complexity 未設定 → MAX_RETRY 環境変数にフォールバック
    data["tasks"][0]["retry_count"] = 1  # 既に1回
    queue_file.write_text(json.dumps(data))
    uv = str(Path.home() / ".local/bin/uv")
    env = {**os.environ, "QUEUE_FILE": str(queue_file), "MAX_RETRY": "1"}
    result = subprocess.run(
        [uv, "run", "scripts/queue.py", "retry", "task-a"],
        capture_output=True, text=True, env=env
    )
    assert result.returncode == 8
    assert "BLOCKED" in result.stdout


def test_retry_complexity_s_blocked_on_second(tmp_path):
    """complexity: S のタスクは 2回目の retry で BLOCKED になる（exit 8）"""
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["complexity"] = "S"
    data["tasks"][0]["retry_count"] = 2  # 既に2回（max=2）
    queue_file.write_text(json.dumps(data))
    result = run_queue(["retry", "task-a"], queue_file)
    assert result.returncode == 8
    assert "BLOCKED" in result.stdout
    # キューファイルで BLOCKED になっていることを確認
    saved = json.loads(queue_file.read_text())
    task = next(t for t in saved["tasks"] if t["slug"] == "task-a")
    assert task["status"] == "BLOCKED"


def test_retry_complexity_l_allows_up_to_five(tmp_path):
    """complexity: L のタスクは 5回目の retry まで READY_FOR_RIKU に戻る"""
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["complexity"] = "L"
    data["tasks"][0]["retry_count"] = 4  # 既に4回（max=5 なのでまだ通る）
    queue_file.write_text(json.dumps(data))
    result = run_queue(["retry", "task-a"], queue_file)
    assert result.returncode == 0
    saved = json.loads(queue_file.read_text())
    task = next(t for t in saved["tasks"] if t["slug"] == "task-a")
    assert task["retry_count"] == 5
    assert task["status"] == "READY_FOR_RIKU"
    # 6回目は BLOCKED になる
    result = run_queue(["retry", "task-a"], queue_file)
    assert result.returncode == 8
    assert "BLOCKED" in result.stdout


def test_retry_complexity_none_uses_env_max_retry(tmp_path):
    """complexity: None のタスクは MAX_RETRY 環境変数（デフォルト3）で動作する"""
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["complexity"] = None
    data["tasks"][0]["retry_count"] = 3  # 既に3回（MAX_RETRY=3 なので次は BLOCKED）
    queue_file.write_text(json.dumps(data))
    uv = str(Path.home() / ".local/bin/uv")
    env = {**os.environ, "QUEUE_FILE": str(queue_file), "MAX_RETRY": "3"}
    result = subprocess.run(
        [uv, "run", "scripts/queue.py", "retry", "task-a"],
        capture_output=True, text=True, env=env
    )
    assert result.returncode == 8
    assert "BLOCKED" in result.stdout

# ---------- アトミック書き込みテスト ----------

def test_atomic_write_produces_valid_json(tmp_queue):
    """start コマンド後のキューファイルが有効な JSON である"""
    run_queue(["start", "task-a"], tmp_queue)
    content = tmp_queue.read_text()
    parsed = json.loads(content)
    assert "tasks" in parsed
    assert parsed["sprint"] == "test-sprint"

# ---------- init コマンドテスト ----------

def test_init_creates_queue(tmp_path):
    """存在しないファイルパスに init すると空のキューが作られる"""
    queue_file = tmp_path / "_queue.json"
    result = run_queue(["init", "sprint-99"], queue_file)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
    data = json.loads(queue_file.read_text())
    assert data["sprint"] == "sprint-99"
    assert data["tasks"] == []


def test_init_fails_if_already_exists(tmp_queue):
    """既存のキューファイルがある場合は exit 1 でエラーになる"""
    result = run_queue(["init", "sprint-99"], tmp_queue)
    assert result.returncode == 1
    assert "already initialized" in result.stderr


# ---------- スキーマ互換テスト ----------

def test_schema_compat_with_queue_sh():
    """queue.sh が生成した .claude/_queue.json を queue.py が正しく読める"""
    result = run_queue(["show"], Path(".claude/_queue.json"))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert all("slug" in t and "status" in t for t in data)
