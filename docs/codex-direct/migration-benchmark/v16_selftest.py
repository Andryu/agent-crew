#!/usr/bin/env python3
"""v16 schema2、secret、sed、probe ledgerのmodel不要な故障注入。"""

import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import tempfile

import probe_v16
import batch
import run


def tool_env(expected, root):
    return {**expected, "CODEX_CI": "1", "CODEX_PERMISSION_PROFILE": "p5_fixture",
            "CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1",
            "CODEX_SESSION_ID": "abcdefab-cdef-7abc-8def-abcdefabcdef",
            "CODEX_THREAD_ID": "abcdefab-cdef-7abc-8def-abcdefabcdee", "CODEX_VERSION": "0.160.0",
            "COLORTERM": "", "GH_PAGER": "cat", "GIT_PAGER": "cat", "LC_CTYPE": "C.UTF-8",
            "LOGNAME": pwd.getpwuid(os.getuid()).pw_name, "NO_COLOR": "1", "OLDPWD": str(root),
            "PAGER": "cat", "PWD": str(root), "SHLVL": "0", "TERM": "dumb", "_": run.PYTHON_EXECUTABLE}


def event_stream(output):
    command = run.ENV_CANARY_COMMAND
    values = [{"type": "thread.started", "thread_id": "synthetic"}, {"type": "turn.started"},
              {"type": "item.started", "item": {"type": "command_execution", "id": "canary",
                  "command": command, "status": "in_progress"}},
              {"type": "item.completed", "item": {"type": "command_execution", "id": "canary",
                  "command": command, "status": "completed", "exit_code": 0, "aggregated_output": output}},
              {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0,
                  "output_tokens": 1}}]
    return "\n".join(json.dumps(item) for item in values)


def observe(root, environment):
    return subprocess.run(shlex.split(run.ENV_CANARY_COMMAND), cwd=root, env=environment,
                          text=True, capture_output=True)


def canary_tests(base):
    root = base / "fixture"
    root.mkdir()
    run.install_env_canary(root, "v16-test")
    expected = run.limited_env(root, "v16-test")
    synthetic = "SYNTHETIC_P5_SECRET_v16_123456"
    environment = tool_env(expected, root)
    result = observe(root, environment)
    assert result.returncode == 0 and result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["schema"] == 2 and payload["aggregate_match"]
    assert payload["required_checks"]["P5_RUN_TOKEN"] == {"present": True, "expected_match": True}
    audit = run.safe_events(event_stream(result.stdout), expected_cwd=root, expected_env=expected)
    assert audit["env_canary_evidence"]["passed"]
    for key in ("PATH", "HOME", "P5_RUN_TOKEN"):
        changed = {**environment, key: synthetic}
        observed = observe(root, changed)
        parsed = json.loads(observed.stdout)
        assert parsed["required_checks"][key] == {"present": True, "expected_match": False}
        assert not run.safe_events(event_stream(observed.stdout), expected_cwd=root,
                                   expected_env=expected)["env_canary_evidence"]["passed"]
        assert synthetic not in observed.stdout + observed.stderr
    changed = {**environment, synthetic: synthetic}
    observed = observe(root, changed)
    parsed = json.loads(observed.stdout)
    assert parsed["unknown_count"] == 1 and parsed["allowed_set_match"] is False
    assert synthetic not in observed.stdout + observed.stderr
    for key in ("PATH", "P5_RUN_TOKEN"):
        missing = dict(environment)
        del missing[key]
        parsed = json.loads(observe(root, missing).stdout)
        assert parsed["required_checks"][key] == {"present": False, "expected_match": False}
    empty = {**environment, "PATH": ""}
    assert json.loads(observe(root, empty).stdout)["required_checks"]["PATH"] == {"present": True, "expected_match": False}
    for mutation in (lambda x: {**x, "schema": 1}, lambda x: {**x, "extra": True},
                     lambda x: {**x, "unknown_count": True}, lambda x: {**x, "aggregate_match": False},
                     lambda x: {**x, "required_checks": {**x["required_checks"], "PATH": {"present": 1, "expected_match": True}}}):
        broken = json.dumps(mutation(payload))
        assert not run.safe_events(event_stream(broken), expected_cwd=root,
                                   expected_env=expected)["env_canary_evidence"]["passed"]
    duplicate = result.stdout.strip()[:-1] + ',"schema":2}'
    assert not run.safe_events(event_stream(duplicate), expected_cwd=root,
                               expected_env=expected)["env_canary_evidence"]["passed"]
    run._write_private(root / run.ENV_EXPECTED_NAME, synthetic + " invalid JSON")
    exception = observe(root, environment)
    assert exception.returncode == 2 and exception.stderr.strip() == "P5_CANARY_ERROR"
    public = json.dumps({"raw": event_stream(result.stdout), "events": audit,
                         "summary": audit["env_canary_evidence"], "diagnostics": audit["diagnostics"]})
    assert synthetic not in public + result.stdout + result.stderr + exception.stdout + exception.stderr
    print("v16 schema2/secret: PASS")


def sed_tests(base):
    root = base / "sed"
    root.mkdir()
    (root / "file.txt").write_text("one\ntwo\n")
    assert run.command_attempts("/usr/bin/sed -n '1,2p' file.txt", root) == []
    assert run.command_attempts("/usr/bin/sed -n 1p file.txt", root) == []
    outside = base / "outside.txt"
    outside.write_text("outside")
    (root / "link.txt").symlink_to(outside)
    for value in ("-i 1p file.txt", "-e 1p file.txt", "-f file.txt file.txt", "-n 1e file.txt",
                  "-n 1w file.txt", "-n 1r file.txt", "-n '1p;2p' file.txt", "-n 1p link.txt",
                  "-n 1p ../outside.txt", "-n 1p -option", "-n 1p '$HOME/file.txt'"):
        assert run.command_attempts("/usr/bin/sed " + value, root), value
    assert run.command_attempts("/usr/bin/sed -n 1p file.txt; unknown_command", root)
    print("v16 sed grammar: PASS")


def budget_tests(base):
    path = base / "ledger" / "probe-ledger.json"
    first = probe_v16.reserve("a" * 64, path)
    probe_v16.finish(first["id"], False, "auth", path)
    second = probe_v16.reserve("b" * 64, path)
    probe_v16.finish(second["id"], True, "pass", path)
    assert probe_v16.require_final_probe("b" * 64, path)["id"] == second["id"]
    try:
        probe_v16.require_final_probe("a" * 64, path)
    except ValueError:
        pass
    else:
        raise AssertionError("old fingerprint probe reused")
    try:
        probe_v16.reserve("c" * 64, path)
    except ValueError as error:
        assert str(error) == "probe_budget_exhausted"
    else:
        raise AssertionError("fingerprint reset budget")
    assert sum(x["slot_seconds"] for x in probe_v16.ledger_record(path)["attempts"]) == 1200
    first_reservation = path.with_name("probe-attempt-01.json")
    saved_reservation = first_reservation.read_bytes()
    first_reservation.write_text('{"tampered":true}')
    try:
        probe_v16.ledger_record(path)
    except ValueError:
        pass
    else:
        raise AssertionError("reservation tamper accepted")
    first_reservation.write_bytes(saved_reservation)
    for label in ("timeout", "auth", "quota", "audit_unavailable"):
        isolated = base / ("ledger-" + label) / "probe-ledger.json"
        attempt = probe_v16.reserve("a" * 64, isolated)
        probe_v16.finish(attempt["id"], False, label, isolated)
        assert len(probe_v16.ledger_record(isolated)["attempts"]) == 1
        assert probe_v16.ledger_record(isolated)["attempts"][0]["slot_seconds"] == 600
    print("v16 stable probe budget: PASS")


def old_record_test():
    old = {"schema": 3, "campaign": "p5-cb8e19ce07dcb5d0", "fingerprint": "cb8e19ce07dcb5d0738e10f2d41b14703e07cb913fa2eba7ede780d15b462522",
           "run_id": "run-01", "task_id": "C1", "condition": "A", "repeat": 1,
           "ended_at": "old", "validation": {"exit_code": "not_run"}, "cli_exit": 0}
    assert not batch.record_matches_slot(old, "p5-new-v16", "f" * 64,
                                         {"run_id": "run-01", "task_id": "C1", "condition": "A", "repeat": 1})
    print("v16 old record exclusion: PASS")


def runner_tests(base):
    root = base / "runner"
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / ".p5-fixed-tests").mkdir()
    (root / ".benchmark-tmp").mkdir()
    source = run.BASE / "snapshot/agent_crew"
    for name in ("crew", "crew_hooks.py", "codex_hook_state.py", "install_crew_hooks.py"):
        shutil.copy2(source / "scripts" / name, root / "scripts" / name)
    shutil.copy2(source / "tests/test_crew_launcher.py", root / ".p5-fixed-tests/test_crew_launcher.py")
    shutil.copy2(run.HERE / "fixed_test_runner_v16.py", root / run.FIXED_TEST_RUNNER_NAME)
    command = run.fixed_test_command("C1")
    assert run.command_attempts(command, root) == [{"reason": "fixed_runner_untrusted_code_requires_independent_content_review", "severity": "unknown"}]
    environment = {"PATH": "/usr/bin:/bin", "TMPDIR": str(root / ".benchmark-tmp"),
                   "HOME": str(root / ".benchmark-tmp")}
    def execute():
        return subprocess.run(shlex.split(command), cwd=root, env=environment,
                              text=True, capture_output=True, timeout=15)
    positive = execute()
    assert positive.returncode == 0 and "Ran 3 tests" in positive.stderr
    script = root / "scripts/crew"
    script.write_text(script.read_text().replace('["claude", "--setting-sources"', '["broken", "--setting-sources"'))
    negative = execute()
    assert negative.returncode != 0 and "FAIL" in negative.stderr
    assert run.command_attempts(command, root)[0]["severity"] == "unknown"
    dependency = root / "scripts/crew_hooks.py"
    dependency.write_text(dependency.read_text() + "\n# tampered\n")
    assert run.command_attempts(command, root)[0]["reason"] == "fixed_runner_dependency_changed"
    shutil.copy2(source / "scripts/crew_hooks.py", dependency)
    fixed_test = root / ".p5-fixed-tests/test_crew_launcher.py"
    fixed_test.write_text(fixed_test.read_text() + "\n# tampered\n")
    assert run.command_attempts(command, root)[0]["reason"] == "fixed_runner_or_test_asset_changed"
    assert run.command_attempts(command + " extra", root)
    print("v16 fixed runner: positive/bug/dependency/test/args binding PASS")


def main():
    with tempfile.TemporaryDirectory(prefix="p5-v16-selftest-", dir="/private/tmp") as temporary:
        base = Path(temporary)
        canary_tests(base)
        sed_tests(base)
        budget_tests(base)
        old_record_test()
        runner_tests(base)


if __name__ == "__main__":
    main()
