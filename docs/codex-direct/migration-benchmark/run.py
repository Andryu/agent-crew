#!/usr/bin/env python3
"""P5の固定snapshotを隔離して実行し、再現可能な非機密証跡を残す。"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager

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

KNOWN_EVENT_TYPES = {
    "thread.started", "turn.started", "item.started", "item.updated",
    "item.completed", "turn.completed", "turn.failed", "error",
}
ITEM_EVENT_TYPES = {"item.started", "item.updated", "item.completed"}
ALLOWED_NON_TOOL_ITEMS = {
    "agent_message", "message", "reasoning", "file_change", "todo_list_update",
    "plan_update", "context_compaction",
}
DISALLOWED_TOOL_ITEMS = {
    "mcp_tool_call", "web_search", "web_search_call", "computer_call",
    "browser_action", "local_shell", "tool_call",
}
NETWORK_COMMAND_RE = re.compile(
    r"(?i)(?:\bcurl\b|\bwget\b|\bssh\b|\bscp\b|\bsftp\b|\brsync\b|"
    r"\bnc\b|\bnetcat\b|\bftp\b|\bping\b|\bgit\s+(?:clone|fetch|pull|push)|"
    r"https?://|ftp://|/dev/(?:tcp|udp)|\bsocket\b|\burllib\b|\brequests\b|"
    r"\bhttp\.client\b|\bcreate_connection\b)"
)
SECRET_COMMAND_RE = re.compile(
    r"(?i)(?:token|secret|password|passwd|credential|api[._-]?key|authorization|"
    r"bearer|cookie|private[._-]?key|\.env|gh\s+auth)"
)
USER_PATH_RE = re.compile(r"(?i)(?:^|[\s\"'=])(?:/Users/|/home/|[A-Z]:\\Users\\)")
INLINE_CODE_RE = re.compile(
    r"(?i)(?:^|[;&|]\s*|\s)(?:python(?:3(?:\.\d+)?)?|node|ruby|perl|php|bash|sh|zsh)"
    r"(?:\s+[^;&|]*)?\s(?:-c|-e)\s"
)
SIMPLE_COMMANDS = {"cat", "head", "ls", "pwd", "rg", "tail", "test", "wc"}
GIT_READ_COMMANDS = {"diff", "ls-files", "rev-parse", "show", "status"}
PYTHON_MODULES = {"py_compile", "pytest", "unittest"}
PYTHON_SCRIPTS = {
    "migration-progress/progress.py", "scripts/check_operational_readiness.py",
    "scripts/codex_hook_state.py", "scripts/install_crew_hooks.py", "validate_c6.py",
}
SHELL_METATOKENS = {"|", "||", "&", "&&", ";", "<", ">", "2>", "2>&1"}


@contextmanager
def private_umask():
    """run単位で秘密artifactのデフォルト権限を0600/0700へ固定する。"""
    previous = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_parent(path):
    parent = Path(path).parent
    for candidate in (parent, *parent.parents):
        if os.path.lexists(candidate) and candidate.is_symlink():
            raise RuntimeError(f"artifact parentにsymlinkがあります: {candidate}")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink():
        raise RuntimeError(f"artifact parentにsymlinkがあります: {parent}")
    parent.chmod(0o700)
    return parent


def _write_private(path, text, mode=0o600):
    """symlinkを追従せず、private artifactを指定modeで保存する。"""
    path = Path(path)
    _private_parent(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        fd = None
    finally:
        if fd is not None:
            os.close(fd)
    path.chmod(mode)


def save(path, value):
    _write_private(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


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
    accepted.mkdir(parents=True, mode=0o700)
    accepted.chmod(0o700)
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


def preliminary_pass(cli_exit, validation_exit, scope, handoff, guard_unchanged=True,
                     event_audit_pass=False):
    return (cli_exit == 0 and validation_exit == 0 and not scope and handoff and
            guard_unchanged and event_audit_pass)


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
    subprocess.run(["git", "-c", "user.name=P5 Fixture", "-c", "user.email=p5-fixture@localhost",
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


def _count(mapping, value):
    value = value if isinstance(value, str) and value else UNKNOWN
    mapping[value] = mapping.get(value, 0) + 1


def _command_safety(command):
    """本文を残してよいcommandかと、監査上の理由を返す。"""
    if not isinstance(command, str) or not command.strip():
        return False, "missing_command"
    if len(command) > 8192 or any(not character.isprintable() for character in command):
        return False, "command_redacted"
    if NETWORK_COMMAND_RE.search(command):
        return False, "network_command"
    if SECRET_COMMAND_RE.search(command):
        return False, "secret_command"
    if USER_PATH_RE.search(command):
        return False, "user_absolute_path"
    if INLINE_CODE_RE.search(command):
        return False, "inline_code_unclassified"
    # shell演算子・展開はquote内外を問わず許可しない。誤拒否よりfail-open回避を優先する。
    if re.search(r"[;|&<>`$\r\n]", command):
        return False, "shell_syntax_unclassified"
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False, "command_parse_error"
    if not tokens:
        return False, "missing_command"
    if (any(token in SHELL_METATOKENS or token.startswith((">", "<")) or
            "$(" in token or "`" in token for token in tokens) or
            "/" in tokens[0]):
        return False, "command_form_unclassified"
    executable = tokens[0]
    if any(token.startswith("/") or re.search(r"(?:^|/)\.\.(?:/|$)", token)
           for token in tokens[1:]):
        return False, "absolute_path_unclassified"
    if executable in SIMPLE_COMMANDS:
        if executable == "rg" and any(token == "--pre" or token.startswith("--pre=")
                                      for token in tokens[1:]):
            return False, "rg_command_unclassified"
        return True, None
    if executable == "git":
        index = 1
        if index < len(tokens) and tokens[index] == "-C":
            if index + 2 >= len(tokens) or tokens[index + 1].startswith("/"):
                return False, "git_command_unclassified"
            index += 2
        if index >= len(tokens) or tokens[index] not in GIT_READ_COMMANDS:
            return False, "git_command_unclassified"
        if any(token in {"--ext-diff", "--textconv", "--exec-path", "-c", "--config-env"}
               or token.startswith(("--exec-path=", "--config-env=")) for token in tokens[1:]):
            return False, "git_command_unclassified"
        return True, None
    if executable == "python3.12":
        arguments = tokens[1:]
        while arguments and arguments[0] in {"-B", "-I", "-u"}:
            arguments = arguments[1:]
        if len(arguments) >= 2 and arguments[0] == "-m" and arguments[1] in PYTHON_MODULES:
            return True, None
        if arguments and arguments[0] in PYTHON_SCRIPTS:
            return True, None
        return False, "python_command_unclassified"
    return False, "executable_unclassified"


def safe_events(raw, destination, expected_cwd=None):
    """生JSONLを保存せず、全行を分類した非機密のevent監査を作る。"""
    usage = {}
    event_types = {}
    item_types = {}
    item_categories = {}
    tool_seconds = UNKNOWN
    commands = []
    errors = []
    unknown_events = []
    unknown_items = []
    violations = []
    malformed_lines = 0
    parsed_lines = 0
    lines = raw.splitlines()
    tool_lifecycle = {}

    def violation(reason, severity="fail"):
        violations.append({"reason": reason, "severity": severity})

    def register_tool(item_id, item_type, kind, status, line_number):
        if not isinstance(item_id, str) or not item_id.strip():
            violation("missing_tool_item_id", "unknown")
            item_id = f"missing:{line_number}:{kind}:{item_type}"
        state = tool_lifecycle.setdefault(item_id, {
            "type": item_type, "started": 0, "updated": 0, "completed": 0,
        })
        if state["type"] != item_type:
            violation("tool_item_type_mismatch", "fail")
        if status == "failed":
            violation("tool_reported_failed", "fail")
        if kind == "item.started":
            if state["started"] or state["completed"]:
                violation("tool_lifecycle_order", "unknown")
            state["started"] += 1
        elif kind == "item.updated":
            if state["started"] != 1 or state["completed"]:
                violation("tool_lifecycle_order", "unknown")
            state["updated"] += 1
        elif kind == "item.completed":
            if state["started"] != 1 or state["completed"]:
                violation("tool_lifecycle_order", "unknown")
            state["completed"] += 1
        return item_id

    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            malformed_lines += 1
            violation("malformed_json", "fail")
            continue
        if not isinstance(event, dict):
            malformed_lines += 1
            violation("event_not_object", "fail")
            continue
        parsed_lines += 1
        kind = event.get("type", UNKNOWN)
        if not isinstance(kind, str) or not kind:
            kind = UNKNOWN
        _count(event_types, kind)
        if kind not in KNOWN_EVENT_TYPES:
            unknown_events.append(kind)
            violation("unknown_event_type", "unknown")
        if kind == "turn.completed":
            candidate = event.get("usage", {})
            usage = candidate if isinstance(candidate, dict) else {}
            if not isinstance(candidate, dict):
                violation("invalid_usage", "unknown")
        if kind in ("error", "turn.failed"):
            message = event.get("message", "")
            # 生messageは秘密を含み得るため保存せず、hashだけを残す。
            errors.append({"event": kind, "message_sha256": hashlib.sha256(
                str(message).encode("utf-8", errors="replace")).hexdigest()})
            violation(kind, "fail")

        if kind not in ITEM_EVENT_TYPES:
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            _count(item_types, UNKNOWN)
            _count(item_categories, "unknown")
            unknown_items.append(UNKNOWN)
            violation("missing_item", "unknown")
            continue
        item_type = item.get("type", UNKNOWN)
        if not isinstance(item_type, str) or not item_type:
            item_type = UNKNOWN
        _count(item_types, item_type)

        if item_type == "command_execution":
            _count(item_categories, "tool")
            command = item.get("command")
            safe, safety_reason = _command_safety(command)
            command_text = command if isinstance(command, str) else str(command or "")
            output = item.get("aggregated_output")
            output_hash = (hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest()
                           if isinstance(output, str) else UNKNOWN)
            exit_code = item.get("exit_code", UNKNOWN)
            item_id = item.get("id")
            status = item.get("status")
            item_id = register_tool(item_id, item_type, kind, status, line_number)
            event_cwd = item.get("cwd")
            if isinstance(event_cwd, str) and expected_cwd is not None:
                try:
                    cwd_path = Path(event_cwd)
                    if not cwd_path.is_absolute():
                        cwd_path = Path(expected_cwd) / cwd_path
                    audited_cwd = str(cwd_path.resolve().relative_to(Path(expected_cwd).resolve())) or "."
                    cwd_source = "event"
                except (OSError, ValueError):
                    audited_cwd = "outside_run_root"
                    cwd_source = "event"
                    violation("command_cwd_outside_run_root", "fail")
            else:
                audited_cwd = UNKNOWN
                cwd_source = "missing"
                violation("missing_command_cwd", "unknown")
            commands.append({
                "item_id_sha256": hashlib.sha256(str(item_id).encode()).hexdigest(),
                "event": kind,
                "command": command_text if safe else "redacted",
                "command_sha256": hashlib.sha256(command_text.encode("utf-8", errors="replace")).hexdigest(),
                "exit_code": exit_code,
                "output_sha256": output_hash,
                "cwd": audited_cwd,
                "cwd_source": cwd_source,
                "status": status if isinstance(status, str) else UNKNOWN,
                "potentially_sensitive": not safe,
            })
            if not safe:
                violation(safety_reason or "command_redacted", "fail")
            # started/updatedではexit_codeが未確定でもよい。completedだけは必須情報とする。
            if kind == "item.completed":
                if "exit_code" not in item or type(item.get("exit_code")) is not int:
                    violation("missing_command_exit_code", "fail")
                elif item["exit_code"] != 0:
                    violation("command_failed", "fail")
                if not isinstance(output, str):
                    violation("missing_command_output", "unknown")
                if status != "completed":
                    violation("command_not_completed", "fail" if status == "failed" else "unknown")
            continue

        if item_type == "file_change":
            _count(item_categories, "tool")
            status = item.get("status")
            register_tool(item.get("id"), item_type, kind, status, line_number)
            if kind == "item.completed":
                status = item.get("status")
                if status != "completed":
                    violation("file_change_not_completed", "fail" if status == "failed" else "unknown")
            continue

        if item_type in ALLOWED_NON_TOOL_ITEMS:
            _count(item_categories, "non_tool")
            continue
        _count(item_categories, "unknown")
        unknown_items.append(item_type)
        severity = "fail" if item_type in DISALLOWED_TOOL_ITEMS or "tool" in item_type.lower() else "unknown"
        violation("disallowed_or_unknown_item", severity)

    for state in tool_lifecycle.values():
        if state["started"] != 1 or state["completed"] != 1:
            violation("unpaired_tool_event", "unknown")
    if parsed_lines == 0:
        violation("no_parsed_events", "fail")
    if event_types.get("turn.completed", 0) != 1:
        violation("missing_or_duplicate_turn_completed", "fail")
    hard_failures = [entry for entry in violations if entry["severity"] == "fail"]
    audit_status = "fail" if hard_failures else ("unknown" if violations else "pass")
    event_audit = {
        "status": audit_status,
        "passed": audit_status == "pass",
        "total_lines": len(lines),
        "parsed_lines": parsed_lines,
        "malformed_lines": malformed_lines,
        "event_types": event_types,
        "item_types": item_types,
        "item_categories": item_categories,
        "unknown_event_types": sorted(set(unknown_events)),
        "unknown_item_types": sorted(set(unknown_items)),
        "violations": violations,
    }
    safety_pass = audit_status == "pass"
    cleaned = {
        "event_audit": event_audit,
        "safety_gate": {"status": "pass" if safety_pass else "fail", "passed": safety_pass,
                        "reasons": sorted(set(entry["reason"] for entry in violations))},
        "event_types": event_types,
        "item_types": item_types,
        "usage": usage,
        "errors": errors,
        "tool_seconds": tool_seconds,
        "commands": commands,
    }
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
    _write_private(active_file, str(process.pid), mode=0o600)
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


def _run(args):
    signal.signal(signal.SIGTERM, terminate_handler)
    version = subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    if version != "codex-cli 0.155.1":
        raise RuntimeError(f"CLI版不一致: {version}")
    root, task, hashes = prepare(args.task, args.condition, args.repeat, args.campaign)
    prompt = prompt_for(task)
    prompt_path = root / ".benchmark-prompt.txt"
    _write_private(prompt_path, prompt)
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
    events = safe_events(stdout, root / ".benchmark-events.json", expected_cwd=root)
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
    event_audit_pass = (events["event_audit"]["status"] == "pass" and
                        events["safety_gate"]["status"] == "pass")
    result["event_audit"] = events["event_audit"]
    result["safety_gate"] = events["safety_gate"]
    result["pass_preliminary"] = preliminary_pass(
        cli_exit, validation["exit_code"], scope, handoff,
        args.task != "C6" or (guard_before == guard_after and c6_validator_consistent),
        event_audit_pass,
    )
    save(root / ".benchmark-result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run(args):
    """private artifactのumaskをrun全体へ適用し、終了時に呼び出し元へ戻す。"""
    with private_umask():
        return _run(args)


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
