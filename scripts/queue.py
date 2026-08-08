# /// script
# requires-python = ">=3.12"
# dependencies = ["typer", "pydantic"]
# ///
"""
queue.py — agent-crew タスクキュー操作ヘルパー（Python実装）
queue.sh と同一の JSON スキーマ・コマンド・終了コードを持つ。Phase 1: queue.sh と並走。
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from pydantic import BaseModel, Field

# ---------- 設定 ----------

QUEUE_FILE = Path(os.environ.get("QUEUE_FILE", ".claude/_queue.json"))
MAX_RETRY = int(os.environ.get("MAX_RETRY", "3"))

# complexity に応じた retry 上限値（未設定・不明は MAX_RETRY にフォールバック）
COMPLEXITY_MAX_RETRY: dict[str, int] = {"S": 2, "M": 3, "L": 5}

app = typer.Typer(help="agent-crew タスクキュー操作", add_completion=False)

# ---------- Pydantic モデル ----------

class TaskEvent(BaseModel):
    ts: str
    agent: str
    action: str
    msg: str


class QaHistoryEntry(BaseModel):
    ts: str
    previous_result: str          # 上書き前の qa_result（APPROVED または CHANGES_REQUESTED）
    previous_summary: Optional[str] = None  # 上書き前に記録されていた qa イベントの summary（events から逆引き）
    reason: str                   # --force 実行時に必須で渡す再判定理由


class Task(BaseModel):
    slug: str
    title: str
    status: str
    assigned_to: Optional[str] = None
    complexity: Optional[str] = None
    risk_level: Optional[str] = None
    parallel_group: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)
    qa_mode: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    notes: Optional[str] = None
    retry_count: int = 0
    qa_result: Optional[str] = None
    qa_history: list[QaHistoryEntry] = Field(default_factory=list)
    # Issue #152: 旧 auto_close_issue が notes 内の任意の "#数字" を誤って Issue 番号とみなし
    # 無関係な Issue/PR を誤クローズする事故が複数件発生した。close_issue に明示的に紐付けられた
    # 番号のみをクローズ対象とする（未設定なら None のままでよく、既存 _queue.json との後方互換を
    # Pydantic のデフォルト値で保つ）。複数フェーズ（design→impl→qa）に分かれるタスク群では、
    # 最終フェーズのタスクのみ close_issue を設定する運用とする。
    close_issue: Optional[int] = None
    summary: Optional[str] = None
    events: list[TaskEvent] = Field(default_factory=list)


class QueueFile(BaseModel):
    sprint: str
    tasks: list[Task]


class SignalEvent(BaseModel):
    ts: str
    type: str
    sprint: str
    slug: str
    agent: str
    detail: dict = Field(default_factory=dict)

# ---------- ユーティリティ ----------

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")

def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@contextlib.contextmanager
def queue_lock(queue_file: Path, timeout_secs: float = 5.0):
    import time
    lock_path = queue_file.with_suffix(".lock")
    lock_path.touch(exist_ok=True)
    fh = open(lock_path, "w")
    try:
        deadline = time.monotonic() + timeout_secs
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fh.close()
                    typer.echo(f"ERROR: failed to acquire lock after {timeout_secs}s", err=True)
                    raise typer.Exit(2)
                time.sleep(0.1)
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def load_queue(queue_file: Path = QUEUE_FILE) -> QueueFile:
    if not queue_file.exists():
        typer.echo(f"ERROR: queue file not found: {queue_file}", err=True)
        raise typer.Exit(3)
    try:
        return QueueFile.model_validate_json(queue_file.read_text())
    except Exception as e:
        typer.echo(f"ERROR: invalid JSON in {queue_file}: {e}", err=True)
        raise typer.Exit(4)


def save_queue(q: QueueFile, queue_file: Path = QUEUE_FILE) -> None:
    content = q.model_dump_json(indent=2)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=queue_file.parent,
        prefix=queue_file.name + ".", delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        QueueFile.model_validate_json(tmp_path.read_text())
    except Exception:
        tmp_path.unlink(missing_ok=True)
        typer.echo("ERROR: generated JSON is invalid, aborting write", err=True)
        raise typer.Exit(5)
    os.replace(tmp_path, queue_file)


def get_task(q: QueueFile, slug: str) -> Task:
    for t in q.tasks:
        if t.slug == slug:
            return t
    typer.echo(f"ERROR: slug not found: {slug}", err=True)
    raise typer.Exit(6)


def emit_signal(signal_type: str, slug: str, agent: str, detail: dict) -> None:
    try:
        q = QueueFile.model_validate_json(QUEUE_FILE.read_text())
        event = SignalEvent(
            ts=now_iso(), type=signal_type, sprint=q.sprint,
            slug=slug, agent=agent, detail=detail,
        )
        signals_file = QUEUE_FILE.parent / "_signals.jsonl"
        with open(signals_file, "a") as f:
            f.write(event.model_dump_json() + "\n")
    except Exception:
        pass  # シグナル書き込み失敗は本体を止めない


def calculate_risk(task: Task) -> None:
    risk = task.risk_level or (
        "high" if task.complexity == "L" else
        "medium" if task.complexity == "M" else "low"
    )
    retry = task.retry_count or 0
    if risk == "high" or (risk == "medium" and task.complexity == "L"):
        level = "WARNING: HIGH RISK"
    elif risk == "medium" and retry > 0:
        level = "NOTICE: ELEVATED"
    else:
        level = "INFO: LOW RISK"
    typer.echo(f"RISK: {task.slug} — {level}", err=True)
    typer.echo(f"  risk_level: {risk}", err=True)
    typer.echo(f"  complexity: {task.complexity}", err=True)
    typer.echo(f"  retry_count: {retry}", err=True)


def warn_uncommitted_work(slug: str) -> None:
    """タスク完了時に未コミット差分があれば stderr へ警告する（非ブロック）。

    agent-crew-sprint-27-reliability-003（未コミット作業の保護漏れ）の恒久対応
    （enforcement: code / learning-loop-verification-proposal.md L1-2）。
    repo ルートは _queue.json の位置から明示的に解決する（CWD 依存の誤判定防止）。
    既知の制約: git status は作業ツリー全体の差分を返すため、
    このタスクに関係する差分だけを区別することはできない。
    """
    try:
        anchor = QUEUE_FILE.resolve().parent
        root_proc = subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if root_proc.returncode != 0:
            return
        repo_root = root_proc.stdout.strip()
        status_proc = subprocess.run(
            ["git", "-C", repo_root, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if status_proc.returncode != 0:
            return
        dirty = [line for line in status_proc.stdout.splitlines() if line.strip()]
        if dirty:
            typer.echo(
                f"WARNING: {slug} 完了時点で未コミットの変更が {len(dirty)} 件あります"
                f"（作業ツリー全体）。セッション中断で成果物が失われる前に commit してください。",
                err=True,
            )
    except Exception:
        # 警告は best-effort。done 本体の成否に影響させない
        pass


def close_linked_issue(
    q: QueueFile, slug: str, agent: str, summary: str, override_issue: Optional[int] = None
) -> None:
    """task.close_issue（または --close-issue による一回限りの上書き）が明示設定されている
    場合のみ対応する Issue/PR を close する。notes の自由記述からの推測は一切行わない
    （Issue #152 再発防止）。"""
    task = get_task(q, slug)
    issue_num = override_issue if override_issue is not None else task.close_issue
    if issue_num is None:
        return
    typer.echo(f"INFO: closing linked issue #{issue_num} for {slug} (close_issue field)", err=True)
    try:
        subprocess.run(
            ["gh", "issue", "close", str(issue_num), "--comment", f"✅ {agent}: {slug} 完了 — {summary}"],
            check=True, capture_output=True
        )
        typer.echo(f"OK: Issue #{issue_num} closed")
    except Exception as e:
        typer.echo(f"WARN: failed to close issue #{issue_num}: {e}", err=True)

# ---------- コマンド: init ----------

@app.command(name="init")
def cmd_init(sprint: str) -> None:
    """キューファイルを初期化する（既存ファイルがある場合はエラー）"""
    queue_file = QUEUE_FILE
    if queue_file.exists():
        typer.echo("ERROR: queue already initialized", err=True)
        raise typer.Exit(1)
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    q = QueueFile(sprint=sprint, tasks=[])
    content = q.model_dump_json(indent=2)
    queue_file.write_text(content)
    typer.echo(f"OK: queue initialized (sprint={sprint})")


# ---------- コマンド: start ----------

@app.command()
def start(slug: str) -> None:
    """タスクを IN_PROGRESS に遷移する"""
    with queue_lock(QUEUE_FILE):
        q = load_queue()
        task = get_task(q, slug)
        if task.status == "IN_PROGRESS":
            typer.echo(f"ERROR: {slug} is already IN_PROGRESS.", err=True); raise typer.Exit(11)
        if task.status == "DONE":
            typer.echo(f"ERROR: {slug} is already DONE.", err=True); raise typer.Exit(12)
        if task.status == "BLOCKED":
            typer.echo(f"ERROR: {slug} is BLOCKED.", err=True); raise typer.Exit(13)
        if task.complexity not in ("S", "M", "L", None):
            typer.echo(f"ERROR: complexity must be S, M, or L for {slug} (got: {task.complexity})", err=True)
            raise typer.Exit(10)
        unresolved = [
            d for d in task.depends_on
            if any(t.slug == d and t.status != "DONE" for t in q.tasks)
        ]
        if unresolved:
            typer.echo(f"ERROR: unresolved dependencies: {', '.join(unresolved)}", err=True)
            raise typer.Exit(9)
        calculate_risk(task)
        task.status = "IN_PROGRESS"
        task.updated_at = today()
        task.events.append(TaskEvent(ts=now_iso(), agent=task.assigned_to or "system", action="start", msg="着手"))
        save_queue(q)
    typer.echo(f"OK: {slug} → IN_PROGRESS")
    emit_signal("task.start", slug, task.assigned_to or "system", {})

# ---------- コマンド: done ----------

@app.command()
def done(
    slug: str,
    agent: str,
    summary: str = typer.Argument(default="完了"),
    skip_qa_guard: bool = typer.Option(False, "--skip-qa-guard", help="qa_result未設定でもdoneを許可する（設計/QA対象外タスク用）"),
    close_issue: Optional[int] = typer.Option(None, "--close-issue", help="task.close_issueを一回限り上書きしてクローズするIssue番号"),
) -> None:
    """タスクを DONE に遷移する"""
    with queue_lock(QUEUE_FILE):
        q = load_queue()
        task = get_task(q, slug)
        if task.status == "DONE":
            typer.echo(f"ERROR: {slug} is already DONE.", err=True); raise typer.Exit(15)
        if task.qa_mode in ("inline", "end_of_sprint") and task.qa_result is None and not skip_qa_guard:
            typer.echo(
                f"ERROR: {slug} has qa_mode={task.qa_mode} but qa_result is not set. "
                f"Run 'qa' first, or pass --skip-qa-guard to bypass explicitly.",
                err=True,
            )
            raise typer.Exit(17)
        task.status = "DONE"
        task.updated_at = today()
        task.summary = summary
        task.events.append(TaskEvent(ts=now_iso(), agent=agent, action="done", msg=summary))
        save_queue(q)
    typer.echo(f"OK: {slug} → DONE")
    emit_signal("task.done", slug, agent, {"summary": summary})
    close_linked_issue(q, slug, agent, summary, override_issue=close_issue)
    warn_uncommitted_work(slug)

# ---------- コマンド: handoff ----------

@app.command()
def handoff(slug: str, next_agent: str) -> None:
    """次タスクを READY_FOR_<AGENT> に遷移する"""
    upper = next_agent.upper()
    with queue_lock(QUEUE_FILE):
        q = load_queue()
        task = get_task(q, slug)
        task.status = f"READY_FOR_{upper}"
        task.updated_at = today()
        task.events.append(TaskEvent(ts=now_iso(), agent=next_agent, action="handoff", msg=f"next: READY_FOR_{upper}"))
        save_queue(q)
    typer.echo(f"OK: {slug} → READY_FOR_{upper}")
    emit_signal("task.handoff", slug, next_agent, {"to_agent": next_agent, "next_slug": slug})

# ---------- コマンド: qa ----------

@app.command()
def qa(
    slug: str,
    result: str,
    summary: str = typer.Argument(default=""),
    force: bool = typer.Option(False, "--force", help="既存のqa_resultを上書きする（再判定）"),
    reason: str = typer.Option("", "--reason", help="--force使用時の再判定理由（必須）"),
) -> None:
    """qa_result を記録する"""
    if result not in ("APPROVED", "CHANGES_REQUESTED"):
        typer.echo("ERROR: result must be APPROVED or CHANGES_REQUESTED", err=True)
        raise typer.Exit(1)
    with queue_lock(QUEUE_FILE):
        q = load_queue()
        task = get_task(q, slug)
        if task.qa_result is not None:
            if not force:
                typer.echo(f"ERROR: {slug} already has qa_result={task.qa_result}. Use --force to re-judge.", err=True)
                raise typer.Exit(14)
            if not reason.strip():
                typer.echo("ERROR: --force requires --reason (再判定理由を必須にする)", err=True)
                raise typer.Exit(16)
            # 旧判定の summary を events から逆引きして退避する
            prev_qa_events = [e for e in task.events if e.action in ("qa", "qa_force")]
            prev_summary = prev_qa_events[-1].msg if prev_qa_events else None
            task.qa_history.append(QaHistoryEntry(
                ts=now_iso(), previous_result=task.qa_result,
                previous_summary=prev_summary, reason=reason,
            ))
        task.qa_result = result
        task.updated_at = today()
        action = "qa_force" if force else "qa"
        msg = f"{result}: {summary}" if not force else f"{result} (再判定, reason={reason}): {summary}"
        task.events.append(TaskEvent(ts=now_iso(), agent="Sora", action=action, msg=msg))
        save_queue(q)
    typer.echo(f"OK: {slug} qa_result = {result}" + (" (forced re-judgment)" if force else ""))
    signal_type = "qa.approved" if result == "APPROVED" else "qa.changes_requested"
    emit_signal(signal_type, slug, "Sora", {"reviewer": "Sora", "result": result, "forced": force})

# ---------- コマンド: block ----------

@app.command()
def block(slug: str, agent: str, reason: str) -> None:
    """タスクを BLOCKED に遷移する"""
    with queue_lock(QUEUE_FILE):
        q = load_queue()
        task = get_task(q, slug)
        task.status = "BLOCKED"
        task.updated_at = today()
        task.events.append(TaskEvent(ts=now_iso(), agent=agent, action="block", msg=reason))
        save_queue(q)
    typer.echo(f"BLOCKED: {slug} ({reason})")
    emit_signal("task.blocked", slug, agent, {"reason": reason})

# ---------- コマンド: retry ----------

@app.command()
def retry(slug: str) -> None:
    """retry_count を増やして READY_FOR_RIKU に戻す。上限は complexity に連動する"""
    with queue_lock(QUEUE_FILE):
        q = load_queue()
        task = get_task(q, slug)
        effective_max = COMPLEXITY_MAX_RETRY.get(task.complexity, MAX_RETRY)
        next_retry = (task.retry_count or 0) + 1
        if next_retry > effective_max:
            task.status = "BLOCKED"
            task.events.append(TaskEvent(ts=now_iso(), agent="system", action="block", msg=f"retry limit exceeded (max={effective_max})"))
            save_queue(q)
            typer.echo(f"BLOCKED: {slug} (retry limit {effective_max} exceeded)")
            emit_signal("task.blocked", slug, "system", {"reason": f"retry limit exceeded (max={effective_max})"})
            raise typer.Exit(8)
        task.retry_count = next_retry
        task.qa_result = None
        task.status = "READY_FOR_RIKU"
        task.updated_at = today()
        task.events.append(TaskEvent(ts=now_iso(), agent="system", action="retry", msg=f"retry {next_retry}/{effective_max}"))
        save_queue(q)
    typer.echo(f"OK: {slug} retry {next_retry}/{effective_max} → READY_FOR_RIKU")
    emit_signal("task.retry", slug, "system", {"retry_count": next_retry})

# ---------- コマンド: show ----------

@app.command()
def show(slug: Optional[str] = typer.Argument(default=None)) -> None:
    """タスク一覧または指定タスクの詳細を表示する"""
    q = load_queue()
    if slug:
        task = get_task(q, slug)
        typer.echo(task.model_dump_json(indent=2))
    else:
        summary = [
            {"slug": t.slug, "status": t.status, "assigned_to": t.assigned_to,
             "complexity": t.complexity, "qa_result": t.qa_result, "retry_count": t.retry_count}
            for t in q.tasks
        ]
        typer.echo(json.dumps(summary, indent=2, ensure_ascii=False))

# ---------- コマンド: next ----------

@app.command(name="next")
def cmd_next() -> None:
    """次に実行可能な READY_FOR_* タスクを1件返す"""
    q = load_queue()
    for t in q.tasks:
        if t.status.startswith("READY_FOR_"):
            agent = t.status.replace("READY_FOR_", "").lower()
            typer.echo(f"{t.slug}|{agent}|{t.title}")
            return

# ---------- コマンド: detect-stale ----------

@app.command("detect-stale")
def detect_stale(
    threshold: int = typer.Option(60, "--threshold"),
    slack: bool = typer.Option(False, "--slack"),
) -> None:
    """中断タスク（IN_PROGRESS >= N 分）を検出する"""
    if slack:
        typer.echo("ERROR: --slack は未実装です", err=True)
        raise typer.Exit(1)
    q = load_queue()
    now = datetime.now(timezone.utc)
    for task in q.tasks:
        if task.status != "IN_PROGRESS":
            continue
        start_events = [e for e in task.events if e.action == "start"]
        if not start_events:
            typer.echo(f"WARN: STALE TASK DETECTED\n  slug: {task.slug}\n  issue: start イベントなし", err=True)
            continue
        try:
            ts = start_events[-1].ts.replace("+0000", "+00:00")
            start_dt = datetime.fromisoformat(ts)
            elapsed_min = int((now - start_dt).total_seconds() / 60)
            if elapsed_min >= threshold:
                typer.echo(
                    f"WARN: STALE TASK DETECTED\n  slug: {task.slug}\n  elapsed: {elapsed_min} min",
                    err=True
                )
        except Exception:
            pass

# ---------- コマンド: retro ----------

@app.command()
def retro(
    save: bool = typer.Option(False, "--save"),
    decisions: bool = typer.Option(False, "--decisions"),
) -> None:
    """スプリント完了メトリクスを集計する"""
    q = load_queue()
    total = len(q.tasks)
    n_done = sum(1 for t in q.tasks if t.status == "DONE")
    n_approved = sum(1 for t in q.tasks if t.qa_result == "APPROVED")
    n_retries = sum(t.retry_count for t in q.tasks)
    n_blocked = sum(1 for t in q.tasks if t.status == "BLOCKED")

    lines = [
        f"## {q.sprint} retro",
        f"- タスク数: {total}",
        f"- 完了: {n_done}",
        f"- QA APPROVED: {n_approved}",
        f"- リトライ合計: {n_retries}",
        f"- BLOCKED: {n_blocked}",
    ]

    signals_file = QUEUE_FILE.parent / "_signals.jsonl"
    if signals_file.exists():
        raw = [json.loads(l) for l in signals_file.read_text().splitlines() if l.strip()]
        sprint_ev = [e for e in raw if e.get("sprint") == q.sprint]
        lines += [
            "",
            "## シグナル集計（_signals.jsonl）",
            f"- 記録イベント数: {len(sprint_ev)}件",
            f"- task.done: {sum(1 for e in sprint_ev if e['type'] == 'task.done')}件",
            f"- qa.approved: {sum(1 for e in sprint_ev if e['type'] == 'qa.approved')}件 / "
            f"qa.changes_requested: {sum(1 for e in sprint_ev if e['type'] == 'qa.changes_requested')}件",
            f"- task.retry: {sum(1 for e in sprint_ev if e['type'] == 'task.retry')}件",
            f"- task.blocked: {sum(1 for e in sprint_ev if e['type'] == 'task.blocked')}件",
        ]

    typer.echo("\n".join(lines))

# ---------- graph ヘルパー ----------

MERMAID_CLASS_DEFS = [
    "  classDef done fill:#22c55e,color:#fff",
    "  classDef in_progress fill:#f59e0b,color:#fff",
    "  classDef blocked fill:#ef4444,color:#fff",
    "  classDef ready fill:#3b82f6,color:#fff",
    "  classDef todo fill:#e5e7eb,color:#374151",
]


def _status_to_class(status: str) -> str:
    """タスクステータスを Mermaid CSS クラス名に変換する"""
    if status.startswith("READY_FOR_"):
        return "ready"
    return {
        "IN_PROGRESS": "in_progress",
        "DONE": "done",
        "BLOCKED": "blocked",
    }.get(status, "todo")


def _build_mermaid(q: QueueFile) -> list[str]:
    """QueueFile から Mermaid flowchart LR の行リストを生成する"""
    lines = ["flowchart LR"]

    # ノード定義（_queue.json の記述順を維持）
    for task in q.tasks:
        cls = _status_to_class(task.status)
        agent = task.assigned_to or "?"
        label = f"{task.slug}\\n({agent} · {task.status})"
        lines.append(f'  {task.slug}["{label}"]:::{cls}')

    lines.append("")

    # エッジ定義
    for task in q.tasks:
        for dep in task.depends_on:
            lines.append(f"  {dep} --> {task.slug}")

    lines.append("")
    lines.extend(MERMAID_CLASS_DEFS)

    return lines


def _save_graph(sprint: str, mermaid_body: str) -> None:
    """Mermaid グラフを docs/graphs/<sprint>.md に保存する"""
    project_root = QUEUE_FILE.parent.parent
    graphs_dir = project_root / "docs" / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    out_file = graphs_dir / f"{sprint}.md"
    content = f"# {sprint} — Mermaid依存グラフ\n\n```mermaid\n{mermaid_body}\n```\n"
    out_file.write_text(content)
    typer.echo(f"OK: graph saved to {out_file}", err=True)


# ---------- コマンド: graph ----------

@app.command()
def graph(
    save: bool = typer.Option(False, "--save", help="docs/graphs/<sprint>.md に保存"),
) -> None:
    """タスク依存関係を Mermaid flowchart LR 形式で出力する"""
    q = load_queue()
    mermaid_lines = _build_mermaid(q)
    output = "\n".join(mermaid_lines)

    typer.echo("```mermaid")
    typer.echo(output)
    typer.echo("```")

    if save:
        _save_graph(q.sprint, output)


# ---------- エントリポイント ----------

if __name__ == "__main__":
    app()
