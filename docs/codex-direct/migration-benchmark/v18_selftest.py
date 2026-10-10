#!/usr/bin/env python3
"""v18のphase遷移、secret gate、preflight binding、probe ledger回帰をmodelなしで検証する。"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
from unittest.mock import patch

import analyze
import batch
import driver as driver_module
import harness_fingerprint
import probe_v17 as probe
import run
import v17_selftest


def _private_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    run.save(path, value)


def _prepare_spec(root, base, fingerprint, phase, task):
    current = base
    for part in root.relative_to(base).parts[:-1]:
        current = current / part
        current.mkdir(mode=0o700, exist_ok=True)
        current.chmod(0o700)
    root.mkdir(mode=0o700, parents=True)
    (root / ".benchmark-tmp/home").mkdir(mode=0o700, parents=True)
    (root / "migration-progress").mkdir(mode=0o700)
    run._write_private(root / "AGENTS.md", "P5 model-free v18 fixture\n")
    run.install_env_canary(root, fingerprint, phase)
    return run.execution_spec(root, task, run.CLI_VERSION, fingerprint, phase)


def _case_evidence(spec):
    expected = run.required_preflight_cases(spec)
    return [{"name": name, "expected": outcome,
             "outcome": "allowed" if outcome == "allow" else "sandbox_denied",
             "exit_code": 0 if outcome == "allow" else 1,
             "binding_sha256": run.canonical_digest(spec["binding"]),
             "command_sha256": "a" * 64, "stdout_sha256": "b" * 64, "stderr_sha256": "c" * 64}
            for name, outcome in expected.items()]


def _preflight_report(spec):
    binding = spec["binding"]
    writes = sorted(str(path.relative_to(spec["root"]))
                    for path in run.permission_policy(spec["root"], spec["task"]))
    return {"schema": 3, "started_at": "2026-10-10T00:00:00+00:00",
        "cli_version": binding["cli_version"],
        "tool_environment_scope": "auxiliary_env_i_probe_not_actual_exec_tool",
        "binding": binding,
        "binding_comparison": "entire_canonical_binding_equal_before_model",
        "execution_profile_evidence": {"schema": 1, "profile_name": "p5_fixture", "network_enabled": False,
            "read_boundary": binding["read_boundary"], "write_paths": writes,
            "policy_template_sha256": binding["policy_template_sha256"],
            "profile_sha256": binding["profile_sha256"],
            "binding_sha256": run.canonical_digest(binding)},
        "passed": True, "cases": _case_evidence(spec), "sandbox_initialized": True,
        "postconditions": {"canary_writes_observed": True, "outside_writes_absent": True,
            "private_sentinel_unchanged": True, "task_file_contents_unchanged": True,
            "binding_unchanged": True, "python_runtime_unchanged": True},
        "canaries_removed": True, "process_may_still_be_running": False,
        "residual_scan_evidence": {"status": "pass", "passed": True, "scan_pass": True,
            "run_root_open_file_process_count": 0, "token_process_scan_pass": True,
            "token_process_scan_count": 3, "complete_detection_claimed": False},
        "ended_at": "2026-10-10T00:00:01+00:00", "private_diagnostics_sha256": "d" * 64}


def phase_transition_and_preflight_tests(base):
    fingerprint = "e" * 64
    preflight_root = base / "preflight" / ("sandbox-preflight-" + uuid.uuid4().hex) / "fixture"
    probe_root = base / "probe" / ("probe-" + uuid.uuid4().hex)
    model_task = run.c6_task()
    probe_task = {"id": "PROBE", "input": [], "fixture": []}
    runtime = {"synthetic_runtime_binding": "fixed"}
    cli = {"synthetic_cli_binding": "fixed"}
    with (patch.object(run, "compute_python_runtime_binding", return_value=runtime),
          patch.object(run, "compute_codex_executable_binding", return_value=cli),
          patch.object(harness_fingerprint, "compute_python_runtime_binding", return_value=runtime),
          patch.object(harness_fingerprint, "compute_codex_executable_binding", return_value=cli),
          patch.object(probe, "BASE", base)):
        preflight_spec = _prepare_spec(preflight_root, base, fingerprint, "model", model_task)
        probe_spec = _prepare_spec(probe_root, base, fingerprint, "probe", probe_task)
        report = _preflight_report(preflight_spec)
        report_path = base / "preflight-report.json"
        _private_json(report_path, report)
        digest, checked_binding, checked_report = probe.check_preflight(report_path, fingerprint)
        assert len(digest) == 64 and checked_binding == preflight_spec["binding"]
        assert checked_report["cases"] == report["cases"]
        profile = report["execution_profile_evidence"]
        assert probe.compare_preflight_binding(preflight_spec["binding"], probe_spec["binding"], profile, probe_spec)

        # model→probeはphase差だけを明示許可し、phase-specific profileを固定仕様から確認する。
        for bad_preflight, bad_probe in (
            ({**preflight_spec["binding"], "phase": "probe"}, probe_spec["binding"]),
            (preflight_spec["binding"], {**probe_spec["binding"], "phase": "model"}),
            (preflight_spec["binding"], {**probe_spec["binding"], "policy_template_sha256": "0" * 64}),
        ):
            assert not probe.compare_preflight_binding(bad_preflight, bad_probe, profile, probe_spec)

        mutations = (
            lambda b: {**b, "private_directories": {}},
            lambda b: {**b, "private_directories": {"root": {}}},
            lambda b: {**b, "env_canary_script": {}},
            lambda b: {**b, "env_canary_script": {**b["env_canary_script"], "inode": 0}},
            lambda b: {**b, "codex_executable": {}},
            lambda b: {**b, "python_runtime": {}},
            lambda b: {**b, "tool_environment": {}},
        )
        for mutate in mutations:
            mutated = {**report, "binding": mutate(report["binding"])}
            _private_json(report_path, mutated)
            try:
                probe.check_preflight(report_path, fingerprint)
            except (OSError, ValueError, run.BoundaryError):
                pass
            else:
                raise AssertionError("preflight nested identity mutation accepted")
        # canonical preflight bindingが有効な通常系を最後に再確認。
        _private_json(report_path, report)
        assert probe.check_preflight(report_path, fingerprint)[1] == preflight_spec["binding"]
    print("v18 model-free phase transition and fixed nested preflight binding: PASS")


def secret_save_tests(base):
    secret = "v18_Synthetic_API_TOKEN_9f6e4d2c8b7a1"
    token = "f1a37d9c02e84b6a7d31c5e9a4028b6d"
    assert run.secret_env_values({"ZERO": "0", "ONE": "1", "P5_RUN_TOKEN": "1"}) == ()
    assert run.secret_env_values({"PATH": run.FIXED_PATH, "HOME": str(base),
                                  "P5_RUN_TOKEN": token}) == (token,)
    secrets = run.secret_env_values({"P5_RUN_TOKEN": token, "API_TOKEN": secret, "ZERO": "0", "ONE": "1"})
    assert secrets == (token, secret)

    root = base / "secret"
    root.mkdir(mode=0o700)
    canary_root = root / "canary"
    canary_root.mkdir(mode=0o700)
    run.install_env_canary(canary_root, "v18-secret-test")
    expected_env = run.limited_env(canary_root, "v18-secret-test")
    canary_result = v17_selftest.observe(canary_root, v17_selftest.tool_env(expected_env, canary_root))
    assert canary_result.returncode == 0 and canary_result.stderr == ""
    valid_raw = v17_selftest.event_stream(canary_result.stdout)
    audit = run.safe_events(valid_raw, expected_cwd=canary_root, expected_env=expected_env,
                            forbidden_values=secrets)
    assert audit["event_audit"]["passed"] and audit["env_canary_evidence"]["passed"]
    raw_path = root / "raw.jsonl"
    # 実canaryのイベント監査結果をそのまま保存関数へ渡すpositive path。
    written_hash = run.save_raw_events(raw_path, valid_raw, forbidden_values=secrets,
                                       audit_passed=audit["event_audit"]["passed"])
    assert raw_path.read_text() == valid_raw and len(written_hash) == 64
    raw_path.unlink()
    try:
        run.save_raw_events(raw_path, valid_raw + "\n" + json.dumps({"type": "error", "message": secret}),
                            forbidden_values=secrets, audit_passed=audit["event_audit"]["passed"])
    except run.BoundaryError:
        pass
    else:
        raise AssertionError("secret raw bytes reached saver")
    assert not raw_path.exists()

    summary_path = root / "summary.json"
    batch.atomic_json(summary_path, {"status": "unknown", "count": 1}, forbidden_values=secrets)
    try:
        batch.atomic_json(root / "summary-secret.json", {"status": secret}, forbidden_values=secrets)
    except run.BoundaryError:
        pass
    else:
        raise AssertionError("secret summary accepted")

    public_candidate = {"campaign": "p5-v18-synthetic", "fingerprint": "a" * 64,
        "campaign_complete": False, "all_runs_final_pass": False,
        "quality_gate": {"status": "unknown"}, "safety_gate": {"status": "unknown"},
        "cache_comparability": {"status": "unknown"}, "speed_target": {"status": "unknown"},
        "decision": "incomplete"}
    public_path = root / "public.md"
    public_markdown = analyze.public_markdown(public_candidate, forbidden_values=secrets)
    analyze.write_public(public_path, public_markdown, forbidden_values=secrets)
    try:
        analyze.public_markdown({**public_candidate, "campaign": secret}, forbidden_values=secrets)
    except analyze.AnalysisError:
        pass
    else:
        raise AssertionError("secret public generation accepted")
    try:
        analyze.write_public(root / "public-secret.md", "token=" + token, forbidden_values=secrets)
    except run.BoundaryError:
        pass
    else:
        raise AssertionError("secret public artifact accepted")
    assert "P5 新campaign集計" in public_path.read_text()

    campaign = root / "campaign"
    run_dir = campaign / "run-01"
    run_dir.mkdir(mode=0o700, parents=True)
    spec = {"root": run_dir, "binding": {"harness_fingerprint": "a" * 64},
            "env": {"P5_RUN_TOKEN": token, "ZERO": "0", "ONE": "1"}}
    try:
        run.abort_run(spec, "model", "synthetic", details={"safe": "fixed reason"})
    except SystemExit as error:
        assert error.code == 1
    diagnostic = campaign / ".evidence/run-01/model-interruption.json"
    assert diagnostic.exists() and token not in diagnostic.read_text()
    try:
        run.abort_run(spec, "model", "synthetic", details={"token": token})
    except run.BoundaryError:
        pass
    except SystemExit as error:
        raise AssertionError("secret diagnostic saved") from error
    else:
        raise AssertionError("secret diagnostic injection accepted")
    print("v18 secret candidate filtering + real saver success/refusal integration: PASS")


def ledger_timeout_then_pass_test(base):
    path = base / "ledger-timeout-pass" / "probe-ledger.json"
    fake_identity = {"pid": os.getpid(), "pgid": os.getpgrp(), "uid": os.getuid(), "started": "synthetic"}
    def reserve_test(target):
        with patch.object(probe, "_process_identity", return_value=fake_identity):
            return probe.reserve("a" * 64, target, driver_config_binding={"sha256": "b" * 64})
    first = reserve_test(path)
    probe.finish(first["id"], False, "model_timeout", path, child_reaped=True, residual_verified=True)
    second = reserve_test(path)
    probe.finish(second["id"], True, "pass", path, child_reaped=True, residual_verified=True)
    try:
        probe.require_final_probe("a" * 64, path, driver_config_binding={"sha256": "b" * 64})
    except ValueError as error:
        assert str(error) == "final_fixed_probe_not_passed"
    else:
        raise AssertionError("later pass masked prior timeout/fail")
    assert [item["state"] for item in probe.ledger_record(path)["attempts"]] == ["fail", "pass"]
    print("v18 timeout→pass ledger cannot authorize formal: PASS")


def persistent_launcher_test(base):
    assert driver_module.LAUNCHER == harness_fingerprint.formal_base() / "drivers/p5-v19-final8-normal-shell.sh"
    launcher = base / "Library/Caches/p5/drivers/p5-v18-normal-shell.sh"
    launcher.parent.mkdir(mode=0o700, parents=True)
    launcher.write_text("#!/bin/zsh\nexec fixed-driver verify\n")
    launcher.chmod(0o700)
    first = harness_fingerprint.compute_normal_shell_launcher_binding(launcher)
    runtime = {"synthetic_runtime": "fixed"}
    cli = {"synthetic_cli": "fixed"}
    driver = {"synthetic_driver": "fixed"}
    first_fp = harness_fingerprint.compute_harness_fingerprint(run.HERE,
        python_runtime_binding=runtime, codex_executable_binding=cli,
        driver_executable_binding=driver, normal_shell_launcher_binding=first)
    wrapper = Path("/private/tmp") / ("p5-v18-wrapper-" + uuid.uuid4().hex)
    wrapper.write_text("#!/bin/zsh\nexec "+str(launcher)+" \"$@\"\n")
    wrapper.chmod(0o700)
    wrapper.unlink()
    second = harness_fingerprint.compute_normal_shell_launcher_binding(launcher)
    second_fp = harness_fingerprint.compute_harness_fingerprint(run.HERE,
        python_runtime_binding=runtime, codex_executable_binding=cli,
        driver_executable_binding=driver, normal_shell_launcher_binding=second)
    assert first == second and first_fp == second_fp
    launcher.chmod(0o600)
    changed = harness_fingerprint._private_executable_binding(launcher, 0o600)
    changed_fp = harness_fingerprint.compute_harness_fingerprint(run.HERE,
        python_runtime_binding=runtime, codex_executable_binding=cli,
        driver_executable_binding=driver, normal_shell_launcher_binding=changed)
    assert changed_fp != first_fp
    print("v18 persistent Cache launcher binding survives /private/tmp wrapper loss: PASS")


def main():
    with tempfile.TemporaryDirectory(prefix="p5-v18-selftest-", dir="/private/tmp") as temp:
        base = Path(temp)
        phase_transition_and_preflight_tests(base)
        secret_save_tests(base)
        ledger_timeout_then_pass_test(base)
        persistent_launcher_test(base)
    print("P5 v18 selftest: all passed; model call count 0")


if __name__ == "__main__":
    main()
