"""
tests/test_dashboard_emit_event.py — dashboard/hooks/emit_event.py ユニットテスト

emit_event.py は Claude Code のセッションを絶対にブロックしてはならないため、
サーバ不在などいかなる失敗でも exit 0・短時間終了・stdout 空であることを検証する。
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

EMIT_EVENT = Path(__file__).parent.parent / "dashboard" / "hooks" / "emit_event.py"

# 何も listen していないはずのポート（サーバ不在をシミュレートする）
UNUSED_PORT = "18787"


def run_emit_event(stdin_text: str, argv: list[str] | None = None, extra_env: dict | None = None):
    cmd = [sys.executable, str(EMIT_EVENT)] + (argv or [])
    env = {**os.environ, **(extra_env or {})}
    start = time.monotonic()
    result = subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    elapsed = time.monotonic() - start
    return result, elapsed


def test_exits_zero_when_server_absent():
    """サーバが起動していないポートに送っても exit 0 かつ1秒以内・stdout 空"""
    payload = json.dumps({"session_id": "s1", "cwd": "/tmp/agent-crew"})
    result, elapsed = run_emit_event(
        payload, argv=["PreToolUse"], extra_env={"STONEFISH_PORT": UNUSED_PORT}
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert elapsed < 1.0


def test_exits_zero_on_invalid_json():
    """stdin が不正 JSON でも exit 0・stdout 空"""
    result, elapsed = run_emit_event(
        "{not valid json", argv=["Stop"], extra_env={"STONEFISH_PORT": UNUSED_PORT}
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert elapsed < 1.0


def test_exits_zero_on_empty_stdin():
    """stdin が空でも exit 0・stdout 空"""
    result, elapsed = run_emit_event(
        "", argv=["Notification"], extra_env={"STONEFISH_PORT": UNUSED_PORT}
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert elapsed < 1.0


def test_no_argv_uses_payload_hook_event_name():
    """argv[1] が無い場合でもクラッシュせず exit 0（サーバ不在時）"""
    payload = json.dumps({"hook_event_name": "Stop", "session_id": "s1"})
    result, elapsed = run_emit_event(
        payload, argv=[], extra_env={"STONEFISH_PORT": UNUSED_PORT}
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert elapsed < 1.0
