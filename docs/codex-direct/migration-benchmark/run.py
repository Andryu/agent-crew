#!/usr/bin/env python3
"""P5の固定snapshotを隔離して実行し、再現可能な非機密証跡を残す。"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "migration-baseline"
WORK = Path("/private/tmp/agent-crew-p5-benchmark/formal")
UNKNOWN = "unknown"
ALLOWED = {"C1", "C2", "C3", "C4", "C5", "C6"}
CLI_TIMEOUT_SECONDS = 240
VALIDATION_TIMEOUT_SECONDS = 45
B_INDEX = HERE / "b-contract-index.json"
A_INDEX = HERE / "a-contract-index.json"
ACTIVE_GROUP = None
REPOSITORY = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verified_b_inputs():
    index = load(B_INDEX)
    tree = HERE / "b-contract"
    actual = {str(path.relative_to(tree)): sha(path) for path in tree.rglob("*") if path.is_file()}
    expected = index.get("files", {})
    if actual != expected or any(path.is_symlink() for path in tree.rglob("*")):
        raise RuntimeError("B指示treeが固定indexと不一致")
    return actual


def verified_a_inputs():
    index = load(A_INDEX)
    tree = HERE / "a-contract"
    actual = {str(path.relative_to(tree)): sha(path) for path in tree.rglob("*") if path.is_file()}
    if actual != index.get("files", {}) or any(path.is_symlink() for path in tree.rglob("*")):
        raise RuntimeError("A補足指示treeが固定indexと不一致")
    return actual


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def c6_task():
    comparison = load(HERE / "comparison-v2.json")
    return next(task for task in comparison["tasks"] if task["id"] == "C6")


def permission_policy(root, task):
    """モデル・validator・preflightで共有する最小write許可。"""
    writes = [root / ".benchmark-tmp"]
    if task["id"] == "C6":
        # progress.pyは同directoryの.state-*へ書いてからos.replaceする。
        writes.append(root / "migration-progress")
    else:
        writes.append(root / "docs/plans")
        writes.extend(root / name for name in task["input"] + task["fixture"])
    return writes


def sandbox_command(root, task, command):
    profile = "p5_fixture"
    config = [f'permissions.{profile}.description="P5 fixture"',
              f'permissions.{profile}.extends=":read-only"',
              f'permissions.{profile}.network.enabled=false']
    config.extend(f'permissions.{profile}.filesystem.{path}="write"' for path in permission_policy(root, task))
    return ["codex", "sandbox", "-P", profile, "-C", str(root),
            *sum((["-c", value] for value in config), []), "--", *command]


def host_guard():
    paths = (REPOSITORY / "migration-progress/state.json", REPOSITORY / ".claude/_queue.json")
    assert (REPOSITORY / "AGENTS.md").is_file(), "host guard rootがagent-crewではありません"
    result = {}
    for path in paths:
        try:
            stat = path.lstat()
            regular = path.is_file() and not path.is_symlink()
            result[str(path.relative_to(REPOSITORY))] = {
                "exists": True, "symlink": path.is_symlink(), "regular": regular,
                "sha256": sha(path) if regular else None, "mode": stat.st_mode & 0o777,
            }
        except FileNotFoundError:
            result[str(path.relative_to(REPOSITORY))] = {"exists": False, "symlink": False,
                                                          "regular": False, "sha256": None, "mode": None}
    return result


def accepted_c6_snapshot(root):
    """モデル終了後のstateを、モデル権限外のcampaign siblingへ一度だけ固定する。"""
    accepted = root.parent / ".accepted" / root.name
    for parent in (root.parent / ".accepted", accepted):
        if os.path.lexists(parent) and parent.is_symlink():
            raise RuntimeError("accepted snapshot pathにsymlinkがあります")
    if os.path.lexists(accepted):
        raise RuntimeError("accepted snapshotを上書きしません")
    accepted.mkdir(parents=True)
    for name in ("progress.py", "README.md"):
        source = BASE / "snapshot/agent_crew/migration-progress" / name
        destination = accepted / "migration-progress" / name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(source, destination)
    state = root / "migration-progress/state.json"
    data = state.read_bytes()
    destination = accepted / "migration-progress/state.json"
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return accepted


def preliminary_pass(cli_exit, validation_exit, scope, handoff, guard_unchanged=True):
    return cli_exit == 0 and validation_exit == 0 and not scope and handoff and guard_unchanged


def prepare(task_id, condition, repeat, campaign):
    comparison = load(BASE / "comparison.json")
    index = load(BASE / "snapshot-index.json")
    task = c6_task() if task_id == "C6" else next(t for t in comparison["tasks"] if t["id"] == task_id)
    root = WORK / campaign / f"{task_id}-{condition}-{repeat}"
    if root.exists():
        raise RuntimeError(f"既存runは上書きしません: {root}")
    root.mkdir(parents=True)
    hashes = {}
    for entry in index["entries"]:
        source = BASE / entry["snapshot"]
        if sha(source) != entry["sha256"]:
            raise RuntimeError(f"P0 hash不一致: {entry['snapshot']}")
        c6_visible = set(task["input"] + task["fixture"])
        if task_id == "C6" and condition == "A" and entry["snapshot"] in comparison["A_instruction_snapshot"]:
            c6_visible.add(entry["source"])
        if entry["repo"] == task["repo"] and (task_id != "C6" or entry["source"] in c6_visible):
            destination = root / entry["source"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if destination.name == "crew":
                destination.chmod(0o755)
            hashes[entry["source"]] = entry["sha256"]
    if task_id == "C6":
        fixture = index["synthetic_fixture"]
        source = BASE / fixture["path"]
        if sha(source) != fixture["sha256"]:
            raise RuntimeError("合成fixture hash不一致")
        destination = root / "migration-progress/state.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        hashes["migration-progress/state.json"] = fixture["sha256"]
    if condition == "A" and task["repo"] == "wealth_advisor":
        verified_a_inputs()
        source = HERE / "a-contract/wealth_advisor/.agents/skills/wealth-advisor/SKILL.md"
        destination = root / ".agents/skills/wealth-advisor/SKILL.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        hashes[str(destination.relative_to(root))] = sha(destination)
    if condition == "B":
        verified_b_inputs()
        contract = HERE / "b-contract" / task["repo"] / "AGENTS.md"
        if not contract.is_file():
            raise RuntimeError("B契約未固定。親によるP2確定待ち")
        shutil.copy2(contract, root / "AGENTS.md")
        hashes["AGENTS.md"] = sha(contract)
        if task["repo"] == "agent_crew":
            skill_dir = root / ".agents/skills/fable-class"
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
            fixed_skill = HERE / "b-contract/agent_crew/.agents/skills/fable-class"
            if not (fixed_skill / "SKILL.md").is_file():
                raise RuntimeError("B skill未固定。親によるP2確定待ち")
            shutil.copytree(fixed_skill, skill_dir)
            for file in skill_dir.rglob("*"):
                if file.is_file():
                    hashes[str(file.relative_to(root))] = sha(file)
        elif task["repo"] == "wealth_advisor":
            source = HERE / "b-contract/wealth_advisor/.agents/skills/wealth-advisor/SKILL.md"
            destination = root / ".agents/skills/wealth-advisor/SKILL.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            hashes[str(destination.relative_to(root))] = sha(destination)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.name=P5 Fixture", "-c", "user.email=p5-fixture@example.invalid",
                    "commit", "-qm", "P0 fixture"], cwd=root, check=True, capture_output=True)
    return root, task, hashes


def prompt_for(task):
    lines = [
        "この隔離fixture内で次の課題を調査・検証してください。日本語で報告してください。",
        f"課題ID: {task['id']} / {task['kind']}",
        f"作業: {task['work']}",
        f"受入条件: {task['accept']}",
        "fixture以外の実環境、外部サービス、認証、金融データへアクセスしないでください。",
        "既存のテスト・契約を用い、必要ならfixture内だけ編集してください。",
        "完了時に目的、実施内容、検証コマンドと結果、未完、次の一手を明記してください。",
    ]
    if task["id"] == "C6":
        lines.append("表示台帳はmigration-progress/state.jsonの合成fixtureです。queueや元repoを変更しないでください。")
    return "\n".join(lines) + "\n"


def safe_events(raw, destination):
    """生イベントを保存せず、秘密混入し得る本文・コマンドを落とす。"""
    usage = {}
    types = {}
    tool_seconds = UNKNOWN
    commands = []
    errors = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type", UNKNOWN)
        types[kind] = types.get(kind, 0) + 1
        if kind == "turn.completed":
            usage = event.get("usage", {})
        if kind == "error":
            errors.append(str(event.get("message", ""))[:200])
        item = event.get("item") or {}
        if item.get("type") == "command_execution" and kind in ("item.started", "item.completed"):
            command = str(item.get("command", ""))
            # 監査用に安全な非機密コマンドのみ本文を保持する。
            safe = bool(re.fullmatch(r"[A-Za-z0-9_./'\"= :;|&()\[\],+*?\\-]+", command)) and not re.search(
                r"(?i)(token|secret|password|credential|api.key|auth|/Users/|\.env|curl|wget|ssh)", command)
            commands.append({"event": kind, "command": command if safe else "redacted",
                             "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                             "exit_code": item.get("exit_code", UNKNOWN),
                             "output_sha256": hashlib.sha256(str(item.get("aggregated_output", "")).encode()).hexdigest(),
                             "potentially_sensitive": not safe})
    cleaned = {"event_types": types, "usage": usage, "errors": errors,
               "tool_seconds": tool_seconds, "commands": commands}
    save(destination, cleaned)
    return cleaned


def limited_env(root):
    temporary = root / ".benchmark-tmp"
    temporary.mkdir(exist_ok=True)
    keys = ("PATH", "LANG", "LC_ALL", "COLUMNS", "LINES", "SYSTEMROOT")
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env.update({"TMPDIR": str(temporary), "TMP": str(temporary), "TEMP": str(temporary),
                "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull})
    return env


def stop_group(pgid):
    if pgid is None:
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def terminate_handler(_signum, _frame):
    stop_group(ACTIVE_GROUP)
    raise SystemExit(143)


def execute_group(command, root, env, timeout, input_text=None):
    global ACTIVE_GROUP
    process = subprocess.Popen(command, text=True, stdin=subprocess.PIPE if input_text is not None else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=root, env=env,
                               start_new_session=True)
    ACTIVE_GROUP = process.pid
    active_file = root / ".benchmark-active-pgid"
    active_file.write_text(str(process.pid), encoding="ascii")
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        # 親が正常終了しても同一groupの孫が残ることを許さない。
        stop_group(process.pid)
        return process.returncode, stdout, stderr
    except subprocess.TimeoutExpired as exc:
        stop_group(process.pid)
        process.communicate()
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        return "timeout", stdout, "timeout"
    finally:
        ACTIVE_GROUP = None
        active_file.unlink(missing_ok=True)


def validate(task, root, timeout=VALIDATION_TIMEOUT_SECONDS, c6_state_before=None, c6_readonly=None):
    if task["id"] == "C4":
        cmd = ["git", "diff", "--check"]
    else:
        cmd = task["validate"].split()
    if task["id"] == "C6":
        validator = HERE / "validate_c6.py"
        destination = root / "validate_c6.py"
        if os.path.lexists(destination):
            raise RuntimeError(f"C6 validatorを既存ファイルへ上書きしません: {destination}")
        shutil.copy2(validator, destination)
        cmd.extend(["--state-before-sha256", c6_state_before,
                    "--progress-sha256", c6_readonly["progress"],
                    "--readme-sha256", c6_readonly["readme"]])
    sandbox = sandbox_command(root, task, cmd)
    exit_code, stdout, stderr = execute_group(sandbox, root, limited_env(root), timeout)
    result = {"command": cmd, "sandbox": "codex sandbox p5_fixture read-only+fixture-write/no-network",
              "exit_code": exit_code, "stdout_tail": stdout[-2500:], "stderr_tail": stderr[-2500:]}
    return result


def run(args):
    signal.signal(signal.SIGTERM, terminate_handler)
    version = subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    if version != "codex-cli 0.155.1":
        raise RuntimeError(f"CLI版不一致: {version}")
    root, task, hashes = prepare(args.task, args.condition, args.repeat, args.campaign)
    prompt = prompt_for(task)
    prompt_path = root / ".benchmark-prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    before = {str(p.relative_to(root)): sha(p) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
    c6_state_before = sha(root / "migration-progress/state.json") if args.task == "C6" else None
    c6_readonly = ({"progress": sha(root / "migration-progress/progress.py"),
                    "readme": sha(root / "migration-progress/README.md")} if args.task == "C6" else None)
    guard_before = host_guard() if args.task == "C6" else None
    out = root / ".benchmark-answer.txt"
    command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
               "--skip-git-repo-check", "--json",
               "--model", "gpt-6-astra", "-c", "model_reasoning_effort=\"medium\"",
               "-c", "model_provider=\"openai\"", "-c", "features.hooks=false",
               "-c", "default_permissions=\"p5_fixture\"",
               *sum((["-c", value] for value in [
                   'permissions.p5_fixture.description="P5 fixture"',
                   'permissions.p5_fixture.extends=":read-only"',
                   'permissions.p5_fixture.network.enabled=false',
                   *[f'permissions.p5_fixture.filesystem.{path}="write"' for path in permission_policy(root, task)]
               ]), []),
               "-C", str(root), "-o", str(out), "-"]
    child_env = {key: value for key, value in os.environ.items()
                 if not re.search(r"(?i)(token|secret|password|credential|api.?key|authorization)", key)}
    started = stamp()
    tick = time.monotonic()
    deadline = getattr(args, "deadline_epoch", None)
    remaining = deadline - time.time() if deadline is not None else 360
    if remaining < 70:
        raise RuntimeError("campaign残時間不足。runを開始しません")
    cli_timeout = min(CLI_TIMEOUT_SECONDS, remaining - 60)
    cli_exit, stdout, stderr_raw = execute_group(command, root, child_env, cli_timeout, prompt)
    events = safe_events(stdout, root / ".benchmark-events.json")
    stderr = re.sub(r"/Users/[^/\s]+", "~/", stderr_raw[-1000:])
    guard_after = host_guard() if args.task == "C6" else None
    if args.task == "C6":
        before["validate_c6.py"] = sha(HERE / "validate_c6.py")
        hashes["comparison-v2.json"] = sha(HERE / "comparison-v2.json")
        hashes["validate_c6.py"] = before["validate_c6.py"]
    remaining = deadline - time.time() if deadline is not None else 60
    accepted = accepted_c6_snapshot(root) if args.task == "C6" else root
    validation = validate(task, accepted, max(1, min(VALIDATION_TIMEOUT_SECONDS, remaining - 5)),
                          c6_state_before, c6_readonly)
    c6_validator_consistent = True
    if args.task == "C6" and validation["exit_code"] == 0:
        try:
            reported = json.loads(validation["stdout_tail"])["state_sha256"]
            current = sha(accepted / "migration-progress/state.json")
            structure = load(accepted / "migration-progress/state.json")
            c6_validator_consistent = (reported == current and structure.get("schema") == 1 and
                                       set(structure.get("tasks", {})) == {f"P{i}" for i in range(8)})
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            c6_validator_consistent = False
    after = {str(p.relative_to(root)): sha(p) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and not p.name.startswith(".benchmark-")}
    modified = sorted(k for k in set(before) | set(after) if not k.startswith(".benchmark-") and before.get(k) != after.get(k))
    allowed = ({"migration-progress/state.json"} if task["id"] == "C6"
               else set(task["input"] + task["fixture"]))
    scope = [k for k in modified if k not in allowed and k != "validate_c6.py" and
             (args.task == "C6" or not re.fullmatch(r"docs/plans/[^/]+\.md", k))]
    answer = out.read_text(encoding="utf-8") if out.exists() else ""
    handoff = all(word in answer for word in ("目的", "検証", "次"))
    result = {
        "campaign": args.campaign, "fingerprint": args.fingerprint,
        "task_id": args.task, "condition": args.condition, "repeat": args.repeat,
        "started_at": started, "ended_at": stamp(), "wall_seconds": round(time.monotonic() - tick, 3),
        "cli_version": version, "model_requested": "gpt-6-astra", "effort_requested": "medium",
        "provider_requested": "openai", "provider_observed": UNKNOWN,
        "model_observed": UNKNOWN, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "input_hashes": hashes, "cli_exit": cli_exit, "validation": validation,
        "modified_paths": modified, "scope_violations": scope,
        "handoff_keyword_check": handoff, "handoff_success": "pending_independent_review",
        "approval_count": UNKNOWN, "approval_wait_seconds": UNKNOWN,
        "llm_seconds": UNKNOWN, "tool_seconds": events["tool_seconds"],
        "input_tokens": events["usage"].get("input_tokens", UNKNOWN),
        "output_tokens": events["usage"].get("output_tokens", UNKNOWN),
        "cost_usd": UNKNOWN, "rework_count": UNKNOWN, "review_findings": "not_reviewed",
        "stderr_tail": stderr, "answer_sha256": hashlib.sha256(answer.encode()).hexdigest() if answer else None,
    }
    result["host_guard"] = {"before": guard_before, "after": guard_after,
                            "unchanged": guard_before == guard_after} if args.task == "C6" else None
    result["c6_validator_consistent"] = c6_validator_consistent if args.task == "C6" else None
    result["accepted_state_sha256"] = sha(accepted / "migration-progress/state.json") if args.task == "C6" else None
    result["pass_preliminary"] = preliminary_pass(
        cli_exit, validation["exit_code"], scope, handoff,
        args.task != "C6" or (guard_before == guard_after and c6_validator_consistent),
    )
    save(root / ".benchmark-result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=sorted(ALLOWED))
    parser.add_argument("condition", choices=["A", "B"])
    parser.add_argument("repeat", type=int, choices=[1, 2])
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--deadline-epoch", type=float)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
