#!/usr/bin/env python3
"""
emit_event.py — Claude Code hooks から STONEFISH ダッシュボードへイベントを送信する

hooks（SessionStart/PreToolUse/PostToolUse/SubagentStart/SubagentStop/Stop/Notification）
から呼ばれ、stdin に渡される hook ペイロード（JSON）を封筒に包んでダッシュボードの
受信サーバ（dashboard/server/server.py）へ POST する。

## 設計方針（最重要）
Claude Code のセッション進行を絶対にブロックしない。ダッシュボードサーバが起動して
いない・ネットワークが不調・ペイロードが壊れている等、どんな理由であっても本スクリプトは
無音（stdout に何も出さず）で exit 0 する。標準出力に何か書くと hook の戻り値として
Claude Code に解釈されるため、成功・失敗を問わず stdout には一切書き込まない。

使い方: <this> <hook_event_name>
  argv[1] が渡されればそれを hook_event として使う。渡されなければ payload 内の
  hook_event_name を使う。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

MAX_STDIN_BYTES = 1024 * 1024  # 1MB。超過分は打ち切る（読み切れないほど巨大な入力を無視するため）
POST_TIMEOUT_SECONDS = 0.8


def _read_stdin_payload() -> dict:
    raw = sys.stdin.buffer.read(MAX_STDIN_BYTES)
    return json.loads(raw.decode("utf-8"))


def _build_envelope(hook_event_arg: str | None, payload: dict) -> dict:
    hook_event = hook_event_arg or payload.get("hook_event_name")
    cwd = payload.get("cwd") or os.getcwd()
    return {
        "schema": 1,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "hook_event": hook_event,
        "session_id": payload.get("session_id"),
        "cwd": cwd,
        "payload": payload,
    }


def _post(envelope: dict) -> None:
    port = os.environ.get("STONEFISH_PORT", "8787")
    url = f"http://127.0.0.1:{port}/events"
    body = json.dumps(envelope).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=POST_TIMEOUT_SECONDS).close()


def main() -> int:
    hook_event_arg = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        payload = _read_stdin_payload()
        envelope = _build_envelope(hook_event_arg, payload)
        _post(envelope)
    except Exception:
        # サーバ不在・タイムアウト・不正JSON等、いかなる失敗でも
        # Claude Code のセッションをブロックしないよう無音で成功扱いにする。
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
