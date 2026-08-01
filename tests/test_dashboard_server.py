"""
tests/test_dashboard_server.py — dashboard/server/server.py 結合テスト

aiohttp のテストユーティリティ（pytest-aiohttp の aiohttp_client フィクスチャ）を使い、
POST /events → JSONL 永続化 → WS ブロードキャスト → WS 接続時の init 配信までを検証する。
実際の ~/.claude/stonefish には触れず、tmp_path を data-dir として使う。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard" / "server"))

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
