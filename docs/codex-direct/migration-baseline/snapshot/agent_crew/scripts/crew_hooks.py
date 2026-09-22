#!/usr/bin/env python3
"""Claude/Codexで共有する状態判定と、hook入出力の薄い変換。"""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys


EVENTS = {"SessionStart", "UserPromptSubmit", "Stop", "SubagentStop", "TaskCompleted"}


def load_queue(path):
    """不正な台帳を空の完了済み台帳として扱わない。"""
    if not path.exists():
        return None
    if path.stat().st_size > 2_000_000:
        raise ValueError("queueサイズ超過")
    q = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(q, dict) or not isinstance(q.get("tasks"), list):
        raise ValueError("queue形式不正")
    slugs = set()
    for t in q["tasks"]:
        if not isinstance(t, dict) or not all(isinstance(t.get(k), str) for k in ("slug", "status")):
            raise ValueError("task形式不正")
        if not t["slug"] or t["slug"] in slugs:
            raise ValueError("task slug不正")
        slugs.add(t["slug"])
        if not isinstance(t.get("depends_on", []), list):
            raise ValueError("依存形式不正")
        if not all(isinstance(s, str) for s in t.get("depends_on", [])):
            raise ValueError("依存slug不正")
    return q


def qa_required(task):
    return task.get("qa_mode") in ("inline", "end_of_sprint") or task.get("assigned_to") == "Sora"


def evaluate(queue, event, scope="", stop_active=False, retro_marker=False):
    """I/Oなし。queueの判定は両ランタイムでこの関数だけを使う。"""
    notes = []
    block = None
    if queue is None:
        return {"notes": ["queue未配置。タスクを推測して更新しない。"], "block": None}
    tasks = queue["tasks"]
    by_slug = {t["slug"]: t for t in tasks}
    if not tasks:
        notes.append("queueは空。スプリント完了とは判定しない。")
    if event == "SessionStart":
        notes.append("未完了タスク: " + ("、".join(
            f"{t['slug']} [{t['status']}]" for t in tasks if t["status"] != "DONE"
        ) or "なし"))
    bad_qa = [t["slug"] for t in tasks if t["status"] == "DONE" and qa_required(t) and t.get("qa_result") != "APPROVED"]
    if bad_qa:
        notes.append("QA未承認のDONE: " + "、".join(bad_qa) + "。完了扱いにせずレビューを確認。")
    blocked = [t["slug"] for t in tasks if t["status"] == "BLOCKED"]
    if blocked:
        notes.append("人間判断待ち: " + "、".join(blocked))
    active = [t["slug"] for t in tasks if t["status"] == "IN_PROGRESS"]
    if active and event in ("Stop", "SubagentStop"):
        notes.append("作業中: " + "、".join(active) + "。担当作業のqa/done/block記録を確認。他者のタスクは更新しない。")
    ready = [t for t in tasks if t["status"].startswith("READY_FOR_") and all(
        dep in by_slug and by_slug[dep]["status"] == "DONE" and (
            not qa_required(by_slug[dep]) or by_slug[dep].get("qa_result") == "APPROVED"
        ) for dep in t.get("depends_on", [])
    )]
    if ready and not blocked:
        notes.append("次に着手可能: " + ready[0]["slug"] + "。通常はメインが直接実装し、必要な独立レビューのみ委譲。")
    retro = [t for t in tasks if "retro" in t["slug"].lower()]
    if retro:
        last = retro[-1]
        others = [t for t in tasks if t is not last]
        if last["status"] != "DONE" and not retro_marker and others and all(t["status"] == "DONE" for t in others):
            notes.append("レトロ未完了: " + last["slug"] + "。スプリント完了前に実施。")
    if tasks and all(t["status"] == "DONE" for t in tasks) and not bad_qa:
        notes.append("全タスクDONE・QA対象APPROVED。通知やVault転記は明示承認された操作として実施。")
    # 子の停止で親のタスクを完了させない。scopeを明示した親Stopだけを制御する。
    if event == "Stop" and scope:
        task = by_slug.get(scope)
        if task is None:
            notes.append("指定タスクがqueueに存在しない。CREW_TASK_SLUGを確認。")
        elif task["status"] == "IN_PROGRESS" or (task["status"] == "DONE" and qa_required(task) and task.get("qa_result") != "APPROVED"):
            reason = f"担当タスク {scope} の完了条件が未充足。検証・独立レビューとqueue記録を確認し、進められない場合はblockで理由を残してください。"
            if stop_active:
                notes.append("継続後も未解決。自動再継続を止め、未完了をオーナーへ報告。")
            else:
                block = reason
    return {"notes": notes, "block": block}


def encode(runtime, event, result):
    """共通判定を各ランタイムでサポートする応答へ変換する。"""
    text = "[agent-crew / " + runtime + "]\n" + "\n".join(result["notes"])
    if event in ("SessionStart", "UserPromptSubmit"):
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    if result["block"]:
        return {"decision": "block", "reason": result["block"]}
    return {"systemMessage": text} if result["notes"] else {}


def run_check(command, root, env, timeout=3):
    """タイムアウトした検査は孫プロセスも含めて終了する（macOS/Linux）。"""
    with subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            raise
        return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def local_checks(root, checks, env):
    """既存の読取り専用コマンドだけを呼び、機密を含む生出力は返さない。"""
    notes = []
    commands = []
    if checks.get("privacy") is True:
        commands.append(("privacy", ["bash", str(root / "scripts/privacy-check.sh"), "--summary"]))
    if checks.get("lesson_candidates") is True:
        commands.append(("lessons", ["bash", str(root / "scripts/lessons.sh"), "list-rule-candidates", "--min-priority", "4"]))
    for kind, command in commands:
        try:
            # 2検査合計6秒以内。ランタイムの15秒timeout前に判定JSONを返す。
            result = run_check(command, root, env, timeout=3)
            if result.returncode:
                notes.append(f"{kind}チェック失敗。手動で再検証。")
            elif kind == "privacy":
                data = json.loads(result.stdout)
                count = data.get("findings")
                if type(count) is not int or count < 0:
                    raise ValueError("count")
                if count:
                    notes.append(f"プライバシー検査: {count}件のパターン検出。公開前にローカルで確認（生データはhookへ出力しない）。")
            else:
                count = 0
                for line in result.stdout.splitlines():
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("lesson")
                    count += 1
                if count:
                    notes.append(f"教訓ルール候補: {count}件。scripts/propose-lesson-rules.sh --dry-runで確認。")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            notes.append(f"{kind}チェックを完了できませんでした。手動で再検証。")
    return notes


def lesson_summary(root, env):
    """開始時に既存の教訓台帳を参照。記述本文はプロンプトへ転載しない。"""
    path = Path(env.get("LESSONS_FILE", str(Path(env.get("HOME", str(Path.home()))) / ".claude/_lessons.json")))
    if not path.exists():
        return "教訓台帳未配置。"
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("size")
        lessons = json.loads(path.read_text())["lessons"]
        if not isinstance(lessons, list):
            raise ValueError("lessons")
        selected = [x for x in lessons if isinstance(x, dict) and x.get("project") == root.name and not x.get("issue_url") and x.get("status") not in ("resolved", "closed", "implemented", "verified", "dismissed")]
        scores = sorted([x.get("priority_score", 0) for x in selected if type(x.get("priority_score", 0)) in (int, float)], reverse=True)[:3]
        return f"このプロジェクトの未対処教訓: {len(selected)}件、上位priority: {scores}。詳細は既存lessons手順で確認。"
    except (OSError, ValueError, KeyError, TypeError):
        return "教訓台帳を検証できませんでした。手動で確認。"


def run(runtime, event, payload, root, env):
    if not isinstance(payload, dict):
        raise ValueError("hook入力はobjectが必要")
    if payload.get("hook_event_name", event) != event:
        raise ValueError("hook event不一致")
    if "stop_hook_active" in payload and type(payload["stop_hook_active"]) is not bool:
        raise ValueError("stop_hook_activeはboolが必要")
    if event == "TaskCompleted" and runtime != "claude":
        raise ValueError("CodexにTaskCompletedは未対応")
    cwd = payload.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not Path(cwd).is_absolute() or not Path(cwd).resolve().is_relative_to(root)):
        raise ValueError("hook cwdが対象repoの外")
    queue_path = Path(env.get("QUEUE_FILE", str(root / ".claude/_queue.json")))
    if not queue_path.is_absolute():
        queue_path = root / queue_path
    queue = load_queue(queue_path)
    if event == "TaskCompleted":
        task_id = payload.get("task_id")
        found = queue and any(t["slug"] == task_id for t in queue["tasks"])
        note = ("TaskCompleted観測: " + task_id + "。queue更新はqueue.shで確認。") if found else "TaskCompletedのtask_idとqueue slugは対応未確認。タスクを推測せず台帳を保持。"
        return encode(runtime, event, {"notes": [note], "block": None})
    sprint = queue.get("sprint", "") if queue else ""
    marker = bool(isinstance(sprint, str) and re.fullmatch(r"[A-Za-z0-9_-]+", sprint) and (root / "docs/sprints" / (sprint + "-retro.md")).is_file())
    scope = env.get("CREW_TASK_SLUG", "")
    scope_root = env.get("CREW_TASK_ROOT", "")
    scope_invalid = bool(scope and (not scope_root or Path(scope_root).resolve() != root or queue_path.resolve() != (root / ".claude/_queue.json").resolve()))
    result = evaluate(queue, event, "" if scope_invalid else scope, payload.get("stop_hook_active", False), marker)
    if scope_invalid:
        result["notes"].append("task scopeのrepoが不一致。終了を阻止せず、起動時の指定を確認。")
    if event in ("SessionStart", "UserPromptSubmit"):
        model = payload.get("model")
        observed = model if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", model) else "未確認"
        result["notes"].append("モデル: " + observed + "（hook payloadで観測できる値のみ）。共通契約: AGENTS.md。")
        result["notes"].append("スプリント計画・レトロ前にObsidianのagent-crew-failure-patterns.mdとagent-crew-adr-index.mdを確認。")
        if event == "SessionStart":
            result["notes"].append(lesson_summary(root, env))
    if event == "Stop":
        manifest = json.loads((root / "config/crew-hooks.json").read_text())
        result["notes"].extend(local_checks(root, manifest.get("checks", {}), env))
    return encode(runtime, event, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("claude", "codex"), required=True)
    parser.add_argument("--event", choices=sorted(EVENTS), required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("入力サイズ超過")
        payload = json.loads(raw)
        result = run(args.runtime, args.event, payload, args.root.resolve(), dict(os.environ))
    except (OSError, ValueError, TypeError, RecursionError):
        # 不正payloadや例外の文字列には秘密が含まれうるため転送しない。
        result = {"systemMessage": "[agent-crew] hook入力・設定・台帳の検証に失敗。判定不能として手動確認してください。"}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
