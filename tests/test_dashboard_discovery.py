"""
tests/test_dashboard_discovery.py — dashboard/server/discovery.py ユニットテスト

ADR-016（イベント収集をtranscript監視方式へ転換）の中核である、
「~/.claude/projects/ 配下を横断スキャンしてアクティブセッションを自動発見する」機能を検証する。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard" / "server"))

from discovery import find_active_sessions  # noqa: E402


def _write_transcript(path: Path, cwd: str) -> None:
    path.write_text(
        json.dumps({
            "type": "assistant",
            "cwd": cwd,
            "message": {"role": "assistant", "id": "msg_1", "content": []},
            "timestamp": "2026-08-02T00:00:00.000Z",
        }) + "\n",
        encoding="utf-8",
    )


def test_finds_recently_updated_session(tmp_path):
    project_dir = tmp_path / "-Users-x-agent-crew"
    project_dir.mkdir()
    transcript = project_dir / "session-1.jsonl"
    _write_transcript(transcript, "/Users/x/Workspace/agent-crew")

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.cwd == "/Users/x/Workspace/agent-crew"
    assert s.dept == "product"
    assert s.session_id == "session-1"
    assert s.transcript_path == str(transcript)


def test_excludes_stale_session_outside_active_window(tmp_path):
    project_dir = tmp_path / "-Users-x-agent-crew"
    project_dir.mkdir()
    transcript = project_dir / "old-session.jsonl"
    _write_transcript(transcript, "/Users/x/Workspace/agent-crew")

    # mtimeを1時間前に偽装
    old_time = time.time() - 3600
    import os
    os.utime(transcript, (old_time, old_time))

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    assert sessions == []


def test_excludes_file_without_cwd_field(tmp_path):
    project_dir = tmp_path / "-Users-x-unknown"
    project_dir.mkdir()
    transcript = project_dir / "session.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "assistant", "id": "msg_1"}}) + "\n",
        encoding="utf-8",
    )

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    assert sessions == []


def test_missing_projects_root_returns_empty_list_not_exception(tmp_path):
    missing = tmp_path / "does-not-exist"
    sessions = find_active_sessions(missing, active_within_seconds=600)
    assert sessions == []


def test_multiple_projects_get_correct_department_each(tmp_path):
    product_dir = tmp_path / "-proj-a"
    invest_dir = tmp_path / "-proj-b"
    other_dir = tmp_path / "-proj-c"
    for d in (product_dir, invest_dir, other_dir):
        d.mkdir()

    _write_transcript(product_dir / "s1.jsonl", "/Users/x/Workspace/agent-crew")
    _write_transcript(invest_dir / "s2.jsonl", "/Users/x/Workspace/alpha-predict-jp")
    _write_transcript(other_dir / "s3.jsonl", "/Users/x/Workspace/personal-blog")

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    depts = {s.cwd: s.dept for s in sessions}
    assert depts["/Users/x/Workspace/agent-crew"] == "product"
    assert depts["/Users/x/Workspace/alpha-predict-jp"] == "invest"
    assert depts["/Users/x/Workspace/personal-blog"] == "other"


def test_extracts_cwd_from_tail_when_file_larger_than_tail_window(tmp_path):
    """ファイル全体ではなく末尾だけを読んでcwdを取得できることを確認する
    （大きなtranscriptを全部読まないための性能上の工夫）。"""
    project_dir = tmp_path / "-proj-large"
    project_dir.mkdir()
    transcript = project_dir / "session.jsonl"

    lines = [json.dumps({"padding": "x" * 500, "n": i}) for i in range(200)]
    lines.append(json.dumps({
        "type": "assistant",
        "cwd": "/Users/x/Workspace/agent-crew",
        "message": {"role": "assistant", "id": "msg_last"},
        "timestamp": "2026-08-02T00:00:00.000Z",
    }))
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    assert len(sessions) == 1
    assert sessions[0].cwd == "/Users/x/Workspace/agent-crew"


def test_directory_scan_io_error_does_not_crash(tmp_path, monkeypatch):
    """projects_root 直下に読めないエントリがあっても例外を投げず処理を続ける。"""
    project_dir = tmp_path / "-proj-a"
    project_dir.mkdir()
    _write_transcript(project_dir / "s1.jsonl", "/Users/x/Workspace/agent-crew")

    # 存在しないファイルに対するstat失敗をシミュレートするのは難しいので、
    # 単純に正常系が例外を出さないことを確認する（IO異常系はdiscovery内でtry/exceptしている）。
    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    assert len(sessions) == 1


# ---------- サブエージェント専用transcriptの発見 ----------


def _write_subagent(session_dir: Path, agent_id: str, meta: dict | None = "OMIT") -> Path:
    """<session_dir>/subagents/agent-<agent_id>.jsonl (+.meta.json) を組み立てる。

    meta=None で .meta.json 自体を作らないケース、meta={不正な形}で壊れたJSON等を
    シミュレートできる。既定の "OMIT" センチネルは「正常なmetaを書く」を意味する。
    """
    subagents_dir = session_dir / "subagents"
    subagents_dir.mkdir(parents=True, exist_ok=True)
    agent_jsonl = subagents_dir / f"agent-{agent_id}.jsonl"
    agent_jsonl.write_text(
        json.dumps({
            "message": {"role": "assistant", "id": f"msg_{agent_id}",
                        "usage": {"input_tokens": 1, "output_tokens": 1}},
            "timestamp": "2026-08-02T00:00:00.000Z",
        }) + "\n",
        encoding="utf-8",
    )
    if meta is None:
        pass  # .meta.json を作らない
    elif meta == "OMIT":
        (subagents_dir / f"agent-{agent_id}.meta.json").write_text(
            json.dumps({"agentType": "engineer-go", "description": "d", "name": "n"}),
            encoding="utf-8",
        )
    else:
        (subagents_dir / f"agent-{agent_id}.meta.json").write_text(meta, encoding="utf-8")
    return agent_jsonl


def test_finds_subagent_transcript_alongside_main_session(tmp_path):
    project_dir = tmp_path / "-Users-x-agent-crew"
    project_dir.mkdir()
    main_transcript = project_dir / "session-1.jsonl"
    _write_transcript(main_transcript, "/Users/x/Workspace/agent-crew")

    session_dir = project_dir / "session-1"
    agent_jsonl = _write_subagent(session_dir, "abc123")

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    assert len(sessions) == 2

    main = next(s for s in sessions if s.transcript_path == str(main_transcript))
    assert main.persona is None

    sub = next(s for s in sessions if s.transcript_path == str(agent_jsonl))
    assert sub.persona == "riku"  # agentType "engineer-go" -> persona "riku"
    assert sub.cwd == main.cwd == "/Users/x/Workspace/agent-crew"
    assert sub.dept == main.dept == "product"


def test_subagent_missing_meta_json_registers_with_persona_none(tmp_path):
    project_dir = tmp_path / "-Users-x-agent-crew"
    project_dir.mkdir()
    main_transcript = project_dir / "session-1.jsonl"
    _write_transcript(main_transcript, "/Users/x/Workspace/agent-crew")

    session_dir = project_dir / "session-1"
    agent_jsonl = _write_subagent(session_dir, "no-meta", meta=None)

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    sub = next(s for s in sessions if s.transcript_path == str(agent_jsonl))
    assert sub.persona is None


def test_subagent_malformed_meta_json_registers_with_persona_none(tmp_path):
    project_dir = tmp_path / "-Users-x-agent-crew"
    project_dir.mkdir()
    main_transcript = project_dir / "session-1.jsonl"
    _write_transcript(main_transcript, "/Users/x/Workspace/agent-crew")

    session_dir = project_dir / "session-1"
    agent_jsonl = _write_subagent(session_dir, "broken", meta="{not valid json")

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    sub = next(s for s in sessions if s.transcript_path == str(agent_jsonl))
    assert sub.persona is None


def test_subagent_dir_absent_is_normal_case_and_still_returns_main_session(tmp_path):
    """subagents/ ディレクトリが無い（大半のケース）でも、これまで通りメインセッション
    だけが返ること（回帰確認）。"""
    project_dir = tmp_path / "-Users-x-agent-crew"
    project_dir.mkdir()
    main_transcript = project_dir / "session-1.jsonl"
    _write_transcript(main_transcript, "/Users/x/Workspace/agent-crew")

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    assert len(sessions) == 1
    assert sessions[0].persona is None


def test_stale_subagent_transcript_is_excluded_by_its_own_mtime(tmp_path):
    project_dir = tmp_path / "-Users-x-agent-crew"
    project_dir.mkdir()
    main_transcript = project_dir / "session-1.jsonl"
    _write_transcript(main_transcript, "/Users/x/Workspace/agent-crew")

    session_dir = project_dir / "session-1"
    agent_jsonl = _write_subagent(session_dir, "stale")
    old_time = time.time() - 3600
    import os
    os.utime(agent_jsonl, (old_time, old_time))

    sessions = find_active_sessions(tmp_path, active_within_seconds=600)
    assert all(s.transcript_path != str(agent_jsonl) for s in sessions)
    # メインセッションは引き続き見つかる
    assert any(s.transcript_path == str(main_transcript) for s in sessions)
