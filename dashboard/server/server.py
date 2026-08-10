#!/usr/bin/env python3
"""
server.py — STONEFISH ダッシュボードのイベント受信サーバ

## ADR-016: transcript 監視方式への転換（2026-08-02）
当初は Claude Code hooks（dashboard/hooks/emit_event.py）から POST されるイベントを主軸に
していたが、「リポジトリごとに hooks を配線するのが運用の手間」というオーナー指摘を受け、
サーバが自ら `~/.claude/projects/` 配下を横断ポーリングしてアクティブセッションを自動発見する
方式（B案縮小版）へ転換した。決定の経緯・却下した代替案・エスカレーション条件は
`docs/adr/ADR-016-dashboard-transcript-monitoring.md` を参照。
`POST /events`（hooks経由の受信）は後方互換のため当面残置するが、主経路は discovery.py に
よる自動発見であり、リポジトリ側の設定は不要。

## エンドポイント
- POST /events : （後方互換）hooksからのイベント受信。enrich → id/received_ts 付与 →
  JSONL append → WS ブロードキャスト。payload.transcript_path があればトークン集計器に、
  cwd があれば承認キュー監視対象に登録する。
- GET  /ws     : WebSocket。接続直後に直近200件のイベント・トークン集計・承認キューの
  現在状態を
  {"type":"init", "events":[...], "tokens":{...}, "personas":{...}, "queue":{...},
   "queues":{...}, "pending":[...]}
  で送り、以後 live 配信する。`personas`は部門別`tokens`の兄弟キーで、サブエージェント
  transcriptから解決できたペルソナ別のトークン集計（discovery.pyがsubagents/配下を発見
  できた場合のみ値が入る）。`queue`（単数）は直近アクティブなプロジェクト1件分で、
  既存SPA（dashboard/app/index.html）との後方互換のために維持している。`queues`（複数、
  ラベル→キューのdict）は複数プロジェクトを横断表示したい将来のSPA拡張向けに追加した。
- GET  /health : 死活監視用 {"ok": true, "clients": N, "events": N}
- GET  /       : dashboard/app/index.html が存在すればそれを返す（無ければ404）

## バックグラウンドポーリング
POLL_INTERVAL_SEC 周期で以下を行い、変化があれば全 WS クライアントへブロードキャストする。
- discovery.find_active_sessions() で `~/.claude/projects/` を横断スキャンし、アクティブな
  transcript をトークン集計器・承認キュー監視対象に自動登録する（hooks配線不要）。発見した
  セッションのうち最も新しく更新された transcript のプロジェクトを「直近アクティブな
  プロジェクト」として `queue`（単数）に反映する
- トークン集計器の poll() が True を返せば {"type":"tokens","depts":{...},"personas":{...}}
- 監視中のいずれかの `_queue.json` の mtime が変化していれば、
  {"type":"queue","queue":{...}}（直近アクティブなプロジェクト1件、既存SPA向け）と
  {"type":"queues","queues":{<label>: {...}, ...}}（既知の全プロジェクト分）の両方を配信する
  （ファイルが無い/壊れている場合は該当分が {"tasks": []}）
- pending.find_pending_approvals() のヒューリスティック（tool_use後にtool_resultが一定時間
  無いセッション）の結果が変化していれば {"type":"pending","pending":[...]}（現行SPAは未使用。
  将来のNotificationフック代替の配信チャネルとして追加）

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
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aiohttp import web, WSMsgType

sys.path.insert(0, str(Path(__file__).parent))
from discovery import ActiveSession, find_active_sessions  # noqa: E402
from enrich import enrich  # noqa: E402
from pending import DEFAULT_PENDING_THRESHOLD_SECONDS, find_pending_approvals  # noqa: E402
from tokens import TranscriptAggregator  # noqa: E402

MAX_BODY_BYTES = 1024 * 1024  # 1MB
RING_BUFFER_SIZE = 1000
INIT_EVENT_COUNT = 200
POLL_INTERVAL_SEC = 3.0

# ADR-016: transcript 監視方式のパラメータ
PROJECTS_ROOT = Path.home() / ".claude" / "projects"
DISCOVERY_ACTIVE_WINDOW_SEC = 600.0  # 10分以内に更新された transcript をアクティブとみなす
PENDING_THRESHOLD_SEC = DEFAULT_PENDING_THRESHOLD_SECONDS

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


def _queue_label(cwd: str) -> str:
    """承認キュー監視対象を識別するラベル。cwdのディレクトリ名（basename）を使う。

    既知の制約: 同名の worktree が複数あると同一ラベルに衝突する（例: 別の
    親ディレクトリ配下に同名 `dashboard/` が複数存在するケース）。個人開発のMVP規模では
    実害が小さいため許容し、問題化した場合はラベルをフルパスベースに拡張する。
    """
    name = Path(cwd).name
    return name or cwd


def _register_queue_target(queue_states: dict, cwd: str) -> None:
    """cwd から承認キュー（_queue.json）の監視対象を登録・更新する。

    新規ラベル、またはパスが変わった（同名ラベルで別プロジェクトを指すようになった）場合は
    mtime を None に戻し、次回ポーリングで必ず現在の状態を配信させる。
    """
    if not cwd:
        return
    label = _queue_label(cwd)
    path = Path(cwd) / ".claude" / "_queue.json"
    entry = queue_states.get(label)
    if entry is None or entry.get("path") != path:
        queue_states[label] = {"path": path, "mtime": None}


def _all_queues(queue_states: dict) -> dict:
    return {label: _read_queue(state.get("path")) for label, state in queue_states.items()}


def _primary_queue(app: web.Application) -> dict:
    """既存SPA（dashboard/app/index.html）が読む `queue`（単数）用に、
    「直近アクティブな1プロジェクト」分のキューだけを取り出す。

    discovery.py 経由では「最も新しく更新された transcript のプロジェクト」、
    POST /events 経由では「最新イベントの cwd」が primary_queue_label として更新される
    （旧: 単一 queue_state 方式の「最新イベントの cwd 優先」という挙動を維持するため）。
    """
    queue_states: dict = app["queue_states"]
    label = app["primary_queue_state"]["label"]
    if label is None:
        return {"tasks": []}
    state = queue_states.get(label)
    if state is None:
        return {"tasks": []}
    return _read_queue(state.get("path"))


def _pending_to_dict(p) -> dict:
    d = asdict(p)
    d["waiting_seconds"] = round(d["waiting_seconds"], 1)
    return d


def _discover_and_register(app: web.Application) -> list[ActiveSession]:
    """~/.claude/projects/ を横断スキャンし、見つかったアクティブセッションをトークン集計器・
    承認キュー監視対象へ登録する（ADR-016の中核。hooks配線がなくても機能する）。

    見つかったセッションのうち最も新しく更新された transcript のプロジェクトを
    `primary_queue_label` として記録する（`queue`単数キーの後方互換用）。
    """
    aggregator: TranscriptAggregator = app["aggregator"]
    queue_states: dict = app["queue_states"]
    try:
        sessions = find_active_sessions(PROJECTS_ROOT, DISCOVERY_ACTIVE_WINDOW_SEC)
    except Exception as e:
        _log(f"セッション自動発見中にエラー: {e}")
        return []

    for session in sessions:
        aggregator.register(session.transcript_path, session.dept, session.persona)
        _register_queue_target(queue_states, session.cwd)

    if sessions:
        latest = max(sessions, key=lambda s: s.mtime)
        app["primary_queue_state"]["label"] = _queue_label(latest.cwd)

    return sessions


@routes.post("/events")
async def handle_post_event(request: web.Request) -> web.Response:
    store: EventStore = request.app["store"]
    clients: set[web.WebSocketResponse] = request.app["ws_clients"]
    aggregator: TranscriptAggregator = request.app["aggregator"]
    queue_states: dict = request.app["queue_states"]

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

    # 後方互換: payload.transcript_path があればトークン集計器に監視対象として登録する
    # （ADR-016以降の主経路は discovery.py による自動発見だが、hooksがまだ動いている
    # 環境でも二重登録は問題なく、register() は同一パスなら冪等）
    payload = enriched.get("payload")
    transcript_path = payload.get("transcript_path") if isinstance(payload, dict) else None
    if isinstance(transcript_path, str) and transcript_path:
        aggregator.register(transcript_path, enriched.get("dept", "other"))

    # 後方互換: cwd があれば承認キュー監視対象に追加し、primary（queue単数用）も
    # 最新イベントのcwd優先で更新する（discovery.py が発見できていない場合の保険。
    # 既に discovery 側で同じラベルが登録済みなら _register_queue_target は何もしない）
    cwd = enriched.get("cwd")
    if isinstance(cwd, str) and cwd:
        _register_queue_target(queue_states, cwd)
        request.app["primary_queue_state"]["label"] = _queue_label(cwd)

    await _broadcast(clients, {"type": "event", "event": enriched})

    return web.json_response({"ok": True, "id": enriched["id"]}, status=202)


@routes.get("/ws")
async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    store: EventStore = request.app["store"]
    clients: set[web.WebSocketResponse] = request.app["ws_clients"]
    aggregator: TranscriptAggregator = request.app["aggregator"]
    queue_states: dict = request.app["queue_states"]

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    _log(f"WS接続: クライアント数={len(clients)}")

    try:
        # 接続直後に最新状態を送るため、バックグラウンドポーリングを待たず同期的に
        # 一度スキャン・pollしておく（discovery.pyでの自動発見はhooks不要のため常に可能）
        sessions = _discover_and_register(request.app)
        try:
            aggregator.poll()
        except Exception as e:
            _log(f"init用トークンpollでエラー: {e}")
        try:
            pending_list = find_pending_approvals(sessions, threshold_seconds=PENDING_THRESHOLD_SEC)
        except Exception as e:
            _log(f"init用承認待ち検知でエラー: {e}")
            pending_list = []

        init_message = json.dumps(
            {
                "type": "init",
                "events": store.recent(INIT_EVENT_COUNT),
                "tokens": aggregator.totals(),
                "personas": aggregator.persona_totals(),
                "queue": _primary_queue(request.app),
                "queues": _all_queues(queue_states),
                "pending": [_pending_to_dict(p) for p in pending_list],
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
    """POLL_INTERVAL_SEC 周期で以下を行い、変化があれば WSクライアントへ配信する（ADR-016）。

    1. discovery.py で ~/.claude/projects/ を横断スキャンし、アクティブセッションを
       トークン集計器・承認キュー監視対象へ自動登録する（hooks配線不要）
    2. トークン集計の変化を配信
    3. 監視中のいずれかの _queue.json の変化を検知したら、既知の全プロジェクト分をまとめて配信
    4. 承認待ちヒューリスティックの結果が変化したら配信
    """
    aggregator: TranscriptAggregator = app["aggregator"]
    queue_states: dict = app["queue_states"]
    clients: set[web.WebSocketResponse] = app["ws_clients"]
    pending_state: dict = app["pending_state"]

    while True:
        await asyncio.sleep(POLL_INTERVAL_SEC)

        sessions = _discover_and_register(app)

        try:
            if aggregator.poll():
                await _broadcast(clients, {
                    "type": "tokens",
                    "depts": aggregator.totals(),
                    "personas": aggregator.persona_totals(),
                })
        except Exception as e:
            # ポーリングの1周期での失敗でループ自体は止めない
            _log(f"トークン集計ポーリング中にエラー: {e}")

        any_queue_changed = False
        for state in queue_states.values():
            queue_path = state.get("path")
            try:
                mtime = queue_path.stat().st_mtime if queue_path is not None else None
            except OSError:
                mtime = None
            if mtime != state.get("mtime"):
                state["mtime"] = mtime
                any_queue_changed = True
        if any_queue_changed:
            # 既存SPA（dashboard/app/index.html）は "queue"（単数）しか処理しないため、
            # 後方互換のため両方配信する（"queues" は将来の複数プロジェクト対応SPA向け）
            await _broadcast(clients, {"type": "queue", "queue": _primary_queue(app)})
            await _broadcast(clients, {"type": "queues", "queues": _all_queues(queue_states)})

        try:
            pending_list = find_pending_approvals(sessions, threshold_seconds=PENDING_THRESHOLD_SEC)
        except Exception as e:
            _log(f"承認待ち検知中にエラー: {e}")
            pending_list = []
        current_ids = {p.tool_use_id for p in pending_list}
        if current_ids != pending_state.get("ids"):
            pending_state["ids"] = current_ids
            await _broadcast(clients, {"type": "pending", "pending": [_pending_to_dict(p) for p in pending_list]})


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
    app["queue_states"] = {}
    app["primary_queue_state"] = {"label": None}
    app["pending_state"] = {"ids": set()}
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
