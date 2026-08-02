#!/usr/bin/env python3
"""
pending.py — 承認待ち（に見える）ツール呼び出しをヒューリスティックで検知する（ADR-016）

hooksのNotificationイベントを使わずに transcript 監視だけで運用する方針（ADR-016）を
採ったため、「承認プロンプトで止まっている」状態を直接のイベントとして取得できない。
代わりに、先行実績（pixel-agents-standalone等）に倣い「直近の assistant メッセージが
tool_use を出している一方で、対応する tool_result がまだ記録されていない」状態が
一定時間続いているセッションを「承認待ちに見える」とみなすヒューリスティックで代替する。

## 既知の限界（ADR-016に明記）
このヒューリスティックは「実行時間の長いツール呼び出し（ビルド・大きなテスト実行等）」と
「本当に承認プロンプトで止まっている」状態を区別できない。誤検知の可能性がある前提で、
実用に耐えないと実証された場合は Notification フック1本の追加（エスカレーションパス）を
検討する。
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from discovery import ActiveSession, TAIL_READ_BYTES  # noqa: E402
from tokens import parse_timestamp  # noqa: E402

DEFAULT_PENDING_THRESHOLD_SECONDS = 20.0


def _log(message: str) -> None:
    print(f"[stonefish] {message}", file=sys.stderr)


@dataclass(frozen=True)
class PendingApproval:
    cwd: str
    dept: str
    session_id: str
    tool_name: Optional[str]
    tool_use_id: str
    waiting_seconds: float


def _read_tail_records(jsonl_path: Path, tail_bytes: int = TAIL_READ_BYTES) -> list[dict]:
    """transcript の末尾 tail_bytes バイトをJSONL行としてパースして返す（順序保持）。

    末尾の不完全行は json.loads が失敗して自動的に無視される。
    """
    try:
        size = jsonl_path.stat().st_size
        with jsonl_path.open("rb") as fh:
            if size > tail_bytes:
                fh.seek(size - tail_bytes)
            chunk = fh.read()
    except OSError as e:
        _log(f"transcript 読み込み失敗（スキップ）: {jsonl_path}: {e}")
        return []

    records: list[dict] = []
    for raw_line in chunk.split(b"\n"):
        line = raw_line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return records


def _unresolved_tool_uses(records: list[dict]) -> dict[str, dict]:
    """records（時系列順）から、tool_result がまだ記録されていない tool_use を
    {tool_use_id: {"tool_name":..., "timestamp":...}} の形で返す。
    """
    tool_uses: dict[str, dict] = {}
    resolved_ids: set[str] = set()

    for record in records:
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        role = message.get("role")
        ts_raw = record.get("timestamp")

        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if role == "assistant" and block_type == "tool_use":
                tool_use_id = block.get("id")
                if tool_use_id:
                    tool_uses[tool_use_id] = {"tool_name": block.get("name"), "timestamp": ts_raw}
            elif role == "user" and block_type == "tool_result":
                tool_use_id = block.get("tool_use_id")
                if tool_use_id:
                    resolved_ids.add(tool_use_id)

    return {tid: info for tid, info in tool_uses.items() if tid not in resolved_ids}


def find_pending_approvals(
    sessions: list[ActiveSession],
    threshold_seconds: float = DEFAULT_PENDING_THRESHOLD_SECONDS,
    now: Optional[float] = None,
) -> list[PendingApproval]:
    """アクティブセッション群のうち、未解決の tool_use が threshold_seconds 以上
    続いているものを「承認待ちに見える」ものとして返す。
    """
    if now is None:
        import time
        now = time.time()

    pending: list[PendingApproval] = []
    for session in sessions:
        unresolved = _unresolved_tool_uses(_read_tail_records(Path(session.transcript_path)))
        for tool_use_id, info in unresolved.items():
            ts_raw = info.get("timestamp")
            ts = parse_timestamp(ts_raw) if isinstance(ts_raw, str) else None
            if ts is None:
                continue
            waiting_seconds = now - ts.timestamp()
            if waiting_seconds < threshold_seconds:
                continue
            pending.append(PendingApproval(
                cwd=session.cwd,
                dept=session.dept,
                session_id=session.session_id,
                tool_name=info.get("tool_name"),
                tool_use_id=tool_use_id,
                waiting_seconds=waiting_seconds,
            ))
    return pending
