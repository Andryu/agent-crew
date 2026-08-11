#!/usr/bin/env python3
"""
discovery.py — ~/.claude/projects/ 配下を横断スキャンし、アクティブな Claude Code
セッション（transcript）を自動発見する（ADR-016: hooks配線不要のtranscript監視方式）。

Claude Code は hooks の有無に関わらず、セッションごとに
`~/.claude/projects/<encoded-cwd>/<session_id>.jsonl` へ transcript を書き続ける。
本モジュールはこれを定期的に横断スキャンし、「最近更新された transcript ＝ アクティブ
セッション」とみなして (transcript_path, cwd, dept, session_id) を抽出する。
リポジトリごとの hooks 設定は一切不要（新規プロジェクトも自動的に対象になる）。

副作用はファイル読み込みのみ。標準ライブラリのみで完結する。
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from enrich import department_for, persona_for  # noqa: E402

# cwd 抽出のために transcript の末尾から読むバイト数。
# 1行あたり通常は数KB以内に収まるため、直近数行を確実に拾える余裕を持たせている。
TAIL_READ_BYTES = 16 * 1024

DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_ACTIVE_WINDOW_SECONDS = 600.0  # 10分以内に更新された transcript をアクティブとみなす


def _log(message: str) -> None:
    print(f"[stonefish] {message}", file=sys.stderr)


@dataclass(frozen=True)
class ActiveSession:
    transcript_path: str
    session_id: str
    cwd: str
    dept: str
    mtime: float
    # サブエージェント専用transcriptから発見した場合のみ設定する。メインセッション自身は
    # 常に None（既存の挙動を変えないため）。
    persona: Optional[str] = None


def _extract_cwd(jsonl_path: Path) -> Optional[str]:
    """transcript の末尾付近から直近の cwd を取り出す。見つからなければ None を返す。

    Claude Code の transcript は各行（assistant/user/system いずれも）に "cwd" フィールドを
    含む。ファイル全体を読むと大きな transcript では重いため、末尾 TAIL_READ_BYTES バイト
    だけを読み、末尾の行から順に試す（末尾の不完全行は json.loads が失敗して自動的に
    スキップされ、その前の行が試される）。
    """
    try:
        size = jsonl_path.stat().st_size
        with jsonl_path.open("rb") as fh:
            if size > TAIL_READ_BYTES:
                fh.seek(size - TAIL_READ_BYTES)
            chunk = fh.read()
    except OSError as e:
        _log(f"transcript 読み込み失敗（スキップ）: {jsonl_path}: {e}")
        return None

    for raw_line in reversed(chunk.split(b"\n")):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        cwd = record.get("cwd")
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


def _read_agent_type(meta_path: Path) -> Optional[str]:
    """agent-<id>.meta.json から agentType を取り出す。

    サブエージェント専用transcriptにはメインセッションのような "cwd" フィールドが無いため、
    persona解決には代わりにこの sidecar の agentType を使う。読めない・壊れている・
    agentType が無い場合はクラッシュさせず None を返す（persona 未解決のまま登録される）。
    """
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    agent_type = raw.get("agentType")
    return agent_type if isinstance(agent_type, str) and agent_type else None


def _find_subagent_sessions(
    session_jsonl_path: Path,
    parent_session_id: str,
    cwd: str,
    dept: str,
    active_within_seconds: float,
    now: float,
) -> list[ActiveSession]:
    """<session_id>/subagents/agent-*.jsonl を探し、見つかった分だけ ActiveSession 化する。

    サブディレクトリが存在しない（大半のセッションはサブエージェントを使わない）場合は
    単に空リストを返す。
    """
    subagents_dir = session_jsonl_path.parent / session_jsonl_path.stem / "subagents"
    if not subagents_dir.is_dir():
        return []

    try:
        agent_jsonl_paths = list(subagents_dir.glob("agent-*.jsonl"))
    except OSError as e:
        _log(f"subagentsディレクトリ走査失敗（スキップ）: {subagents_dir}: {e}")
        return []

    sessions: list[ActiveSession] = []
    for agent_jsonl_path in agent_jsonl_paths:
        try:
            mtime = agent_jsonl_path.stat().st_mtime
        except OSError as e:
            _log(f"stat失敗（スキップ）: {agent_jsonl_path}: {e}")
            continue
        # サブエージェント自身のtranscriptが直近active_within_seconds秒以内に更新されて
        # いない限り、そのカードのトークンには一切反映されない（発見の前提条件）。
        if now - mtime > active_within_seconds:
            continue

        meta_path = agent_jsonl_path.with_name(agent_jsonl_path.stem + ".meta.json")
        agent_type = _read_agent_type(meta_path)
        persona = persona_for({"agent_type": agent_type}) if agent_type else None

        sessions.append(ActiveSession(
            transcript_path=str(agent_jsonl_path),
            session_id=f"{parent_session_id}/{agent_jsonl_path.stem}",
            cwd=cwd,
            dept=dept,
            mtime=mtime,
            persona=persona,
        ))

    return sessions


def find_active_sessions(
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
    active_within_seconds: float = DEFAULT_ACTIVE_WINDOW_SECONDS,
    now: Optional[float] = None,
) -> list[ActiveSession]:
    """projects_root 配下の *.jsonl を横断スキャンし、直近 active_within_seconds 秒以内に
    更新されたファイルをアクティブセッションとして返す。

    cwd が取得できなかったファイル（空・壊れている・書き込み開始直後など）は除外する。
    projects_root が存在しない環境（このマシンで一度も Claude Code を使っていない等）では
    空リストを返す（例外にしない）。
    """
    if now is None:
        now = time.time()

    sessions: list[ActiveSession] = []
    if not projects_root.exists():
        return sessions

    try:
        project_dirs = list(projects_root.iterdir())
    except OSError as e:
        _log(f"projects_root 走査失敗: {projects_root}: {e}")
        return sessions

    for project_dir in project_dirs:
        if not project_dir.is_dir():
            continue
        try:
            jsonl_paths = list(project_dir.glob("*.jsonl"))
        except OSError as e:
            _log(f"プロジェクトディレクトリ走査失敗（スキップ）: {project_dir}: {e}")
            continue

        for jsonl_path in jsonl_paths:
            try:
                mtime = jsonl_path.stat().st_mtime
            except OSError as e:
                _log(f"stat失敗（スキップ）: {jsonl_path}: {e}")
                continue
            if now - mtime > active_within_seconds:
                continue

            cwd = _extract_cwd(jsonl_path)
            if cwd is None:
                continue

            dept = department_for(cwd)
            sessions.append(ActiveSession(
                transcript_path=str(jsonl_path),
                session_id=jsonl_path.stem,
                cwd=cwd,
                dept=dept,
                mtime=mtime,
            ))
            sessions.extend(_find_subagent_sessions(
                jsonl_path, jsonl_path.stem, cwd, dept, active_within_seconds, now,
            ))

    return sessions
