"""
tests/test_dashboard_pending.py — dashboard/server/pending.py ユニットテスト

ADR-016で採用した「hooksのNotificationイベントを使わず、tool_use後にtool_resultが
一定時間ないことをヒューリスティックで承認待ちとみなす」ロジックを検証する。
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard" / "server"))

from discovery import ActiveSession  # noqa: E402
from pending import find_pending_approvals  # noqa: E402

BASE_TS = "2026-08-02T00:00:00.000Z"
BASE_EPOCH = datetime(2026, 8, 2, 0, 0, 0, tzinfo=timezone.utc).timestamp()


def _session(transcript_path: Path, cwd: str = "/Users/x/proj", dept: str = "product") -> ActiveSession:
    return ActiveSession(
        transcript_path=str(transcript_path),
        session_id=transcript_path.stem,
        cwd=cwd,
        dept=dept,
        mtime=BASE_EPOCH,
    )


def _assistant_tool_use(tool_use_id: str, tool_name: str, ts: str) -> str:
    return json.dumps({
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_use_id, "name": tool_name}],
        },
        "timestamp": ts,
    })


def _user_tool_result(tool_use_id: str, ts: str) -> str:
    return json.dumps({
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}],
        },
        "timestamp": ts,
    })


def test_unresolved_tool_use_past_threshold_is_pending(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(_assistant_tool_use("toolu_1", "Bash", BASE_TS) + "\n", encoding="utf-8")

    now = BASE_EPOCH + 30  # 30秒経過
    pending = find_pending_approvals([_session(transcript)], threshold_seconds=20.0, now=now)

    assert len(pending) == 1
    assert pending[0].tool_use_id == "toolu_1"
    assert pending[0].tool_name == "Bash"
    assert pending[0].waiting_seconds == pytest.approx(30.0, abs=0.01)
    assert pending[0].cwd == "/Users/x/proj"
    assert pending[0].dept == "product"


def test_resolved_tool_use_is_not_pending(tmp_path):
    transcript = tmp_path / "session.jsonl"
    lines = [
        _assistant_tool_use("toolu_1", "Bash", BASE_TS),
        _user_tool_result("toolu_1", "2026-08-02T00:00:05.000Z"),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    now = BASE_EPOCH + 30
    pending = find_pending_approvals([_session(transcript)], threshold_seconds=20.0, now=now)
    assert pending == []


def test_recent_tool_use_below_threshold_is_not_pending(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(_assistant_tool_use("toolu_1", "Bash", BASE_TS) + "\n", encoding="utf-8")

    now = BASE_EPOCH + 5  # まだ5秒しか経っていない
    pending = find_pending_approvals([_session(transcript)], threshold_seconds=20.0, now=now)
    assert pending == []


def test_multiple_tool_uses_only_unresolved_reported(tmp_path):
    transcript = tmp_path / "session.jsonl"
    lines = [
        _assistant_tool_use("toolu_1", "Bash", BASE_TS),
        _user_tool_result("toolu_1", "2026-08-02T00:00:01.000Z"),
        _assistant_tool_use("toolu_2", "Write", "2026-08-02T00:00:02.000Z"),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    now = BASE_EPOCH + 60
    pending = find_pending_approvals([_session(transcript)], threshold_seconds=20.0, now=now)
    assert len(pending) == 1
    assert pending[0].tool_use_id == "toolu_2"
    assert pending[0].tool_name == "Write"


def test_no_tool_use_blocks_returns_empty(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}, "timestamp": BASE_TS}) + "\n",
        encoding="utf-8",
    )
    pending = find_pending_approvals([_session(transcript)], threshold_seconds=20.0, now=BASE_EPOCH + 999)
    assert pending == []


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    transcript = tmp_path / "session.jsonl"
    lines = [
        "{not valid json",
        _assistant_tool_use("toolu_1", "Bash", BASE_TS),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    now = BASE_EPOCH + 30
    pending = find_pending_approvals([_session(transcript)], threshold_seconds=20.0, now=now)
    assert len(pending) == 1


def test_missing_transcript_file_does_not_crash(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.jsonl"
    session = _session(missing)
    pending = find_pending_approvals([session], threshold_seconds=20.0, now=BASE_EPOCH + 30)
    assert pending == []
    captured = capsys.readouterr()
    assert "stonefish" in captured.err


def test_multiple_sessions_across_departments(tmp_path):
    t1 = tmp_path / "s1.jsonl"
    t2 = tmp_path / "s2.jsonl"
    t1.write_text(_assistant_tool_use("toolu_1", "Bash", BASE_TS) + "\n", encoding="utf-8")
    t2.write_text(_assistant_tool_use("toolu_2", "Edit", BASE_TS) + "\n", encoding="utf-8")

    sessions = [
        _session(t1, cwd="/Users/x/agent-crew", dept="product"),
        _session(t2, cwd="/Users/x/alpha-predict-jp", dept="invest"),
    ]
    pending = find_pending_approvals(sessions, threshold_seconds=20.0, now=BASE_EPOCH + 30)
    depts = {p.dept for p in pending}
    assert depts == {"product", "invest"}
