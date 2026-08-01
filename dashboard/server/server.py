#!/usr/bin/env python3
"""
server.py — STONEFISH ダッシュボードのイベント受信サーバ

Claude Code hooks（dashboard/hooks/emit_event.py）から POST されるイベントを受け取り、
JSONL へ永続化しつつ、接続中の WebSocket クライアントへリアルタイム配信する。
disler/claude-code-hooks-multi-agent-observability の構成（hooks → HTTP → サーバ → WS → SPA）
を踏襲した M1（イベントパイプライン）の実装。

## エンドポイント
- POST /events : イベント受信。enrich → id/received_ts 付与 → JSONL append → WS ブロードキャスト
- GET  /ws     : WebSocket。接続直後に直近200件を {"type":"init", ...} で送り、以後 live 配信
- GET  /health : 死活監視用 {"ok": true, "clients": N, "events": N}

## 永続化
<data-dir>/events.jsonl に1行1イベントで append する（都度 flush）。
サーバ起動時にはこのファイルの末尾1000行を読み込み、直近イベントのリングバッファを復元する。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web, WSMsgType

sys.path.insert(0, str(Path(__file__).parent))
from enrich import enrich  # noqa: E402

MAX_BODY_BYTES = 1024 * 1024  # 1MB
RING_BUFFER_SIZE = 1000
INIT_EVENT_COUNT = 200

DEFAULT_PORT = 8787
DEFAULT_DATA_DIR = Path.home() / ".claude" / "stonefish"


def _log(message: str) -> None:
    """最小限のログを stderr に出す。"""
    print(f"[stonefish] {message}", file=sys.stderr)


class EventStore:
    """イベントの永続化（JSONL）とリングバッファを管理する。"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.data_dir / "events.jsonl"
        self.ring: deque[dict] = deque(maxlen=RING_BUFFER_SIZE)
        self._seq = 0
        self._restore()

    def _restore(self) -> None:
        """events.jsonl の末尾 RING_BUFFER_SIZE 行からリングバッファを復元する。"""
        if not self.jsonl_path.exists():
            return
        try:
            lines = self.jsonl_path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            _log(f"events.jsonl の読み込みに失敗: {e}")
            return

        restored = 0
        for line in lines[-RING_BUFFER_SIZE:]:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.ring.append(event)
            restored += 1

        # 再起動後も id の連番が既存イベントと衝突しないよう、末尾行から seq を引き継ぐ
        if self.ring:
            last_id = self.ring[-1].get("id", "")
            if isinstance(last_id, str) and "-" in last_id:
                tail = last_id.rsplit("-", 1)[-1]
                if tail.isdigit():
                    self._seq = int(tail)

        _log(f"起動時復元: events.jsonl から {restored} 件をリングバッファへ復元")

    def next_id(self, received_ts_ms: int) -> str:
        self._seq += 1
        return f"{received_ts_ms}-{self._seq}"

    def append(self, event: dict) -> None:
        """イベントを JSONL に append（都度 flush）し、リングバッファにも積む。"""
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False))
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.ring.append(event)

    def recent(self, n: int) -> list[dict]:
        items = list(self.ring)
        return items[-n:]

    def count(self) -> int:
        return len(self.ring)


routes = web.RouteTableDef()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@routes.post("/events")
async def handle_post_event(request: web.Request) -> web.Response:
    store: EventStore = request.app["store"]
    clients: set[web.WebSocketResponse] = request.app["ws_clients"]

    body = await request.read()
    if len(body) > MAX_BODY_BYTES:
        return web.json_response({"error": "payload too large"}, status=400)

    try:
        envelope = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "invalid json"}, status=400)

    if not isinstance(envelope, dict):
        return web.json_response({"error": "invalid json"}, status=400)

    enriched = enrich(envelope)
    received_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    enriched["id"] = store.next_id(received_ts_ms)
    enriched["received_ts"] = _now_iso()

    store.append(enriched)

    message = json.dumps({"type": "event", "event": enriched}, ensure_ascii=False)
    dead: list[web.WebSocketResponse] = []
    # await 中に新規 WS 接続が clients を変更しても壊れないようスナップショットを走査する
    for ws in list(clients):
        if ws.closed:
            dead.append(ws)
            continue
        try:
            await ws.send_str(message)
        except Exception:
            # 1クライアントへの送信失敗（切断途中など）で他クライアントへの配信を止めない
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)

    return web.json_response({"ok": True, "id": enriched["id"]}, status=202)


@routes.get("/ws")
async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    store: EventStore = request.app["store"]
    clients: set[web.WebSocketResponse] = request.app["ws_clients"]

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    _log(f"WS接続: クライアント数={len(clients)}")

    try:
        init_message = json.dumps(
            {"type": "init", "events": store.recent(INIT_EVENT_COUNT)},
            ensure_ascii=False,
        )
        await ws.send_str(init_message)

        async for msg in ws:
            # クライアントからのメッセージは想定していない（受信専用チャネル）。
            # クローズ要求のみハンドリングする。
            if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSING):
                break
    finally:
        clients.discard(ws)
        _log(f"WS切断: クライアント数={len(clients)}")

    return ws


@routes.get("/health")
async def handle_health(request: web.Request) -> web.Response:
    store: EventStore = request.app["store"]
    clients: set[web.WebSocketResponse] = request.app["ws_clients"]
    return web.json_response({
        "ok": True,
        "clients": len(clients),
        "events": store.count(),
    })


def build_app(data_dir: Path) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY_BYTES)
    app["store"] = EventStore(data_dir)
    app["ws_clients"] = set()
    app.add_routes(routes)
    return app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="STONEFISH ダッシュボード イベント受信サーバ")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("STONEFISH_PORT", DEFAULT_PORT)),
        help=f"待受ポート（既定: env STONEFISH_PORT または {DEFAULT_PORT}）",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=os.environ.get("STONEFISH_DATA_DIR", str(DEFAULT_DATA_DIR)),
        help=f"永続化先ディレクトリ（既定: env STONEFISH_DATA_DIR または {DEFAULT_DATA_DIR}）",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir).expanduser()
    app = build_app(data_dir)
    _log(f"起動: port={args.port} data_dir={data_dir}")
    web.run_app(app, host="127.0.0.1", port=args.port, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
