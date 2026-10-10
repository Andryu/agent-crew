#!/usr/bin/env python3
"""v17 schema2・secret・sed・probe budget/residualのmodel不要な故障注入。"""

import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

import probe_v17 as probe_v16
import batch
import run
import analyze
import harness_fingerprint


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
    # Ledger state-machine tests use a synthetic supervisor identity; actual
    # ps/process-group behavior is covered by dedicated residual/failure tests.
    supervisor = {"pid": os.getpid(), "pgid": os.getpgrp(), "uid": os.getuid(), "started": "synthetic"}
    with patch.object(probe_v16, "_process_identity", return_value=supervisor):
        first = probe_v16.reserve("a" * 64, path)
    try:
        probe_v16.reserve("a" * 64, path)
    except ValueError as error:
        assert str(error) == "probe_prior_attempt_incomplete_or_residual_unknown"
    else:
        raise AssertionError("parallel probe reservation accepted")
    try:
        probe_v16.finish(first["id"], False, "timeout", path)
    except ValueError:
        pass
    else:
        raise AssertionError("finish without child/residual proof accepted")
    assert probe_v16.ledger_record(path)["attempts"][0]["state"] == "reserved"
    probe_v16.finish(first["id"], False, "auth", path, child_reaped=True, residual_verified=True)
    with patch.object(probe_v16, "_process_identity", return_value=supervisor):
        second = probe_v16.reserve("b" * 64, path)
        probe_v16.finish(second["id"], True, "pass", path, child_reaped=True, residual_verified=True)
    for fingerprint in ("a" * 64, "b" * 64):
        try:
            probe_v16.require_final_probe(fingerprint, path)
        except ValueError:
            pass
        else:
            raise AssertionError("後発passが先行failを隠した")
    clean = base / "ledger-single-pass" / "probe-ledger.json"
    with patch.object(probe_v16, "_process_identity", return_value=supervisor):
        only_pass = probe_v16.reserve("d" * 64, clean)
    probe_v16.finish(only_pass["id"], True, "pass", clean, child_reaped=True, residual_verified=True)
    assert probe_v16.require_final_probe("d" * 64, clean)["id"] == only_pass["id"]
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
        with patch.object(probe_v16, "_process_identity", return_value=supervisor):
            attempt = probe_v16.reserve("a" * 64, isolated)
        probe_v16.finish(attempt["id"], False, label, isolated, child_reaped=True, residual_verified=True)
        assert len(probe_v16.ledger_record(isolated)["attempts"]) == 1
        assert probe_v16.ledger_record(isolated)["attempts"][0]["slot_seconds"] == 600
    crashed = base / "crash" / "probe-ledger.json"
    with patch.object(probe_v16, "_process_identity", return_value=supervisor):
        probe_v16.reserve("a" * 64, crashed)
    for operation in (lambda: probe_v16.reserve("b" * 64, crashed),
                      lambda: probe_v16.require_final_probe("b" * 64, crashed)):
        try:
            operation()
        except ValueError:
            pass
        else:
            raise AssertionError("crashed reservation bypassed")
    stale = base / "stale-lock" / "probe-ledger.json"
    stale.parent.mkdir(mode=0o700)
    stale.with_name("probe-ledger.lock").write_bytes(b"")
    stale.with_name("probe-ledger.lock").chmod(0o600)
    with patch.object(probe_v16, "_process_identity", return_value=supervisor):
        attempt = probe_v16.reserve("a" * 64, stale)
    probe_v16.finish(attempt["id"], False, "stale_lock_recovered", stale,
                     child_reaped=True, residual_verified=True)
    concurrent = base / "concurrent" / "probe-ledger.json"
    outcomes = []
    def contender():
        try:
            with patch.object(probe_v16, "_process_identity", return_value=supervisor):
                outcomes.append(("reserved", probe_v16.reserve("c" * 64, concurrent)["id"]))
        except ValueError as error:
            outcomes.append(("rejected", str(error)))
    workers = [threading.Thread(target=contender) for _ in range(2)]
    for worker in workers: worker.start()
    for worker in workers: worker.join()
    assert sum(result[0] == "reserved" for result in outcomes) == 1
    assert sum(result[0] == "rejected" for result in outcomes) == 1
    reused = {"child_pid": 9, "child_pgid": 9, "child_started": "Mon Jan  1 00:00:00 2024"}
    assert not probe_v16.process_identity_matches(reused, {"pid": 9, "pgid": 9, "started": "Mon Jan  1 00:00:01 2024"})
    timeout_child = subprocess.Popen(["/bin/sleep", "30"], start_new_session=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    child_identity = {"pid": timeout_child.pid, "pgid": timeout_child.pid,
                      "uid": os.getuid(), "started": "synthetic-child-start"}
    child_entry = {"child_pid": timeout_child.pid, "child_pgid": timeout_child.pid,
                   "child_started": child_identity["started"]}
    try:
        timeout_child.communicate(timeout=0.02)
    except subprocess.TimeoutExpired:
        pass
    with patch.object(probe_v16, "_process_identity", return_value=child_identity):
        assert probe_v16.reap_probe_child(timeout_child, child_entry)
    assert timeout_child.returncode is not None
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


def residual_context_tests(base):
    uid = os.getuid()
    root = base / "process-root"
    root.mkdir()
    def check(ps_rows, open_rows="", lsof_error="", lsof_code=1):
        def fake_run(command, **_kwargs):
            if command[0] == "/bin/ps":
                return SimpleNamespace(returncode=0, stdout=ps_rows, stderr="")
            return SimpleNamespace(returncode=lsof_code, stdout=open_rows, stderr=lsof_error)
        with patch.object(run.subprocess, "run", fake_run):
            return run.scan_residual_context(root, 42)
    assert check(f"99 99 {uid}\n")["passed"]
    assert not check(f"42 42 {uid}\n")["passed"]
    assert not check(f"99 42 {uid}\n")["passed"]
    assert not check(f"99 99 {uid}\n", "p99\n", lsof_code=0)["passed"]
    assert not check(f"99 99 {uid}\n", lsof_error="unavailable")["scan_pass"]
    assert check(f"99 99 {uid}\n", "", lsof_error="WARNING: incomplete scan", lsof_code=0)["status"] == "unknown"
    assert check(f"99 99 {uid}\n", "", lsof_code=0)["status"] == "unknown"
    assert check(f"99 99 {uid}\n", "p99\n", lsof_error="WARNING: skipped file", lsof_code=0)["status"] == "unknown"
    def failed_scan(_command, **_kwargs):
        raise subprocess.TimeoutExpired("lsof", 5)
    with patch.object(run.subprocess, "run", failed_scan):
        assert run.scan_residual_context(root, 42)["status"] == "unknown"
    def decode_scan(_command, **_kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "synthetic")
    with patch.object(run.subprocess, "run", decode_scan):
        assert run.scan_residual_context(root, 42)["status"] == "unknown"
    assert run.scan_residual_context(root, None)["status"] == "unknown"
    print("v16 residual PID/group/open file/unknown: PASS")


def raw_secret_path_tests(base):
    secret = b"SYNTHETIC_P5_SECRET_RAW_v17_7391"
    output = base / "raw-secret.jsonl"
    valid = event_stream("safe")
    for label, payload, audited in (("audit_exception", valid, False), ("failed", valid, True),
                                    ("unknown", valid, True), ("timeout", valid, True)):
        if label != "audit_exception":
            payload += "\n" + json.dumps({"type": label, "secret": secret.decode()})
        raw_writer = []
        try:
            with patch.object(run, "_write_private", side_effect=lambda *_args, **_kwargs: raw_writer.append(True)):
                run.save_raw_events(output, payload, forbidden_values=(secret,), audit_passed=audited)
        except run.BoundaryError:
            pass
        else:
            raise AssertionError(label + " raw save was accepted")
        assert not output.exists()
        assert raw_writer == [], "secret bytes reached raw saver"
    generated = {"raw": "", "events": json.dumps({"diagnostics": []}),
                 "summary": json.dumps({"status": "unknown"}), "diagnostics": "[]", "public": "{}"}
    assert all(secret.decode() not in content for content in generated.values())
    # 実event serializerはsecretを含むrawを要約へ取り込まず、固定reasonとdigestだけにする。
    root = base / "secret-events"
    root.mkdir()
    root.chmod(0o700)
    raw = event_stream("safe") + "\n" + json.dumps({"type": "diagnostic", "secret": secret.decode()})
    event_path = root / "events.json"
    report = run.safe_events(raw, event_path, expected_cwd=root, expected_env={}, forbidden_values=(secret,))
    saved_events = event_path.read_text()
    assert report["event_audit"]["passed"] is False and secret.decode() not in saved_events
    summary_path = root / "summary.json"
    try:
        batch.atomic_json(summary_path, {"detail": secret.decode()}, forbidden_values=(secret,))
    except run.BoundaryError:
        pass
    else:
        raise AssertionError("batch summary saved secret")
    spec = {"root": root / "run-01", "binding": {"harness_fingerprint": "f" * 64},
            "env": {"TOKEN": secret.decode()}}
    try:
        run.abort_run(spec, "model", "synthetic", details={"diagnostic": secret.decode()})
    except run.BoundaryError:
        pass
    except SystemExit:
        raise AssertionError("diagnostic saved secret")
    else:
        raise AssertionError("diagnostic secret injection not rejected")
    public_candidate = {"campaign": secret.decode(), "fingerprint": "f" * 64, "campaign_complete": False,
        "all_runs_final_pass": False, "quality_gate": {"status": "unknown"},
        "safety_gate": {"status": "unknown"}, "cache_comparability": {"status": "unknown"},
        "speed_target": {"status": "unknown"}, "decision": "incomplete"}
    try:
        analyze.public_markdown(public_candidate, forbidden_values=(secret,))
    except analyze.AnalysisError:
        pass
    else:
        raise AssertionError("public candidate contains secret")
    public_path = root / "public.md"
    try:
        analyze.write_public(public_path, "synthetic " + secret.decode(), forbidden_values=(secret,))
    except run.BoundaryError:
        pass
    else:
        raise AssertionError("public file writer accepted secret")
    assert not public_path.exists()
    print("v17 raw saver secret refusal: PASS")


def binding_and_preflight_tests(base):
    path = base / "preflight-minimal.json"
    run._write_private(path, json.dumps({"passed": True, "binding": {"harness_fingerprint": "a" * 64}}))
    try:
        probe_v16.check_preflight(path, "a" * 64)
    except ValueError:
        pass
    else:
        raise AssertionError("passed+fingerprint-only preflight accepted")
    shell_file = base / "path_helper"
    shell_file.write_text("#!/bin/sh\nexit 0\n")
    shell_file.chmod(0o700)
    executable_identity = harness_fingerprint._shell_file_identity(shell_file)
    shell_file.chmod(0o600)
    nonexec_identity = harness_fingerprint._shell_file_identity(shell_file)
    assert executable_identity["mode"] != nonexec_identity["mode"]
    assert executable_identity["executable"] is True and nonexec_identity["executable"] is False
    original_identity = harness_fingerprint._shell_file_identity
    def fingerprint_with_mode(mode):
        def identity(value, optional=False):
            found = original_identity(value, optional)
            if str(value) == "/usr/libexec/path_helper":
                return {**found, "mode": mode, "executable": bool(mode & 0o111)}
            return found
        with patch.object(harness_fingerprint, "_shell_file_identity", identity):
            return harness_fingerprint.compute_harness_fingerprint(run.HERE,
                python_runtime_binding={"synthetic": True}, codex_executable_binding={"synthetic": True},
                driver_executable_binding={"synthetic": True},
                normal_shell_launcher_binding={"synthetic_launcher": True})
    before = fingerprint_with_mode(0o755)
    after = fingerprint_with_mode(0o644)
    assert before != after
    print("v17 strict preflight acceptance/shell mode fingerprint/old fingerprint binding: PASS")


def main():
    with tempfile.TemporaryDirectory(prefix="p5-v16-selftest-", dir="/private/tmp") as temporary:
        base = Path(temporary)
        canary_tests(base)
        sed_tests(base)
        budget_tests(base)
        old_record_test()
        runner_tests(base)
        residual_context_tests(base)
        raw_secret_path_tests(base)
        binding_and_preflight_tests(base)


if __name__ == "__main__":
    main()
