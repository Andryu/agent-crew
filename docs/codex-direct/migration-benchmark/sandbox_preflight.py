#!/usr/bin/env python3
"""P5 fixture 用の Codex sandbox 境界を、モデル呼出しなしで検証する。"""

import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid

import run as runner


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
EXPECTED_VERSION = "codex-cli 0.155.1"
DENIAL_MARKERS = (
    "operation not permitted",
    "permission denied",
    "read-only file system",
    "sandbox denied",
    "sandbox violation",
    "network is disabled",
    "network disabled",
    "not allowed",
)
INFRASTRUCTURE_MARKERS = (
    "sandbox-exec: sandbox_apply",
    "sandbox initialization failed",
    "unknown permission profile",
    "failed to parse",
    "invalid configuration",
    "invalid config",
    "no such file or directory",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tail(value, limit=2000):
    return value[-limit:]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify_denial(exit_code, stdout, stderr):
    """拒否を、設定・CLI障害とは区別して保守的に分類する。"""
    combined = (stdout + "\n" + stderr).lower()
    if exit_code == 0:
        return "unexpected_success"
    if any(marker in combined for marker in INFRASTRUCTURE_MARKERS):
        return "preflight_error"
    if any(marker in combined for marker in DENIAL_MARKERS):
        return "sandbox_denied"
    return "unexpected_failure"


def sandbox_command(fixture, command):
    """run.pyと同じC6最小権限policyを用いる。"""
    return runner.sandbox_command(fixture, runner.c6_task(), command)


def isolated_environment(root, fixture):
    """Codex の初期化も実 HOME/.codex を参照・更新しないよう隔離する。"""
    home = root / "home"
    tmp = fixture / "tmp"
    for directory in (home, tmp):
        directory.mkdir()
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT"}}
    env.update({
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "TMP": str(tmp),
        "TEMP": str(tmp),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def run_case(name, fixture, command, expected, env):
    invocation = sandbox_command(fixture, command)
    try:
        completed = subprocess.run(invocation, text=True, capture_output=True, env=env,
                                   cwd=fixture, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "name": name, "expected": expected, "outcome": "preflight_error",
            "exit_code": "timeout" if isinstance(error, subprocess.TimeoutExpired) else "spawn_error",
            "command": command, "used_legacy_sandbox_flag": "--sandbox" in invocation,
            "stdout_tail": tail(getattr(error, "stdout", "") or ""),
            "stderr_tail": str(error),
        }
    if expected == "allow":
        outcome = "allowed" if completed.returncode == 0 else "preflight_error"
    else:
        outcome = classify_denial(completed.returncode, completed.stdout, completed.stderr)
    return {
        "name": name,
        "expected": expected,
        "outcome": outcome,
        "exit_code": completed.returncode,
        "command": command,
        "used_legacy_sandbox_flag": "--sandbox" in invocation,
        "stdout_tail": tail(completed.stdout),
        "stderr_tail": tail(completed.stderr),
    }


def write_command(path, contents):
    return ["python3.12", "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')",
            str(path), contents]


def case_matches_expected(case):
    """許可試験と拒否試験は期待する outcome が異なる。"""
    return ((case["expected"] == "allow" and case["outcome"] == "allowed") or
            (case["expected"] == "deny" and case["outcome"] == "sandbox_denied"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true",
                        help="成功・失敗を出力後、生成した一時rootの削除を試みる")
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="agent-crew-p5-sandbox-preflight-", dir="/private/tmp"))
    fixture = root / "fixture"
    fixture.mkdir()
    sibling = root / "outside-same-private-tmp.txt"
    repository_target = REPOSITORY / f".p5-sandbox-preflight-{uuid.uuid4().hex}.txt"
    fixture_target = fixture / "migration-progress/state.json"
    fixture_target.parent.mkdir()
    snapshot = HERE.parent / "migration-baseline/snapshot/agent_crew/migration-progress"
    shutil.copy2(snapshot / "progress.py", fixture_target.parent / "progress.py")
    shutil.copy2(snapshot / "README.md", fixture_target.parent / "README.md")
    shutil.copy2(HERE.parent / "migration-baseline/fixtures/board-state.json", fixture_target)
    before_inputs = {name: digest(fixture_target.parent / name) for name in ("progress.py", "README.md")}
    before_state = digest(fixture_target)
    env = isolated_environment(root, fixture)
    version = subprocess.run(["codex", "--version"], text=True, capture_output=True,
                             check=False, env=env).stdout.strip()
    if version != EXPECTED_VERSION:
        raise SystemExit(f"CLI版不一致: expected {EXPECTED_VERSION}, observed {version or 'unknown'}")
    assert (REPOSITORY / "AGENTS.md").is_file(), "preflight rootがagent-crewではありません"
    report = {"schema": 1, "started_at": utc_now(), "cli_version": version,
              "root": str(root), "fixture": str(fixture), "cases": []}

    listener = None
    try:
        ready = run_case("sandbox_ready", fixture, ["/usr/bin/true"], "allow", env)
        report["cases"].append(ready)
        report["sandbox_initialized"] = ready["outcome"] == "allowed"
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        cases = (
            ("fixture_state_write", ["python3.12", "-B", "migration-progress/progress.py", "set",
                                      "--task", "P0", "--status", "検証中", "--current", "preflight",
                                      "--next", "read", "--blocker", "なし"], "allow"),
            ("fixture_state_read", ["python3.12", "-B", "migration-progress/progress.py", "--once"], "allow"),
            ("same_private_tmp_write", write_command(sibling, "must-not-write\n"), "deny"),
            ("repository_root_write", write_command(repository_target, "must-not-write\n"), "deny"),
            ("network_connect", ["python3.12", "-c",
                                  f"import socket; socket.create_connection(('127.0.0.1', {port}), timeout=1)"], "deny"),
        )
        if report["sandbox_initialized"]:
            report["cases"].extend(run_case(name, fixture, command, expected, env)
                                   for name, command, expected in cases)
        else:
            # sandbox-exec の初期化失敗を個別の保護拒否と取り違えない。
            report["cases"].extend({
                "name": name, "expected": expected, "outcome": "not_run_preflight_error",
                "exit_code": "not_run", "command": command,
                "used_legacy_sandbox_flag": False,
                "stdout_tail": "", "stderr_tail": "sandbox initialization failed",
            } for name, command, expected in cases)

        listener.close()
        listener = None
        fixture_ok = (fixture_target.is_file() and digest(fixture_target) != before_state and
                      all(digest(fixture_target.parent / name) == value for name, value in before_inputs.items()) and
                      not list(fixture_target.parent.glob(".state-*")))
        outside_absent = not sibling.exists() and not repository_target.exists()
        report["postconditions"] = {
            "fixture_write_observed": fixture_ok,
            "forbidden_targets_absent": outside_absent,
        }
        report["passed"] = (report["sandbox_initialized"] and fixture_ok and outside_absent and
                            all(case_matches_expected(case) for case in report["cases"]))
        report["ended_at"] = utc_now()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["passed"]:
            raise SystemExit(1)
    finally:
        if listener is not None:
            listener.close()
        # Codex sandbox が作る管理用mountは削除を拒むことがあるため、通常は監査証跡を残す。
        # --cleanup時も、生成元を厳密に限定した mkdtemp root だけを対象にする。
        if args.cleanup:
            try:
                shutil.rmtree(root)
            except OSError as error:
                print(f"cleanup_failed: {root}: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
