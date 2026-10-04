#!/usr/bin/env python3
"""P5集計を合成24runとprivate raw証跡で検証する。モデルは呼ばない。"""

import hashlib
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
import json
import importlib.util
import os
import pwd
import shlex
import subprocess
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


batch = load_module("batch")
analyze = load_module("analyze")
from harness_fingerprint import compute_harness_fingerprint
import run as harness_run
import harness_fingerprint as fingerprint_module
import probe_v17 as probe_v16
HASH = "a" * 64


def synthetic_canary_output(required, root):
    environment = {**required, "CODEX_CI": "1", "CODEX_PERMISSION_PROFILE": "p5_fixture",
                   "CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1",
                   "CODEX_SESSION_ID": "abcdefab-cdef-7abc-8def-abcdefabcdef",
                   "CODEX_THREAD_ID": "abcdefab-cdef-7abc-8def-abcdefabcdee",
                   "CODEX_VERSION": "0.160.0", "COLORTERM": "", "GH_PAGER": "cat", "GIT_PAGER": "cat",
                   "LC_CTYPE": "C.UTF-8", "LOGNAME": pwd.getpwuid(os.getuid()).pw_name,
                   "NO_COLOR": "1", "OLDPWD": str(root), "PAGER": "cat", "PWD": str(root),
                   "SHLVL": "0", "TERM": "dumb", "_": harness_run.PYTHON_EXECUTABLE}
    result = subprocess.run(shlex.split(harness_run.ENV_CANARY_COMMAND), cwd=root, env=environment,
                            text=True, capture_output=True, check=True)
    return result.stdout.strip()


def binding(root, fingerprint, phase, task):
    return harness_run.derive_canonical_binding(root, task, harness_run.CLI_VERSION,
                                                fingerprint, phase=phase)


def synthetic_preflight(spec):
    model = spec["binding"]
    profile = {"schema": 1, "profile_name": "p5_fixture", "network_enabled": False,
        "read_boundary": model["read_boundary"],
        "write_paths": sorted(str(path.relative_to(spec["root"])) for path in harness_run.permission_policy(spec["root"], spec["task"])),
        "policy_template_sha256": model["policy_template_sha256"],
        "profile_sha256": model["profile_sha256"],
        "binding_sha256": harness_run.canonical_digest(model)}
    required = harness_run.required_preflight_cases(spec)
    cases = [{"name": name, "expected": expected,
              "outcome": "allowed" if expected == "allow" else "sandbox_denied",
              "exit_code": 0 if expected == "allow" else 1,
              "command_sha256": HASH, "stdout_sha256": HASH, "stderr_sha256": HASH,
              "binding_sha256": harness_run.canonical_digest(model)}
             for name, expected in required.items()]
    return {"schema": 3, "started_at": "synthetic-start", "ended_at": "synthetic-end",
            "private_diagnostics_sha256": HASH, "cli_version": harness_run.CLI_VERSION, "binding": model,
            "binding_comparison": "entire_canonical_binding_equal_before_model",
            "tool_environment_scope": "auxiliary_env_i_probe_not_actual_exec_tool",
            "passed": True, "canaries_removed": True, "sandbox_initialized": True,
            "process_may_still_be_running": False, "execution_profile_evidence": profile,
            "residual_scan_evidence": {"status": "pass", "passed": True, "scan_pass": True,
                "run_root_open_file_process_count": 0, "token_process_scan_pass": True,
                "token_process_scan_count": 3, "complete_detection_claimed": False},
            "postconditions": {"canary_writes_observed": True, "outside_writes_absent": True,
                               "private_sentinel_unchanged": True, "task_file_contents_unchanged": True,
                               "binding_unchanged": True, "python_runtime_unchanged": True}, "cases": cases}


def fixtures(campaign_dir, a_seconds=100.0, b_seconds=70.0):
    fingerprint = compute_harness_fingerprint(HERE)
    campaign = f"p5-{fingerprint[:16]}"
    assert campaign_dir.name == campaign
    runs, reviews = [], []
    for slot in batch.scheduled_runs():
        task, condition, repeat, run_id = (slot["task_id"], slot["condition"],
                                            slot["repeat"], slot["run_id"])
        root = campaign_dir / run_id
        accepted = campaign_dir / ".accepted" / run_id
        root.mkdir(parents=True, exist_ok=True)
        accepted.mkdir(parents=True, exist_ok=True)
        harness_run.install_env_canary(root, fingerprint)
        task_definition = harness_run.c6_task() if task == "C6" else next(
            item for item in harness_run.load(harness_run.BASE / "comparison.json")["tasks"]
            if item["id"] == task)
        model_spec = harness_run.canonical_execution_spec(root, task_definition,
                                                          harness_run.CLI_VERSION, fingerprint, phase="model")
        model = model_spec["binding"]
        validator = binding(accepted, fingerprint, "validation", task_definition)
        raw = campaign_dir / ".evidence" / run_id / "events.raw.jsonl"
        raw.parent.mkdir(parents=True, exist_ok=True)
        canary = harness_run.ENV_CANARY_COMMAND
        env_output = synthetic_canary_output(model_spec["env"], root)
        events = [
            {"type": "thread.started", "thread_id": "synthetic"},
            {"type": "turn.started"},
            {"type": "item.started", "item": {"type": "command_execution", "id": "env-canary",
                                               "command": canary, "status": "in_progress"}},
            {"type": "item.completed", "item": {"type": "command_execution", "id": "env-canary",
                                                 "command": canary, "status": "completed", "exit_code": 0,
                                                 "aggregated_output": env_output}},
            {"type": "turn.completed", "usage": {"input_tokens": 1000,
                                                 "cached_input_tokens": 500, "output_tokens": 100,
                                                 "cache_write_input_tokens": 100, "total_tokens": 1100}},
        ]
        raw.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        raw.chmod(0o600)
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        classified = harness_run.safe_events(raw.read_text(encoding="utf-8"), expected_cwd=root,
                                             expected_env=model_spec["env"])
        assert classified["event_audit"]["passed"] is True
        assert classified["env_canary_evidence"]["passed"] is True
        preflight_path = root / ".benchmark-isolation.json"
        batch.atomic_json(preflight_path, synthetic_preflight(model_spec))
        preflight_sha = hashlib.sha256(harness_run.safe_read(preflight_path)).hexdigest()
        empty_digest = harness_run.canonical_digest(harness_run.tree_manifest(accepted))
        runs.append({
            "schema": 3, "campaign": campaign, "fingerprint": fingerprint,
            "run_id": run_id, "task_id": task, "condition": condition, "repeat": repeat,
            "cli_version": harness_run.CLI_VERSION, "cli_exit": 0,
            "preflight_evidence_relative_path": f"{run_id}/.benchmark-isolation.json",
            "preflight_evidence_sha256": preflight_sha,
            "validation": {"exit_code": 0, "manifest_unchanged": True, "binding": validator,
                           "derived_from_model_profile_sha256": model["profile_sha256"],
                           "manifest_before_sha256": empty_digest, "manifest_after_sha256": empty_digest},
            "snapshot_evidence": {"matched": True, "before_sha256": empty_digest,
                                  "after_sha256": empty_digest, "accepted_sha256": empty_digest},
            "isolation_gate": {"status": "pass", "passed": True, "preflight_bound": True,
                               "env_canary_pass": True, "residual_process_count": 0,
                               "residual_scan_pass": True, "preflight_evidence_valid": True,
                               "binding": model, "preflight_binding": model},
            "env_canary_evidence": classified["env_canary_evidence"],
            "residual_process_evidence": {phase: {"status": "pass", "passed": True,
                "scan_pass": True, "detected_count": 0, "kill_count": 0, "remaining_count": 0,
                "scan_count": 2, "clean_after_scan": True, "detection_scope": "process_group_and_descendant_scan",
                "complete_descendant_detection_claimed": False} for phase in ("model", "validation")},
            "event_audit": classified["event_audit"],
            "attempt_policy": classified["attempt_policy"],
            "acceptance_gate": {"status": "pass", "passed": True},
            "safety_gate": {"status": "pass", "passed": True},
            "raw_event_evidence": {"path_relative_to_campaign": f".evidence/{run_id}/events.raw.jsonl",
                                   "sha256": digest, "mode": "0600"},
            "scope_violations": [], "host_guard": {"unchanged": True},
            "c6_validator_consistent": True if task == "C6" else None,
            "wall_seconds": a_seconds if condition == "A" else b_seconds,
            "input_tokens": 1000, "cached_input_tokens": 500,
            "cache_write_input_tokens": 100, "output_tokens": 100, "total_tokens": 1100,
            "cost_usd": "unknown", "approval_wait_seconds": "unknown",
            "ended_at": "2026-09-30T00:00:00Z",
        })
        reviews.append({
            "run_id": run_id, "task_id": task, "condition": condition, "repeat": repeat,
            "raw_event_sha256": digest, "source_result_sha256": HASH,
            "replay_report_sha256": HASH, "classifier_sha256": HASH,
            "event_audit_reproduced": True,
            "event_audit_pass": True, "attempt_policy_pass": True,
            "acceptance_pass": True, "handoff_pass": True, "scope_pass": True,
            "review_findings": [], "reviewed_by": "independent-reviewer",
            "reviewed_at": "2026-09-30T00:00:00Z",
        })
    summary = {"schema": 2, "campaign": campaign, "fingerprint": fingerprint,
               "schedule": batch.scheduled_runs(), "results": runs}
    review_file = {"schema": 2, "campaign": campaign, "fingerprint": fingerprint,
                   "reviews": reviews}
    refresh_evidence(summary, review_file, campaign_dir)
    return summary, {"passed": True}, review_file


def refresh_evidence(summary, reviews, campaign_dir):
    review_by_id = {review["run_id"]: review for review in reviews["reviews"]}
    classifier = harness_run.sha(HERE / "run.py")
    for record in summary["results"]:
        run_id = record["run_id"]
        result_path = campaign_dir / run_id / ".benchmark-result.json"
        batch.atomic_json(result_path, record)
        source_sha = hashlib.sha256(harness_run.safe_read(result_path)).hexdigest()
        review = review_by_id[run_id]
        review["source_result_sha256"] = source_sha
        review["classifier_sha256"] = classifier
        raw_path = campaign_dir / ".evidence" / run_id / "events.raw.jsonl"
        task = harness_run.c6_task() if record["task_id"] == "C6" else next(
            item for item in harness_run.load(harness_run.BASE / "comparison.json")["tasks"]
            if item["id"] == record["task_id"])
        spec = harness_run.canonical_execution_spec(campaign_dir / run_id, task,
                                                    harness_run.CLI_VERSION, summary["fingerprint"], phase="model")
        replay = harness_run.safe_events(raw_path.read_text(encoding="utf-8"),
                                         expected_cwd=campaign_dir / run_id,
                                         expected_env=spec["env"])
        replay.update({"schema": 1, "purpose": "independent_raw_reclassification",
                       "source_result_sha256": source_sha, "run_id": run_id,
                       "harness_fingerprint": summary["fingerprint"], "classifier_sha256": classifier,
                       "automatic_only": True, "independent_reviewer_judgement": "pending"})
        replay_path = campaign_dir / ".reviews" / f"{run_id}-replay.json"
        batch.atomic_json(replay_path, replay)
        review["replay_report_sha256"] = hashlib.sha256(harness_run.safe_read(replay_path)).hexdigest()


def decide(summary, preflight, reviews, campaign_dir):
    return analyze.analyze(summary, preflight, reviews, campaign_dir)


def batch_process_control_tests(parent):
    """実processを起動せず、timeout後の子root非接触とcampaign停止を検証する。"""
    assert batch.LIMIT_SECONDS == 24 * batch.RUN_PARENT_SECONDS + batch.GLOBAL_PREFLIGHT_SECONDS + batch.FINALIZATION_GRACE_SECONDS
    assert batch.RUN_PARENT_SECONDS == 1200 and batch.RUN_CHILD_GRACE_SECONDS >= 60
    originals = (batch.WORK, batch.require_preflight, batch.subprocess, batch.scheduled_runs, batch.atomic_json, batch.wait_private_process,
                 os.kill, os.killpg, Path.exists, Path.read_text, harness_run.safe_read)
    all_slots = batch.scheduled_runs()
    signals = []
    state = {"forbidden_root": None, "locked": False}
    def guard(path):
        root = state["forbidden_root"]
        if state["locked"] and root is not None and (Path(path) == root or root in Path(path).parents):
            raise AssertionError("未完了/非正常終了後に子run rootへ触れた: " + str(path))
    def guarded_exists(path):
        guard(path)
        return originals[8](path)
    def guarded_text(path, *args, **kwargs):
        guard(path)
        return originals[9](path, *args, **kwargs)
    def guarded_safe_read(path):
        guard(path)
        return originals[10](path)
    def forbidden_signal(*args):
        signals.append(args)
        raise AssertionError("batchがPID/PGIDへ自動signalを送った")
    os.kill, os.killpg = forbidden_signal, forbidden_signal
    Path.exists, Path.read_text, harness_run.safe_read = guarded_exists, guarded_text, guarded_safe_read
    try:
        for mode in ("preflight_timeout", "preflight_signal", "preflight_before_launch_signal", "preflight_success_run_timeout", "run_timeout", "run_nonzero", "run_signal", "run_before_popen_signal", "run_popen_signal", "run_after_wait_signal", "summary_signal", "normal"):
            work = parent / mode / "formal"
            work.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            launches = []
            state.update(forbidden_root=None, locked=False, run_waited=False, summary_interrupted=False)
            batch.WORK = work
            batch.scheduled_runs = lambda: all_slots[:1 if mode == "normal" else 2]
            preflight_calls = []
            def synthetic_preflight_call(_campaign, _expected_binding, _deadline=None):
                preflight_calls.append(True)
                if mode == "preflight_before_launch_signal":
                    raise batch.BatchSignal(15)
            batch.require_preflight = originals[1] if mode in {"preflight_timeout", "preflight_signal"} else synthetic_preflight_call
            def guarded_wait_private_process(command, cwd, campaign_dir, label, timeout, **kwargs):
                assert isinstance(kwargs.get("deadline_monotonic"), float)
                if label == "run-01":
                    child_deadline = float(command[command.index("--deadline-monotonic") + 1])
                    assert timeout == batch.RUN_PARENT_SECONDS
                    assert child_deadline <= kwargs["deadline_monotonic"] - batch.RUN_CHILD_GRACE_SECONDS
                elif label == "preflight":
                    assert timeout == batch.GLOBAL_PREFLIGHT_SECONDS
                if mode == "run_before_popen_signal" and label == "run-01":
                    state["locked"] = True
                    raise batch.BatchSignal(15)
                return originals[5](command, cwd, campaign_dir, label, timeout, **kwargs)
            batch.wait_private_process = guarded_wait_private_process
            def guarded_atomic_json(path, value):
                if mode == "summary_signal" and Path(path).name == "batch-summary.json" and state.get("run_waited") and not state.get("summary_interrupted"):
                    state["summary_interrupted"] = True
                    state["locked"] = True
                    raise batch.BatchSignal(15)
                return originals[4](path, value)
            batch.atomic_json = guarded_atomic_json
            class MockProcess:
                pid = 246813579
                def __init__(self, command, **kwargs):
                    self.command, self.kwargs = command, kwargs
                    self.is_preflight = Path(command[2]).name == "sandbox_preflight.py"
                    self.wait_calls = 0
                    self.returncode = None
                    launches.append(self)
                    if mode == "run_popen_signal" and not self.is_preflight:
                        state["locked"] = True
                        raise batch.BatchSignal(15)
                    assert kwargs["stdout"] is not subprocess.PIPE and kwargs["stderr"] is not subprocess.PIPE
                    for handle in (kwargs["stdout"], kwargs["stderr"]):
                        assert os.fstat(handle.fileno()).st_mode & 0o777 == 0o600
                    if self.is_preflight:
                        kwargs["stdout"].write(b'{"passed": true}\n')
                    else:
                        campaign = Path(command[command.index("--campaign") + 1])
                        run_id = command[command.index("--run-id") + 1]
                        state["forbidden_root"] = campaign / run_id
                        fingerprint = command[command.index("--fingerprint") + 1]
                        slot = next(item for item in all_slots if item["run_id"] == run_id)
                        record = {"schema": 3, "campaign": campaign.name, "fingerprint": fingerprint, **slot,
                                  "ended_at": "synthetic", "cli_exit": 0, "validation": {"exit_code": 0},
                                  "pass_preliminary": True,
                                  "isolation_gate": {"status": "pass", "passed": True, "preflight_bound": True},
                                  **{name: {"status": "pass", "passed": True} for name in
                                     ("event_audit", "attempt_policy", "safety_gate", "acceptance_gate")}}
                        # timeout後に完成して見える結果があっても、親は読まない。
                        batch.atomic_json(campaign / run_id / ".benchmark-result.json", record)
                def wait(self, timeout):
                    self.wait_calls += 1
                    assert timeout > 0 and self.wait_calls == 1
                    if self.is_preflight:
                        if mode == "preflight_timeout":
                            raise subprocess.TimeoutExpired(self.command, timeout)
                        if mode == "preflight_signal":
                            raise batch.BatchSignal(15)
                        self.returncode = 0
                        return 0
                    if mode in {"run_timeout", "preflight_success_run_timeout"}:
                        state["locked"] = True
                        raise subprocess.TimeoutExpired(self.command, timeout)
                    if mode == "run_signal":
                        state["locked"] = True
                        raise batch.BatchSignal(15)
                    if mode == "run_nonzero":
                        state["locked"] = True
                        self.returncode = 1
                        return 1
                    self.returncode = 0
                    state["run_waited"] = True
                    if mode == "run_after_wait_signal":
                        state["locked"] = True
                    return 0
                def communicate(self, **_kwargs):
                    raise AssertionError("batchはpipe communicateを使わない")
                def kill(self):
                    raise AssertionError("batch Popen.kill禁止")
                def terminate(self):
                    raise AssertionError("batch Popen.terminate禁止")
                def send_signal(self, _signal):
                    raise AssertionError("batch Popen.send_signal禁止")
            batch.subprocess = SimpleNamespace(Popen=MockProcess, TimeoutExpired=subprocess.TimeoutExpired)
            if mode == "run_after_wait_signal":
                # 正常wait後にresultを読もうとした瞬間の割込みを作る。
                original_safe_read = harness_run.safe_read
                def interrupt_result_read(path):
                    if Path(path).name == ".benchmark-result.json" and state["run_waited"]:
                        raise batch.BatchSignal(15)
                    return original_safe_read(path)
                harness_run.safe_read = interrupt_result_read
            try:
                with redirect_stdout(io.StringIO()):
                    batch.main()
            except batch.BatchSignal:
                assert mode in {"run_after_wait_signal", "summary_signal"}
            finally:
                if mode == "run_after_wait_signal":
                    harness_run.safe_read = originals[10]
            campaign = work / ("p5-" + compute_harness_fingerprint(HERE)[:16])
            summary_path = campaign / "batch-summary.json"
            summary = json.loads(summary_path.read_text())
            assert not signals
            if mode == "normal":
                assert summary["stopped_reason"] is None and summary["completed_records"] == 1
                assert summary["results"][0]["pass_preliminary"]
            elif mode in {"preflight_timeout", "preflight_signal", "preflight_before_launch_signal"}:
                assert summary["stopped_reason"] == ("infrastructure_error" if mode == "preflight_before_launch_signal" else "preflight_failure") and summary["completed_records"] == 0
                if mode == "preflight_before_launch_signal":
                    assert not launches and len(preflight_calls) == 1
                else:
                    assert len(launches) == 1 and launches[0].is_preflight
                    assert json.loads((campaign / "sandbox-preflight.json").read_text())["passed"] is False
                assert not (campaign / "run-01").exists()
            else:
                assert summary["stopped_reason"] == "infrastructure_error"
                if mode not in {"run_after_wait_signal", "summary_signal"}:
                    assert summary["completed_records"] == 1
                    record = summary["results"][0]
                    assert record["run_id"] == "run-01" and not record["pass_preliminary"]
                    if mode not in {"run_popen_signal", "run_before_popen_signal"}:
                        assert record["process_execution"]["exit_code"] != 0
                assert len([item for item in launches if not item.is_preflight]) == (0 if mode == "run_before_popen_signal" else 1)
            marker = campaign / "active-run.json"
            assert marker.exists() == (mode != "normal")
            if marker.exists():
                assert marker.stat().st_mode & 0o777 == 0o600
            assert not (campaign / "run-02").exists()
            for path in (campaign / ".evidence/.batch").iterdir() if (campaign / ".evidence/.batch").exists() else []:
                assert path.stat().st_mode & 0o777 == 0o600
                if path.suffix == ".json":
                    assert json.loads(path.read_text())["automatic_termination"] is False
            if mode != "normal":
                original_summary = summary_path.read_bytes()
                count = len(launches)
                try:
                    with redirect_stdout(io.StringIO()):
                        batch.main()
                except SystemExit:
                    pass
                else:
                    raise AssertionError("停止済みcampaignを再開した")
                assert len(launches) == count and summary_path.read_bytes() == original_summary
                assert len(preflight_calls) == (1 if mode not in {"preflight_timeout", "preflight_signal"} else 0)
    finally:
        (batch.WORK, batch.require_preflight, batch.subprocess, batch.scheduled_runs,
         batch.atomic_json, batch.wait_private_process, os.kill, os.killpg, Path.exists, Path.read_text, harness_run.safe_read) = originals
    print("batch process control: no kill/killpg/private files+wait/timeout root untouched/no run-02/summary stop/no resume/normal OK")


def monotonic_parent_wait_test(parent):
    """Popenに時間が掛かってもwaitは共通絶対期限から再計測する。"""
    parent.mkdir(parents=True, mode=0o700)
    original_popen, original_monotonic = batch.subprocess.Popen, batch.time.monotonic
    clock, observed = [1000.0], []
    class FakeProcess:
        pid = 12345
        def __init__(self, *_args, **_kwargs):
            clock[0] += 7.0
        def wait(self, timeout):
            observed.append(timeout)
            return 0
    try:
        batch.subprocess.Popen = FakeProcess
        batch.time.monotonic = lambda: clock[0]
        result = batch.wait_private_process(["fake"], parent, parent, "slow-popen", 1200,
                                            deadline_monotonic=1100.0)
        assert result["exit_code"] == 0 and observed == [93.0]
    finally:
        batch.subprocess.Popen, batch.time.monotonic = original_popen, original_monotonic
    print("batch deadline: Popen後にmonotonic絶対期限を再計測 OK")


def _synthetic_main():
    with tempfile.TemporaryDirectory(prefix="p5-analysis-", dir="/private/tmp",
                                     ignore_cleanup_errors=True) as temporary:
        fingerprint = compute_harness_fingerprint(HERE)
        campaign_dir = Path(temporary) / f"p5-{fingerprint[:16]}"
        summary, preflight, reviews = fixtures(campaign_dir)
        positive = decide(summary, preflight, reviews, campaign_dir)
        assert positive["campaign_complete"] and positive["all_runs_final_pass"]
        assert positive["quality_gate"]["status"] == "pass"
        assert positive["safety_gate"]["status"] == "pass"
        assert positive["cache_comparability"]["status"] == "comparable"
        assert positive["speed_target"]["status"] == "achieved"
        assert positive["speed_target"]["ratio_median"] == 0.7
        assert positive["decision"] == "adopt"
        assert positive["usage"]["totals"]["cached_input_tokens"] == 12000
        assert batch.stop_reason(summary["results"][0]) is None

        first = summary["results"][0]
        first_review = reviews["reviews"][0]
        stale_sidecar = dict(first_review)
        first["output_tokens"] = 101
        refresh_evidence(summary, reviews, campaign_dir)
        reviews["reviews"][0] = stale_sidecar
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        reviews["reviews"][0] = first_review
        first["output_tokens"] = 100
        refresh_evidence(summary, reviews, campaign_dir)

        result_path = campaign_dir / first["run_id"] / ".benchmark-result.json"
        original_result_bytes = harness_run.safe_read(result_path)
        result_path.write_text('{"changed":true}\n', encoding="utf-8")
        result_path.chmod(0o600)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        result_path.write_bytes(original_result_bytes)
        result_path.chmod(0o600)
        replay_path = campaign_dir / ".reviews" / f"{first['run_id']}-replay.json"
        original_replay_bytes = harness_run.safe_read(replay_path)
        replay_path.write_text('{"changed":true}\n', encoding="utf-8")
        replay_path.chmod(0o600)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        replay_path.write_bytes(original_replay_bytes)
        replay_path.chmod(0o600)

        accepted_change = campaign_dir / ".accepted" / first["run_id"] / "changed.txt"
        accepted_change.write_text("tampered", encoding="utf-8")
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        accepted_change.unlink()
        late_answer = campaign_dir / ".accepted" / first["run_id"] / ".benchmark-answer.txt"
        late_answer.write_text("late change", encoding="utf-8")
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        late_answer.unlink()
        old_fingerprint = summary["fingerprint"]
        summary["fingerprint"] = reviews["fingerprint"] = old_fingerprint[:16] + "0" * 48
        try:
            decide(summary, preflight, reviews, campaign_dir)
        except analyze.AnalysisError as error:
            assert "current shared harness fingerprint" in str(error)
        else:
            raise AssertionError("旧fingerprintの採用を拒否しなかった")
        summary["fingerprint"] = reviews["fingerprint"] = old_fingerprint

        first = summary["results"][0]
        first_raw = campaign_dir / ".evidence" / first["run_id"] / "events.raw.jsonl"
        original_raw = first_raw.read_bytes()
        original_event, original_attempt = first["event_audit"], first["attempt_policy"]
        unknown_events = [json.loads(line) for line in original_raw.splitlines()]
        unknown_events[-1:-1] = [
            {"type": "item.started", "item": {"type": "command_execution", "id": "cmd1",
                                               "command": "python3 -c 'print(1)'", "status": "in_progress"}},
            {"type": "item.completed", "item": {"type": "command_execution", "id": "cmd1",
                                                 "command": "python3 -c 'print(1)'", "status": "completed",
                                                 "exit_code": 0, "aggregated_output": "1"}},
        ]
        first_raw.write_text("".join(json.dumps(event) + "\n" for event in unknown_events), encoding="utf-8")
        first_raw.chmod(0o600)
        spec = harness_run.canonical_execution_spec(campaign_dir / first["run_id"],
                                                    analyze._task_for_record(first), harness_run.CLI_VERSION,
                                                    summary["fingerprint"], phase="model")
        classified = harness_run.safe_events(first_raw.read_text(encoding="utf-8"),
                                             expected_cwd=campaign_dir / first["run_id"],
                                             expected_env=spec["env"])
        assert classified["event_audit"]["passed"] is True
        assert classified["attempt_policy"]["status"] == "unknown"
        first["event_audit"] = classified["event_audit"]
        first["attempt_policy"] = classified["attempt_policy"]
        first["env_canary_evidence"] = classified["env_canary_evidence"]
        first["safety_gate"] = {"status": "fail", "passed": False}
        first["raw_event_evidence"]["sha256"] = reviews["reviews"][0]["raw_event_sha256"] = hashlib.sha256(first_raw.read_bytes()).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)
        resolved_run = analyze.gate_record(first, reviews["reviews"][0], True, campaign_dir)
        assert resolved_run["final_pass"] is True
        assert resolved_run["independently_resolved_unknown"] is True
        incomplete_summary = {**summary, "results": [first], "stopped_reason": "attempt_policy_not_pass"}
        incomplete_reviews = {**reviews, "reviews": [reviews["reviews"][0]]}
        assert decide(incomplete_summary, preflight, incomplete_reviews, campaign_dir)["decision"] == "incomplete"
        assert batch.stop_reason(first) == "attempt_policy_not_pass"
        batch_work = Path(temporary) / "batch-stop/formal"
        first_file = batch_work / summary["campaign"] / first["run_id"] / ".benchmark-result.json"
        batch.atomic_json(first_file, first)
        original_work, original_preflight, original_subprocess = batch.WORK, batch.require_preflight, batch.subprocess
        original_probe = probe_v16.require_final_probe
        try:
            batch.WORK = batch_work
            batch.require_preflight = lambda _campaign_dir, _expected_binding, _deadline=None: None
            probe_v16.require_final_probe = lambda fingerprint: {"fingerprint": fingerprint, "state": "synthetic_pass"}
            def unexpected_model_start(*_args, **_kwargs):
                raise AssertionError("unknown後に次runを起動した")
            batch.subprocess = SimpleNamespace(Popen=unexpected_model_start)
            with redirect_stdout(io.StringIO()):
                batch.main()
            batch_summary = json.loads((batch_work / summary["campaign"] / "batch-summary.json").read_text(encoding="utf-8"))
            assert batch_summary["completed_records"] == 1
            assert batch_summary["stopped_reason"] == "attempt_policy_not_pass"
            assert not (batch_work / summary["campaign"] / "run-02").exists()
        finally:
            batch.WORK, batch.require_preflight, batch.subprocess = original_work, original_preflight, original_subprocess
            probe_v16.require_final_probe = original_probe
        first["attempt_policy"] = {"status": "fail", "passed": False}
        assert batch.stop_reason(first) == "attempt_policy_not_pass"
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        first_raw.write_bytes(original_raw)
        first_raw.chmod(0o600)
        first["event_audit"], first["attempt_policy"] = original_event, original_attempt
        first["safety_gate"] = {"status": "pass", "passed": True}
        first["raw_event_evidence"]["sha256"] = reviews["reviews"][0]["raw_event_sha256"] = hashlib.sha256(original_raw).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)

        raw = campaign_dir / ".evidence" / summary["results"][0]["run_id"] / "events.raw.jsonl"
        raw_bytes = raw.read_bytes()
        raw.unlink()
        missing_raw = decide(summary, preflight, reviews, campaign_dir)
        assert missing_raw["safety_gate"]["status"] == "fail"
        assert missing_raw["decision"] != "adopt"
        raw.write_bytes(raw_bytes)
        raw.chmod(0o600)
        reviews["reviews"][0]["raw_event_sha256"] = "0" * 64
        mismatch = decide(summary, preflight, reviews, campaign_dir)
        assert mismatch["decision"] != "adopt"
        reviews["reviews"][0]["raw_event_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        reviews["reviews"][0]["event_audit_reproduced"] = False
        no_replay = decide(summary, preflight, reviews, campaign_dir)
        assert no_replay["decision"] != "adopt"
        reviews["reviews"][0]["event_audit_reproduced"] = True
        reviews["reviews"][0]["attempt_policy_pass"] = False
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        reviews["reviews"][0]["attempt_policy_pass"] = True
        invalid_raw = raw.read_bytes()
        raw.write_bytes(b"not-json\n")
        raw.chmod(0o600)
        first = summary["results"][0]
        first["raw_event_evidence"]["sha256"] = reviews["reviews"][0]["raw_event_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)
        replay_path = campaign_dir / ".reviews" / f"{first['run_id']}-replay.json"
        forged = json.loads(harness_run.safe_read(replay_path))
        forged["event_audit"] = first["event_audit"]
        forged["attempt_policy"] = first["attempt_policy"]
        forged["env_canary_evidence"] = first["env_canary_evidence"]
        batch.atomic_json(replay_path, forged)
        reviews["reviews"][0]["replay_report_sha256"] = hashlib.sha256(harness_run.safe_read(replay_path)).hexdigest()
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        raw.write_bytes(invalid_raw)
        raw.chmod(0o600)
        first["raw_event_evidence"]["sha256"] = reviews["reviews"][0]["raw_event_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)

        model = summary["results"][0]["isolation_gate"]["binding"]
        old_tool = model.pop("tool_environment")
        assert decide(summary, preflight, reviews, campaign_dir)["safety_gate"]["status"] == "fail"
        model["tool_environment"] = old_tool
        refresh_evidence(summary, reviews, campaign_dir)
        summary["results"][0]["isolation_gate"]["preflight_bound"] = False
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        summary["results"][0]["isolation_gate"]["preflight_bound"] = True
        refresh_evidence(summary, reviews, campaign_dir)
        validation = summary["results"][0]["validation"]
        derived = validation.pop("derived_from_model_profile_sha256")
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        validation["derived_from_model_profile_sha256"] = derived
        refresh_evidence(summary, reviews, campaign_dir)

        first = summary["results"][0]
        isolation = first["isolation_gate"]
        canonical_model = isolation["binding"]
        preflight_path = campaign_dir / first["run_id"] / ".benchmark-isolation.json"
        original_preflight = harness_run.safe_read(preflight_path)
        forged_model = dict(canonical_model)
        forged_model["codex_executable"] = {"realpath": "/usr/bin/true", "sha256": HASH}
        isolation["binding"] = isolation["preflight_binding"] = forged_model
        forged_preflight = json.loads(original_preflight)
        forged_preflight["binding"] = forged_model
        for case in forged_preflight["cases"]:
            case["binding_sha256"] = harness_run.canonical_digest(forged_model)
        batch.atomic_json(preflight_path, forged_preflight)
        first["preflight_evidence_sha256"] = hashlib.sha256(harness_run.safe_read(preflight_path)).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        forged_model["codex_executable"] = canonical_model["codex_executable"]
        forged_model["tool_environment"] = {"keys": ["PATH"], "sha256": HASH}
        batch.atomic_json(preflight_path, forged_preflight)
        first["preflight_evidence_sha256"] = hashlib.sha256(harness_run.safe_read(preflight_path)).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        isolation["binding"] = isolation["preflight_binding"] = canonical_model
        preflight_path.write_bytes(original_preflight)
        preflight_path.chmod(0o600)
        first["preflight_evidence_sha256"] = hashlib.sha256(original_preflight).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)

        damaged_preflight = json.loads(original_preflight)
        damaged_preflight["cases"] = [case for case in damaged_preflight["cases"]
                                       if case["name"] != "network_connect"]
        batch.atomic_json(preflight_path, damaged_preflight)
        first["preflight_evidence_sha256"] = hashlib.sha256(harness_run.safe_read(preflight_path)).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        preflight_path.write_bytes(original_preflight)
        preflight_path.chmod(0o600)
        first["preflight_evidence_sha256"] = hashlib.sha256(original_preflight).hexdigest()
        refresh_evidence(summary, reviews, campaign_dir)
        isolation["env_canary_pass"] = False
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        isolation["env_canary_pass"] = True
        first["residual_process_evidence"]["model"]["remaining_count"] = 1
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        first["residual_process_evidence"]["model"]["remaining_count"] = 0
        refresh_evidence(summary, reviews, campaign_dir)

        for record in summary["results"]:
            if record["task_id"] == "C1" and record["condition"] == "B":
                record["cached_input_tokens"] = 900
        refresh_evidence(summary, reviews, campaign_dir)
        cache_diff = decide(summary, preflight, reviews, campaign_dir)
        assert cache_diff["cache_comparability"]["status"] == "unknown"
        assert cache_diff["speed_target"]["status"] == "unknown"
        for record in summary["results"]:
            record["cached_input_tokens"] = 500
        del summary["results"][0]["cached_input_tokens"]
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["speed_target"]["status"] == "unknown"
        summary["results"][0]["cached_input_tokens"] = 500
        refresh_evidence(summary, reviews, campaign_dir)

        slots = [slot["run_id"] for slot in batch.scheduled_runs()]
        assert len(slots) == len(set(slots)) == 24 and all(len(slot) == 6 for slot in slots)
        mapping_path = campaign_dir / "run-slot-mapping.json"
        mapping = batch.load_or_create_mapping(mapping_path, summary["campaign"], summary["fingerprint"])
        assert mapping == batch.scheduled_runs()
        assert mapping_path.stat().st_mode & 0o777 == 0o600
        assert batch.record_matches_slot(summary["results"][0], summary["campaign"],
                                         summary["fingerprint"], mapping[0])
        assert not batch.record_matches_slot(summary["results"][0], summary["campaign"],
                                             summary["fingerprint"], mapping[1])
        assert campaign_dir / slots[0] / ".benchmark-result.json" != campaign_dir / "C1-A-1" / ".benchmark-result.json"
        try:
            batch.load_or_create_mapping(mapping_path, summary["campaign"], "e" * 64)
        except ValueError:
            pass
        else:
            raise AssertionError("resumeのfingerprint不一致を拒否しなかった")
        summary["results"][0]["run_id"] = "run-24"
        try:
            decide(summary, preflight, reviews, campaign_dir)
        except analyze.AnalysisError:
            pass
        else:
            raise AssertionError("opaque slot mapping不一致を拒否しなかった")
        summary["results"][0]["run_id"] = "run-01"
        private = campaign_dir / "aggregate.json"
        batch.atomic_json(private, positive)
        assert private.stat().st_mode & 0o777 == 0o600
        markdown = analyze.public_markdown(positive)
        assert "/private/" not in markdown and "/Users/" not in markdown
        batch_process_control_tests(Path(temporary) / "batch-process-control")
        monotonic_parent_wait_test(Path(temporary) / "monotonic-parent-wait")
    print("P5 analysis selftest: raw/review/binding/opaque/cache/4gate OK")


def main():
    os.umask(0o077)
    # 実runtimeの型・bytes・改変検知はsecurity selftestが担当する。
    # ここでは開始時の実bindingを一度確認し、合成24runの集計契約だけを検証する。
    # productionの毎phase再hashを変更せず、test内の差替えは終了時に戻す。
    actual_runtime = fingerprint_module.compute_python_runtime_binding()
    frozen_json = json.dumps(actual_runtime, sort_keys=True)
    original_shared = fingerprint_module.compute_python_runtime_binding
    original_runner = harness_run.compute_python_runtime_binding
    original_locations = harness_run.require_formal_locations
    original_source = harness_run.require_source_directory
    original_base = harness_run.prepare_formal_base
    original_batch_base = batch.formal_base
    original_batch_runtime = batch.compute_python_runtime_binding
    original_probe_guard = probe_v16.require_final_probe
    def frozen_runtime():
        return json.loads(frozen_json)
    try:
        fingerprint_module.compute_python_runtime_binding = frozen_runtime
        harness_run.compute_python_runtime_binding = frozen_runtime
        # 集計の合成caseはprivate tmpに置く。正式配置guardはsecurity selftestで検証する。
        harness_run.require_formal_locations = lambda *_args: None
        harness_run.require_source_directory = lambda: None
        harness_run.prepare_formal_base = lambda: batch.WORK.parent
        batch.formal_base = lambda: batch.WORK.parent
        batch.compute_python_runtime_binding = frozen_runtime
        probe_v16.require_final_probe = lambda fingerprint: {"fingerprint": fingerprint, "state": "synthetic_pass"}
        _synthetic_main()
    finally:
        fingerprint_module.compute_python_runtime_binding = original_shared
        harness_run.compute_python_runtime_binding = original_runner
        harness_run.require_formal_locations = original_locations
        harness_run.require_source_directory = original_source
        harness_run.prepare_formal_base = original_base
        batch.formal_base = original_batch_base
        batch.compute_python_runtime_binding = original_batch_runtime
        probe_v16.require_final_probe = original_probe_guard


if __name__ == "__main__":
    main()
