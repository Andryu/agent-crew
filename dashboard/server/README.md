# STONEFISH ダッシュボード — イベント受信サーバ（M1 + M2サーバ拡張 + ADR-016）

`~/.claude/projects/` 配下を横断ポーリングしてアクティブな Claude Code セッションを
自動発見し、部門別トークン集計・承認キュー・承認待ち状態を WebSocket 経由でダッシュボード
SPA へ配信するサーバ（`discovery.py`）。**リポジトリごとの hooks 設定は不要**。

> **ADR-016（2026-08-02）**: 当初は各リポジトリに hooks を配線する方式（disler/
> claude-code-hooks-multi-agent-observability 構成）だったが、「リポジトリごとの設定が
> 運用の手間」というオーナー指摘を受け、transcript 監視方式（B案縮小版）へ転換した。
> `POST /events`（hooks経由）は後方互換のため残置しているが、主経路は
> `discovery.find_active_sessions()` による自動発見。決定の経緯は
> `docs/adr/ADR-016-dashboard-transcript-monitoring.md` を参照。

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

- `GET /ws` — WebSocket。接続直後に直近200件のイベント・現在のトークン集計・現在の全プロジェクト
  分の承認キュー・承認待ちヒューリスティックの結果をまとめた `init` メッセージを送り、以後は
  live 配信する（メッセージ型は下記参照）。接続時に同期的に `~/.claude/projects/` を再スキャン
  するため、hooksが一度も動いていなくても最新状態が返る。
- `GET /health` — `{"ok":true,"clients":N,"events":N}`。死活監視用。
- `GET /` — `dashboard/app/index.html` が存在すれば `text/html` で返す（SPA は別トラックで
  実装中のため存在チェックのみ。無ければ `404`）。
- `POST /events` — （後方互換）hooks からのイベント受信。`dashboard/hooks/emit_event.py` が
  送る封筒形式の JSON を受け取り、部門（`dept`）・ペルソナ（`persona`）を付与してから
  `<data-dir>/events.jsonl` に1行 append し、接続中の WebSocket クライアントへ配信する。
  成功時は `202`。JSON として不正・1MB 超は `400`。ADR-016以降の主経路ではないため、
  hooksが配線されていない環境でも動作に影響しない。

## バックグラウンドポーリング（ADR-016: transcript監視方式）

`POLL_INTERVAL_SEC`（既定3秒）周期で以下を行い、変化があれば全 WebSocket クライアントへ
配信する。

1. `discovery.find_active_sessions()` で `~/.claude/projects/` 配下を横断スキャンし、
   `DISCOVERY_ACTIVE_WINDOW_SEC`（既定600秒）以内に更新された transcript を「アクティブ
   セッション」としてトークン集計器・承認キュー監視対象へ自動登録する（**リポジトリごとの
   設定は不要**）
2. 登録済み transcript の増分読み（`TranscriptAggregator.poll()`）で新規/更新 usage があれば
   `tokens` メッセージ
3. 監視中のいずれかの `_queue.json` の mtime が変化していれば、既知の全プロジェクト分を
   まとめて `queues` メッセージ（ファイルが無い・JSON が壊れている場合は該当ラベルが
   `{"tasks": []}`）
4. `pending.find_pending_approvals()` のヒューリスティック（直近の `tool_use` に対応する
   `tool_result` が `PENDING_THRESHOLD_SEC` 秒（既定20秒）以上未記録）の結果が変化していれば
   `pending` メッセージ。hooksのNotificationイベントを使わない代替手段（ADR-016）であり、
   実行時間の長いツール呼び出しを誤検知する可能性がある既知の限界がある

## WebSocket メッセージ型

| type | 送信タイミング | 形状 |
|---|---|---|
| `init` | 接続直後に1回 | `{"type":"init","events":[...],"tokens":{...},"queues":{...},"pending":[...]}` |
| `event` | `POST /events` を受けるたび（後方互換パス） | `{"type":"event","event":{...}}` |
| `tokens` | ポーリングでトークン集計に変化があったとき | `{"type":"tokens","depts":{"product":{"input":N,"output":N,"cache":N,"total":N}, ...}}` |
| `queues` | ポーリングでいずれかの `_queue.json` の mtime が変化したとき | `{"type":"queues","queues":{"<label>":{"sprint":"...","tasks":[{"slug":...,"title":...,"status":...,"assigned_to":...}],"updated_ts":<epoch秒>}, ...}}`（`<label>` はプロジェクトディレクトリのbasename。ファイル不在/不正時は該当ラベルが `{"tasks":[]}`） |
| `pending` | ポーリングで承認待ちヒューリスティックの結果（未解決 `tool_use_id` の集合）が変化したとき | `{"type":"pending","pending":[{"cwd":"...","dept":"...","session_id":"...","tool_name":"...","tool_use_id":"...","waiting_seconds":N}, ...]}` |

`tokens` の集計規則は `scripts/token-report.py` と同一（同一 `message.id` は最新timestampの
行のみ採用し、ストリーミング途中経過の合算による水増しを防ぐ）。詳細は `tokens.py` の
docstring を参照。

## 動作確認（hooks不要）

サーバを起動して `~/.claude/projects/` に何らかのアクティブな Claude Code セッションが
あれば、hooksの設定やイベント送信を何もせずに WebSocket 接続するだけで反映を確認できる。

```bash
uv run --group dashboard python - <<'PY'
import asyncio
from aiohttp import ClientSession

async def main():
    async with ClientSession() as session:
        async with session.ws_connect("http://127.0.0.1:8787/ws") as ws:
            print(await ws.receive_json())  # {"type": "init", "events": [...], "tokens": {...}, "queues": {...}, "pending": [...]}

asyncio.run(main())
PY
```

## 手動送信の例（後方互換パスの動作確認用）

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

`emit_event.py` 経由での送信例（実際に hooks から呼ばれるのと同じ形。ADR-016以降は必須では
ないが、後方互換パスとして残置している）:

```bash
echo '{"session_id":"test","cwd":"'"$PWD"'","hook_event_name":"Stop"}' \
  | dashboard/hooks/emit_event.py Stop
```

## settings-fragment.json について（レガシー・ADR-016以降は原則不要）

`dashboard/hooks/settings-fragment.json` は、`.claude/settings.json` の `hooks` キー配下に
マージするための断片（参照実装）。SessionStart / PreToolUse / PostToolUse / SubagentStart /
SubagentStop / Stop / Notification の7イベントで `emit_event.py <イベント名>` を command 型
hook として呼び出す設定が入っている。matcher はすべて全マッチ（`"*"`）、timeout は5秒。

ADR-016でtranscript監視方式（hooks配線不要）へ転換したため、このファイルのリポジトリごとの
配線は原則不要になった。互換性のため当面残置している（Phase 2で段階的に縮小・撤去予定。
`docs/adr/ADR-016-dashboard-transcript-monitoring.md` 参照）。

## テスト

```bash
uv run --group dashboard pytest tests/
```
