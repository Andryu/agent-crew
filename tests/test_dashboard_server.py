"""
tests/test_dashboard_server.py — dashboard/server/server.py 結合テスト

aiohttp のテストユーティリティ（pytest-aiohttp の aiohttp_client フィクスチャ）を使い、
POST /events → JSONL 永続化 → WS ブロードキャスト → WS 接続時の init 配信までを検証する。
実際の ~/.claude/stonefish には触れず、tmp_path を data-dir として使う。

M2 で追加したトークン集計・承認キューのブロードキャストテストは、バックグラウンドポーリング
の周期（server.POLL_INTERVAL_SEC）を monkeypatch で短縮してから app を構築することで、
実時間3秒を待たずに検証する。
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard" / "server"))

import server as server_module  # noqa: E402
from server import build_app  # noqa: E402

SAMPLE_ENVELOPE = {
    "schema": 1,
    "ts": "2026-08-02T00:00:00.000000Z",
    "hook_event": "SubagentStart",
    "session_id": "sess-1",
    "cwd": "/Users/andryu/Workspace/agent-crew",
    "payload": {"agent_type": "engineer-go"},
}


@pytest.fixture
def app(tmp_path):
    return build_app(tmp_path)


async def test_post_event_returns_202_and_writes_jsonl(aiohttp_client, tmp_path, app):
    client = await aiohttp_client(app)
    resp = await client.post("/events", data=json.dumps(SAMPLE_ENVELOPE))
    assert resp.status == 202
    body = await resp.json()
    assert body["ok"] is True
    assert "id" in body

    jsonl_path = tmp_path / "events.jsonl"
    assert jsonl_path.exists()
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["dept"] == "product"
    assert saved["persona"] == "riku"
    assert saved["hook_event"] == "SubagentStart"
    assert "id" in saved
    assert "received_ts" in saved


async def test_post_event_invalid_json_returns_400(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post("/events", data="{not valid json")
    assert resp.status == 400


async def test_post_event_non_dict_json_returns_400(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post("/events", data=json.dumps([1, 2, 3]))
    assert resp.status == 400


async def test_post_event_too_large_returns_400_or_413(aiohttp_client, app):
    client = await aiohttp_client(app)
    huge_payload = json.dumps({"payload": {"x": "a" * (2 * 1024 * 1024)}})
    resp = await client.post("/events", data=huge_payload)
    # aiohttp の client_max_size 超過は 413、アプリ側チェックなら 400。どちらも許容。
    assert resp.status in (400, 413)


async def test_health_endpoint(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.get("/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["ok"] is True
    assert body["clients"] == 0
    assert body["events"] == 0


async def test_ws_receives_init_with_existing_events(aiohttp_client, app):
    client = await aiohttp_client(app)
    # 先にイベントを1件投入しておく
    await client.post("/events", data=json.dumps(SAMPLE_ENVELOPE))

    ws = await client.ws_connect("/ws")
    init_msg = await ws.receive_json()
    assert init_msg["type"] == "init"
    assert len(init_msg["events"]) == 1
    assert init_msg["events"][0]["dept"] == "product"
    await ws.close()


async def test_ws_receives_live_broadcast(aiohttp_client, app):
    client = await aiohttp_client(app)
    ws = await client.ws_connect("/ws")

    # 接続直後の init（既存イベントなしなので空リスト）を読み飛ばす
    init_msg = await ws.receive_json()
    assert init_msg["type"] == "init"
    assert init_msg["events"] == []

    await client.post("/events", data=json.dumps(SAMPLE_ENVELOPE))

    live_msg = await ws.receive_json()
    assert live_msg["type"] == "event"
    assert live_msg["event"]["dept"] == "product"
    assert live_msg["event"]["persona"] == "riku"
    await ws.close()


async def test_health_reflects_connected_clients(aiohttp_client, app):
    client = await aiohttp_client(app)
    ws = await client.ws_connect("/ws")
    await ws.receive_json()  # init を読み飛ばす

    resp = await client.get("/health")
    body = await resp.json()
    assert body["clients"] == 1

    await ws.close()


def test_restore_ring_buffer_from_existing_jsonl(tmp_path):
    """サーバ起動時に events.jsonl の末尾からリングバッファを復元する"""
    jsonl_path = tmp_path / "events.jsonl"
    lines = [
        json.dumps({"id": f"1000-{i}", "hook_event": "PreToolUse", "n": i})
        for i in range(3)
    ]
    jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    restored_app = build_app(tmp_path)
    store = restored_app["store"]
    assert store.count() == 3
    assert store.recent(10)[0]["n"] == 0
    assert store.recent(10)[-1]["n"] == 2


# ---------- M2: トークン集計・承認キュー ----------


async def test_ws_init_includes_tokens_and_queue_defaults(aiohttp_client, app):
    """未登録状態（transcript未登録・queue監視対象未設定）での init は空のtokens/queueを返す。"""
    client = await aiohttp_client(app)
    ws = await client.ws_connect("/ws")
    init_msg = await ws.receive_json()
    assert init_msg["type"] == "init"
    assert init_msg["tokens"] == {}
    assert init_msg["queue"] == {"tasks": []}
    await ws.close()


async def test_get_root_matches_current_app_html_state(aiohttp_client, app):
    """dashboard/app/index.html は別トラックで並行実装中のため、このテストはその有無を前提にしない。
    存在するなら中身をそのままtext/htmlで返し、存在しないなら404を返すことだけを検証する。"""
    index_path = Path(__file__).parent.parent / "dashboard" / "app" / "index.html"
    client = await aiohttp_client(app)
    resp = await client.get("/")
    if index_path.is_file():
        assert resp.status == 200
        assert "text/html" in resp.headers["Content-Type"]
        assert await resp.text() == index_path.read_text(encoding="utf-8")
    else:
        assert resp.status == 404


async def test_background_poll_broadcasts_tokens_and_queue(aiohttp_client, tmp_path, monkeypatch):
    """transcript登録・_queue.json作成後、短縮したポーリング周期で
    {"type":"tokens",...} と {"type":"queue",...} が両方配信されること。"""
    monkeypatch.setattr(server_module, "POLL_INTERVAL_SEC", 0.05)

    data_dir = tmp_path / "data"
    project_dir = tmp_path / "myproj"
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True)

    transcript = project_dir / "session.jsonl"
    transcript.write_text(
        json.dumps({
            "message": {
                "role": "assistant",
                "id": "msg_1",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
            "timestamp": "2026-08-02T00:00:00.000Z",
        }) + "\n",
        encoding="utf-8",
    )

    queue_path = claude_dir / "_queue.json"
    queue_path.write_text(
        json.dumps({
            "sprint": "sprint-x",
            "tasks": [
                {"slug": "t1", "title": "Task 1", "status": "TODO", "assigned_to": "Riku"},
            ],
        }),
        encoding="utf-8",
    )

    test_app = server_module.build_app(data_dir)
    client = await aiohttp_client(test_app)
    ws = await client.ws_connect("/ws")
    init_msg = await ws.receive_json()
    assert init_msg["type"] == "init"

    envelope = {
        "schema": 1,
        "ts": "2026-08-02T00:00:00.000000Z",
        "hook_event": "PostToolUse",
        "session_id": "sess-tok",
        "cwd": str(project_dir),
        "payload": {"transcript_path": str(transcript)},
    }
    resp = await client.post("/events", data=json.dumps(envelope))
    assert resp.status == 202

    event_msg = await asyncio.wait_for(ws.receive_json(), timeout=2)
    assert event_msg["type"] == "event"

    seen = {}
    for _ in range(2):
        msg = await asyncio.wait_for(ws.receive_json(), timeout=2)
        seen[msg["type"]] = msg

    assert "tokens" in seen
    assert seen["tokens"]["depts"]["other"]["input"] == 10
    assert seen["tokens"]["depts"]["other"]["output"] == 5

    assert "queue" in seen
    assert seen["queue"]["queue"]["sprint"] == "sprint-x"
    assert seen["queue"]["queue"]["tasks"] == [
        {"slug": "t1", "title": "Task 1", "status": "TODO", "assigned_to": "Riku"},
    ]

    await ws.close()


async def test_queue_broadcast_falls_back_to_empty_tasks_when_file_becomes_invalid(
    aiohttp_client, tmp_path, monkeypatch
):
    """_queue.json が壊れたJSONになった場合でも例外にせず {"tasks": []} を配信すること。"""
    monkeypatch.setattr(server_module, "POLL_INTERVAL_SEC", 0.05)

    data_dir = tmp_path / "data"
    project_dir = tmp_path / "myproj2"
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True)
    queue_path = claude_dir / "_queue.json"
    queue_path.write_text("{not valid json", encoding="utf-8")

    test_app = server_module.build_app(data_dir)
    client = await aiohttp_client(test_app)
    ws = await client.ws_connect("/ws")
    await ws.receive_json()  # init

    envelope = {
        "schema": 1,
        "ts": "2026-08-02T00:00:00.000000Z",
        "hook_event": "Notification",
        "session_id": "sess-q",
        "cwd": str(project_dir),
        "payload": {},
    }
    resp = await client.post("/events", data=json.dumps(envelope))
    assert resp.status == 202

    await ws.receive_json()  # event ブロードキャスト

    queue_msg = await asyncio.wait_for(ws.receive_json(), timeout=2)
    assert queue_msg["type"] == "queue"
    assert queue_msg["queue"] == {"tasks": []}

    await ws.close()
