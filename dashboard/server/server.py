#!/usr/bin/env python3
"""
server.py — STONEFISH ダッシュボードのイベント受信サーバ

Claude Code hooks（dashboard/hooks/emit_event.py）から POST されるイベントを受け取り、
JSONL へ永続化しつつ、接続中の WebSocket クライアントへリアルタイム配信する。
disler/claude-code-hooks-multi-agent-observability の構成（hooks → HTTP → サーバ → WS → SPA）
を踏襲した M1（イベントパイプライン）の実装に、M2（トークン会計・承認キュー配信・SPA配信）
を追加したもの。

## エンドポイント
- POST /events : イベント受信。enrich → id/received_ts 付与 → JSONL append → WS ブロードキャスト。
  payload.transcript_path があればトークン集計器（tokens.TranscriptAggregator）に監視登録し、
  cwd があれば承認キュー（<cwd>/.claude/_queue.json）監視対象を更新する（最新イベントの cwd優先）。
- GET  /ws     : WebSocket。接続直後に直近200件のイベント・トークン集計・承認キュー状態を
  {"type":"init", "events":[...], "tokens":{...}, "queue":{...}} で送り、以後 live 配信する。
- GET  /health : 死活監視用 {"ok": true, "clients": N, "events": N}
- GET  /       : dashboard/app/index.html が存在すればそれを返す（SPA は並行実装中のため
  存在チェックのみ。無ければ404）

## バックグラウンドポーリング
POLL_INTERVAL_SEC 周期で以下を確認し、変化があれば全 WS クライアントへブロードキャストする。
- トークン集計器の poll() が True を返せば {"type":"tokens","depts":{...}}
- 承認キューファイルの mtime が変化していれば {"type":"queue","queue":{...}}
  （ファイルが無い/壊れている場合は {"tasks": []}）

## 永続化
<data-dir>/events.jsonl に1行1イベントで append する（都度 flush）。
サーバ起動時にはこのファイルの末尾1000行を読み込み、直近イベントのリングバッファを復元する。
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aiohttp import web, WSMsgType

sys.path.insert(0, str(Path(__file__).parent))
from enrich import enrich  # noqa: E402
from tokens import TranscriptAggregator  # noqa: E402

MAX_BODY_BYTES = 1024 * 1024  # 1MB
RING_BUFFER_SIZE = 1000
INIT_EVENT_COUNT = 200
POLL_INTERVAL_SEC = 3.0

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


async def _broadcast(clients: set[web.WebSocketResponse], message: dict) -> None:
    """message を全 WS クライアントへ配信する。送信失敗したクライアントは切断済みとして除去する。"""
    text = json.dumps(message, ensure_ascii=False)
    dead: list[web.WebSocketResponse] = []
    # await 中に新規 WS 接続が clients を変更しても壊れないようスナップショットを走査する
    for ws in list(clients):
        if ws.closed:
            dead.append(ws)
            continue
        try:
            await ws.send_str(text)
        except Exception:
            # 1クライアントへの送信失敗（切断途中など）で他クライアントへの配信を止めない
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


def _read_queue(queue_path: Optional[Path]) -> dict:
    """承認キュー（_queue.json）を読み込み、WS配信用の簡約形式へ変換する。

    監視対象未設定・ファイル不在・JSON不正のいずれの場合も {"tasks": []} を返す
    （呼び出し側で例外分岐を持たせないための安全側フォールバック）。
    """
    if queue_path is None:
        return {"tasks": []}
    try:
        raw = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tasks": []}
    if not isinstance(raw, dict):
        return {"tasks": []}

    tasks_raw = raw.get("tasks")
    tasks: list[dict] = []
    if isinstance(tasks_raw, list):
        for task in tasks_raw:
            if not isinstance(task, dict):
                continue
            tasks.append({
                "slug": task.get("slug"),
                "title": task.get("title"),
                "status": task.get("status"),
                "assigned_to": task.get("assigned_to"),
            })

    try:
        updated_ts = queue_path.stat().st_mtime
    except OSError:
        updated_ts = None

    return {"sprint": raw.get("sprint"), "tasks": tasks, "updated_ts": updated_ts}


@routes.post("/events")
async def handle_post_event(request: web.Request) -> web.Response:
    store: EventStore = request.app["store"]
    clients: set[web.WebSocketResponse] = request.app["ws_clients"]
    aggregator: TranscriptAggregator = request.app["aggregator"]
    queue_state: dict = request.app["queue_state"]

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

    # payload.transcript_path があればトークン集計器に監視対象として登録する
    payload = enriched.get("payload")
    transcript_path = payload.get("transcript_path") if isinstance(payload, dict) else None
    if isinstance(transcript_path, str) and transcript_path:
        aggregator.register(transcript_path, enriched.get("dept", "other"))

    # cwd があれば承認キュー監視対象を更新する（最新イベントの cwd を優先）
    cwd = enriched.get("cwd")
    if isinstance(cwd, str) and cwd:
        new_queue_path = Path(cwd) / ".claude" / "_queue.json"
        if queue_state.get("path") != new_queue_path:
            queue_state["path"] = new_queue_path
            # 監視対象切替時は次回ポーリングで必ず変化ありと判定させ、新対象の状態を送らせる
            queue_state["mtime"] = None

    await _broadcast(clients, {"type": "event", "event": enriched})

    return web.json_response({"ok": True, "id": enriched["id"]}, status=202)


@routes.get("/ws")
async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    store: EventStore = request.app["store"]
    clients: set[web.WebSocketResponse] = request.app["ws_clients"]
    aggregator: TranscriptAggregator = request.app["aggregator"]
    queue_state: dict = request.app["queue_state"]

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    _log(f"WS接続: クライアント数={len(clients)}")

    try:
        init_message = json.dumps(
            {
                "type": "init",
                "events": store.recent(INIT_EVENT_COUNT),
                "tokens": aggregator.totals(),
                "queue": _read_queue(queue_state.get("path")),
            },
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


@routes.get("/")
async def handle_index(request: web.Request) -> web.Response:
    """dashboard/app/index.html があれば text/html で返す。

    SPA（dashboard/app/）は並行実装中のため、ここでは存在チェックのみ行う。
    無ければ 404（このハンドラは SPA 完成を前提としない）。
    """
    index_path = Path(__file__).resolve().parent.parent / "app" / "index.html"
    if not index_path.is_file():
        raise web.HTTPNotFound()
    try:
        html = index_path.read_text(encoding="utf-8")
    except OSError as e:
        _log(f"index.html 読み込み失敗: {e}")
        raise web.HTTPNotFound()
    return web.Response(text=html, content_type="text/html")


async def _background_poll_task(app: web.Application) -> None:
    """POLL_INTERVAL_SEC 周期でトークン集計・承認キューの変化を検知し、WSクライアントへ配信する。"""
    aggregator: TranscriptAggregator = app["aggregator"]
    queue_state: dict = app["queue_state"]
    clients: set[web.WebSocketResponse] = app["ws_clients"]

    while True:
        await asyncio.sleep(POLL_INTERVAL_SEC)

        try:
            if aggregator.poll():
                await _broadcast(clients, {"type": "tokens", "depts": aggregator.totals()})
        except Exception as e:
            # ポーリングの1周期での失敗でループ自体は止めない
            _log(f"トークン集計ポーリング中にエラー: {e}")

        queue_path = queue_state.get("path")
        if queue_path is None:
            continue
        try:
            mtime = queue_path.stat().st_mtime
        except OSError:
            mtime = None
        if mtime != queue_state.get("mtime"):
            queue_state["mtime"] = mtime
            await _broadcast(clients, {"type": "queue", "queue": _read_queue(queue_path)})


async def _start_background_tasks(app: web.Application) -> None:
    app["poll_task"] = asyncio.create_task(_background_poll_task(app))


async def _cleanup_background_tasks(app: web.Application) -> None:
    task: Optional[asyncio.Task] = app.get("poll_task")
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def build_app(data_dir: Path) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY_BYTES)
    app["store"] = EventStore(data_dir)
    app["ws_clients"] = set()
    app["aggregator"] = TranscriptAggregator()
    app["queue_state"] = {"path": None, "mtime": None}
    app.add_routes(routes)
    app.on_startup.append(_start_background_tasks)
    app.on_cleanup.append(_cleanup_background_tasks)
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
