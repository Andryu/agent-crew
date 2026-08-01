# STONEFISH ダッシュボード — イベント受信サーバ（M1）

Claude Code の hooks から送られてくるイベントを受け取り、JSONL に永続化しつつ
WebSocket 経由でダッシュボード SPA（M2 で実装予定）へ配信するサーバ。

## 起動方法

```bash
uv sync --group dashboard
uv run --group dashboard python dashboard/server/server.py
```

オプション:

| フラグ | 既定値 | 説明 |
|---|---|---|
| `--port` | `$STONEFISH_PORT` または `8787` | 待受ポート |
| `--data-dir` | `$STONEFISH_DATA_DIR` または `~/.claude/stonefish` | `events.jsonl` の保存先 |

## エンドポイント

- `POST /events` — hooks からのイベント受信。`dashboard/hooks/emit_event.py` が送る封筒
  形式の JSON を受け取り、部門（`dept`）・ペルソナ（`persona`）を付与してから
  `<data-dir>/events.jsonl` に1行 append し、接続中の WebSocket クライアントへ配信する。
  成功時は `202`。JSON として不正・1MB 超は `400`。
- `GET /ws` — WebSocket。接続直後に直近200件を `{"type":"init","events":[...]}` で送り、
  以後は新規イベントを `{"type":"event","event":{...}}` で live 配信する。
- `GET /health` — `{"ok":true,"clients":N,"events":N}`。死活監視用。

## 手動送信の例

```bash
curl -X POST http://127.0.0.1:8787/events \
  -H 'Content-Type: application/json' \
  -d '{
    "schema": 1,
    "ts": "2026-08-02T00:00:00.000000Z",
    "hook_event": "SubagentStart",
    "session_id": "test-session",
    "cwd": "/Users/you/Workspace/agent-crew",
    "payload": {"agent_type": "engineer-go"}
  }'

curl http://127.0.0.1:8787/health
```

`emit_event.py` 経由での送信例（実際に hooks から呼ばれるのと同じ形）:

```bash
echo '{"session_id":"test","cwd":"'"$PWD"'","hook_event_name":"Stop"}' \
  | dashboard/hooks/emit_event.py Stop
```

## WebSocket の確認

```bash
uv run --group dashboard python - <<'PY'
import asyncio
from aiohttp import ClientSession

async def main():
    async with ClientSession() as session:
        async with session.ws_connect("http://127.0.0.1:8787/ws") as ws:
            print(await ws.receive_json())  # {"type": "init", "events": [...]}
            print(await ws.receive_json())  # 新規イベントが来ると {"type": "event", ...}

asyncio.run(main())
PY
```

## settings-fragment.json について

`dashboard/hooks/settings-fragment.json` は、`.claude/settings.json` の `hooks` キー配下に
マージするための断片（参照実装）。SessionStart / PreToolUse / PostToolUse / SubagentStart /
SubagentStop / Stop / Notification の7イベントで `emit_event.py <イベント名>` を command 型
hook として呼び出す設定が入っている。matcher はすべて全マッチ（`"*"`）、timeout は5秒。

M3（導入の仕組み）で `install.sh --only=dashboard-hooks` が、既存の `.claude/settings.json`
の hooks を壊さないよう jq でこの断片をマージする想定（Sprint-25 の enforce-retro-stop.sh の
手法を踏襲）。現時点ではこのファイル単体を手で `.claude/settings.json` にマージしても動作する。

## テスト

```bash
uv run --group dashboard pytest tests/
```
