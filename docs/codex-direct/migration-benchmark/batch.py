#!/usr/bin/env python3
"""P5のABBA/BAABを上限付きで逐次実行する。"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

from harness_fingerprint import (compute_harness_fingerprint, compute_python_runtime_binding,
                                 compute_codex_executable_binding, compute_driver_executable_binding,
                                 compute_driver_config_binding, formal_base)
import run as harness_run

HERE = Path(__file__).resolve().parent
WORK = formal_base() / "formal"
TASKS = ["C1", "C2", "C3", "C4", "C5", "C6"]
GLOBAL_PREFLIGHT_SECONDS = 315
RUN_PARENT_SECONDS = 1200
RUN_CHILD_GRACE_SECONDS = 60
FINALIZATION_GRACE_SECONDS = 300
LIMIT_SECONDS = 24 * RUN_PARENT_SECONDS + GLOBAL_PREFLIGHT_SECONDS + FINALIZATION_GRACE_SECONDS
RETENTION_DAYS = 14


def scheduled_runs():
    schedule = []
    for index, task in enumerate(TASKS):
        order = "ABBA" if index % 2 == 0 else "BAAB"
        used = {"A": 0, "B": 0}
        for condition in order:
            used[condition] += 1
            schedule.append({"run_id": f"run-{len(schedule) + 1:02d}",
                             "task_id": task, "condition": condition, "repeat": used[condition]})
    return schedule


def load_or_create_mapping(path, campaign, fingerprint):
    mapping = {"schema": 1, "campaign": campaign, "fingerprint": fingerprint,
               "runs": scheduled_runs()}
    if os.path.lexists(path):
        if json.loads(harness_run.safe_read(path)) != mapping:
            raise ValueError("run slot mappingが現行schedule/fingerprintと不一致")
    else:
        atomic_json(path, mapping)
    return mapping["runs"]


def secure_mkdir(path):
    """fdを介して0700のprivate directoryを作成・確認する。"""
    path = Path(path)
    fd = harness_run._open_directory(path, create=True)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise RuntimeError(f"private directoryのowner/modeが不正です: {path}")
    finally:
        os.close(fd)
    return path


def atomic_json(path, value, *, forbidden_values=()):
    """検証したdirectory fdとO_NOFOLLOWを用いて0600 JSONを保存する。"""
    path = Path(path)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    harness_run.assert_artifact_clean(payload, forbidden_values)
    secure_mkdir(path.parent)
    harness_run._write_private(path, payload)
    directory_fd = harness_run._open_directory(path.parent)
    try:
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            info = os.fstat(file_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                    info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
                raise RuntimeError("保存したJSONのtype/owner/modeが不正です")
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def remove_private_file(path):
    """検証したprivate directory fdから通常fileだけを消す。"""
    path = Path(path)
    directory_fd = harness_run._open_directory(path.parent)
    try:
        info = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimeError("削除対象のtype/owner/modeが不正です")
        os.unlink(path.name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def campaign_binding(campaign_dir, fingerprint, python_runtime, codex_executable,
                     driver_executable, driver_config):
    """開始時のCLI/runtimeとprivate directory identityを固定する。"""
    value = {"schema": 1, "fingerprint": fingerprint,
             "codex_executable": codex_executable, "python_runtime": python_runtime,
             "driver_executable": driver_executable, "driver_config": driver_config,
             "private_directories": harness_run.private_directory_identity(campaign_dir)}
    value["binding_sha256"] = harness_run.canonical_digest(value)
    return value


def require_campaign_binding(campaign_dir, expected):
    """preflight/run起動境界で固定値と保存file・現物を再照合する。"""
    harness_run.require_formal_locations(WORK, campaign_dir)
    binding_file = campaign_dir / "campaign-binding.json"
    saved = harness_run.load_campaign_binding(binding_file, campaign_dir, expected["fingerprint"])["record"]
    if saved != expected:
        raise RuntimeError("campaign binding fileが開始時期待値と不一致")
    current = campaign_binding(campaign_dir, expected["fingerprint"],
                               compute_python_runtime_binding(), compute_codex_executable_binding(),
                               compute_driver_executable_binding(), compute_driver_config_binding())
    if current != expected:
        raise RuntimeError("campaign runtime/CLI/private directory identityが変更されました")
    return binding_file


def private_artifact_policy(campaign, fingerprint, campaign_dir, now=None):
    now = time.time() if now is None else now
    return {
        "schema": 1,
        "campaign": campaign,
        "fingerprint": fingerprint,
        "classification": "private",
        "storage": "account_home_cache_only",
        "campaign_dir": str(campaign_dir),
        "raw_artifacts": {
            "prompt": "private_only",
            "answer": "private_only",
            "events": "private_only",
            "result": "private_only",
            "preflight": "private_only",
            "summary": "private_only",
        },
        "public_commit_prohibited": True,
        "retention_days": RETENTION_DAYS,
        "expires_epoch": now + RETENTION_DAYS * 24 * 60 * 60,
        "aggregate": {
            "path": str(campaign_dir / "aggregate.json"),
            "status": "pending_review",
            "delete_after_review": True,
            "review_complete_required": True,
            "explicit_extension_required_before_expiry": True,
        },
    }


def complete_record(record, campaign, fingerprint):
    return (record.get("fingerprint") == fingerprint and record.get("campaign") == campaign
            and all(key in record for key in ("ended_at", "validation", "cli_exit")))


def record_matches_slot(record, campaign, fingerprint, slot):
    return (complete_record(record, campaign, fingerprint) and
            all(record.get(key) == slot[key] for key in ("run_id", "task_id", "condition", "repeat")))


def infrastructure_record(task, condition, repeat, campaign, fingerprint, error, exit_code=None):
    return {"schema": 3, "campaign": campaign, "fingerprint": fingerprint, "task_id": task,
            "condition": condition, "repeat": repeat, "infrastructure_error": error,
            "exit_code": exit_code if exit_code is not None else "unknown",
            "pass_preliminary": False}


def stop_reason(record):
    """監査不能・利用失敗・infra失敗なら追加のモデルrunを止める。"""
    if record.get("infrastructure_error"):
        return "infrastructure_error"
    if record.get("cli_exit") != 0:
        return "cli_not_successful"
    audit = record.get("event_audit") if isinstance(record.get("event_audit"), dict) else {}
    safety = record.get("safety_gate") if isinstance(record.get("safety_gate"), dict) else {}
    if audit.get("status") != "pass" or audit.get("passed") is not True:
        return "event_audit_not_pass"
    isolation = record.get("isolation_gate") if isinstance(record.get("isolation_gate"), dict) else {}
    if isolation.get("status") != "pass" or isolation.get("passed") is not True or isolation.get("preflight_bound") is not True:
        return "isolation_gate_not_pass"
    attempt = record.get("attempt_policy") if isinstance(record.get("attempt_policy"), dict) else {}
    if attempt.get("status") != "pass" or attempt.get("passed") is not True:
        return "attempt_policy_not_pass"
    if safety.get("status") != "pass" or safety.get("passed") is not True:
        return "safety_gate_not_pass"
    acceptance = record.get("acceptance_gate") if isinstance(record.get("acceptance_gate"), dict) else {}
    if acceptance.get("status") != "pass" or acceptance.get("passed") is not True:
        return "acceptance_gate_not_pass"
    return None


def load_clock(path, fingerprint, now=None, deadline_monotonic=None):
    now = time.time() if now is None else now
    if os.path.lexists(path):
        clock = json.loads(harness_run.safe_read(path))
        if (clock.get("fingerprint") != fingerprint or
                (deadline_monotonic is not None and clock.get("deadline_monotonic") != deadline_monotonic)):
            raise ValueError("campaign clock fingerprint不一致")
        return clock
    deadline_monotonic = (time.monotonic() + LIMIT_SECONDS if deadline_monotonic is None else deadline_monotonic)
    clock = {"fingerprint": fingerprint, "started_epoch": now,
             "deadline_epoch": now + max(0, deadline_monotonic - time.monotonic()),
             "deadline_monotonic": deadline_monotonic}
    atomic_json(path, clock)
    return clock


class BatchSignal(SystemExit):
    def __init__(self, signum):
        self.signum = signum
        super().__init__(128 + signum)


class PreflightFailure(RuntimeError):
    pass


def interrupt_handler(signum, _frame):
    raise BatchSignal(signum)


def wait_private_process(command, cwd, campaign_dir, label, timeout, *, deadline_monotonic=None):
    """private fileへ出力しleaderのwaitだけを行う。timeout/例外でkillしない。"""
    evidence = campaign_dir / ".evidence" / ".batch"
    directory = harness_run._open_directory(evidence, create=True)
    token = label + "-" + os.urandom(8).hex()
    paths = {name: evidence / f"{token}.{name}" for name in ("stdout", "stderr")}
    handles = []
    process = None
    code, error = "not_started", None
    try:
        for name in ("stdout", "stderr"):
            fd = os.open(paths[name].name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            os.fchmod(fd, 0o600)
            handles.append(os.fdopen(fd, "wb"))
        process = subprocess.Popen(command, cwd=cwd, stdout=handles[0], stderr=handles[1],
                                   stdin=None, start_new_session=True)
        try:
            remaining = timeout if deadline_monotonic is None else deadline_monotonic - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, 0)
            code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            code, error = "timeout", "実行完了未確認。自動終了せずcampaignを停止"
        except BatchSignal as interruption:
            code, error = f"signal:{interruption.signum}", "signal受信。自動終了せずcampaignを停止"
        except Exception:
            code, error = "wait_error", "process待機失敗。自動終了せずcampaignを停止"
    except OSError:
        code, error = "spawn_error", "process起動失敗。campaignを停止"
    finally:
        for handle in handles:
            handle.close()
        os.close(directory)
    complete = type(code) is int
    diagnostic_path = evidence / f"{token}.process.json"
    atomic_json(diagnostic_path, {"schema": 1, "label": label, "exit_code": code,
        "completion_confirmed": complete, "automatic_termination": False,
        "process_may_still_be_running": process is not None and not complete,
        "leader_pid_at_launch": process.pid if process is not None else None,
        "pid_current_ownership_unverified": True})
    return {"exit_code": code, "completion_confirmed": complete, "error": error,
            "stdout_relative_path": str(paths["stdout"].relative_to(campaign_dir)),
            "stderr_relative_path": str(paths["stderr"].relative_to(campaign_dir)),
            "diagnostic_relative_path": str(diagnostic_path.relative_to(campaign_dir)),
            "automatic_termination": False}


def require_preflight(campaign_dir, expected_binding, campaign_deadline_monotonic=None):
    """正常終了したpreflightだけを読み、不合格・timeoutならmodelを開始させない。"""
    preflight_file = campaign_dir / "sandbox-preflight.json"
    binding_file = require_campaign_binding(campaign_dir, expected_binding)
    preflight_deadline = min(time.monotonic() + GLOBAL_PREFLIGHT_SECONDS,
                            (campaign_deadline_monotonic or time.monotonic() + LIMIT_SECONDS) - FINALIZATION_GRACE_SECONDS)
    execution = wait_private_process([sys.executable, "-B", str(HERE / "sandbox_preflight.py"),
                                      "--expected-binding-file", str(binding_file),
                                      "--fingerprint", expected_binding["fingerprint"]],
                                     HERE, campaign_dir, "preflight", GLOBAL_PREFLIGHT_SECONDS,
                                     deadline_monotonic=preflight_deadline)
    require_campaign_binding(campaign_dir, expected_binding)
    if execution["exit_code"] != 0:
        atomic_json(preflight_file, {"passed": False, "infrastructure_error": "preflight_execution_failed",
                                     "process_execution": execution})
        raise PreflightFailure("sandbox preflightの正常終了未確認。モデルrunを開始しません")
    try:
        preflight_data = json.loads(harness_run.safe_read(campaign_dir / execution["stdout_relative_path"]))
        if not isinstance(preflight_data, dict):
            raise ValueError("preflight object required")
    except (OSError, RuntimeError, ValueError):
        preflight_data = {"passed": False, "raw_output_invalid": True}
    atomic_json(preflight_file, preflight_data)
    if preflight_data.get("passed") is not True:
        raise PreflightFailure("sandbox preflight不合格。モデルrunを開始しません")
    return preflight_data


def _main(campaign_deadline_monotonic=None):
    os.umask(0o077)
    signal.signal(signal.SIGTERM, interrupt_handler)
    signal.signal(signal.SIGINT, interrupt_handler)
    if campaign_deadline_monotonic is not None and (not math.isfinite(campaign_deadline_monotonic)
            or not 0 < campaign_deadline_monotonic - time.monotonic() <= LIMIT_SECONDS + 1):
        raise SystemExit("campaign monotonic deadlineが固定上限外です")
    if WORK != formal_base() / "formal":
        raise SystemExit("formal campaignの固定保存先が変更されました")
    harness_run.require_formal_locations(WORK)
    harness_run.prepare_formal_base()
    secure_mkdir(WORK)
    contracts = [HERE / f"b-contract/{repo}/AGENTS.md" for repo in ("agent_crew", "wealth_advisor")]
    skill = HERE / "b-contract/agent_crew/.agents/skills/fable-class/SKILL.md"
    b_index = HERE / "b-contract-index.json"
    a_index = HERE / "a-contract-index.json"
    if any(not contract.is_file() for contract in contracts) or not skill.is_file() or not b_index.is_file() or not a_index.is_file():
        raise SystemExit("P2確定版のB契約とfable-classが未固定です")
    fixed = json.loads(b_index.read_text(encoding="utf-8"))["files"]
    b_tree = HERE / "b-contract"
    actual = {str(path.relative_to(b_tree)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in b_tree.rglob("*") if path.is_file()}
    if fixed != actual or any(path.is_symlink() for path in b_tree.rglob("*")):
        raise SystemExit("B指示treeが固定indexと不一致")
    a_fixed = json.loads(a_index.read_text(encoding="utf-8"))["files"]
    a_tree = HERE / "a-contract"
    a_actual = {str(path.relative_to(a_tree)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in a_tree.rglob("*") if path.is_file()}
    if a_fixed != a_actual or any(path.is_symlink() for path in a_tree.rglob("*")):
        raise SystemExit("A補足指示treeが固定indexと不一致")
    python_runtime = compute_python_runtime_binding()
    codex_executable = compute_codex_executable_binding()
    driver_executable = compute_driver_executable_binding()
    driver_config = compute_driver_config_binding()
    fingerprint = compute_harness_fingerprint(HERE, python_runtime_binding=python_runtime,
                                              codex_executable_binding=codex_executable,
                                              driver_executable_binding=driver_executable)
    import probe_v19
    probe_v19.require_final_probe(fingerprint)
    campaign = f"p5-{fingerprint[:16]}"
    campaign_dir = secure_mkdir(WORK / campaign)
    expected_binding = campaign_binding(campaign_dir, fingerprint, python_runtime, codex_executable,
                                        driver_executable, driver_config)
    binding_file = campaign_dir / "campaign-binding.json"
    if os.path.lexists(binding_file):
        if json.loads(harness_run.safe_read(binding_file)) != expected_binding:
            raise SystemExit("既存campaign bindingが開始時期待値と不一致")
    else:
        atomic_json(binding_file, expected_binding)
    require_campaign_binding(campaign_dir, expected_binding)
    active = campaign_dir / "active-run.json"
    if os.path.lexists(active):
        raise SystemExit("active operation markerが残存。子run rootを読まず自動再開を拒否します")
    policy_file = campaign_dir / "private-artifact-policy.json"
    if not os.path.lexists(policy_file):
        atomic_json(policy_file, private_artifact_policy(campaign, fingerprint, campaign_dir))
    else:
        policy = json.loads(harness_run.safe_read(policy_file))
        if (policy.get("campaign") != campaign or policy.get("fingerprint") != fingerprint
                or policy.get("campaign_dir") != str(campaign_dir)
                or policy.get("storage") != "account_home_cache_only"):
            raise SystemExit("既存private artifact policyがcampaignと不一致")
    clock_file = campaign_dir / "campaign-clock.json"
    clock = load_clock(clock_file, fingerprint, deadline_monotonic=campaign_deadline_monotonic)
    summary_file = campaign_dir / "batch-summary.json"
    previous = json.loads(harness_run.safe_read(summary_file)) if os.path.lexists(summary_file) else None
    if previous and previous.get("fingerprint") != fingerprint:
        raise SystemExit("campaign fingerprint不一致。別campaignとして実行してください")
    if previous and previous.get("stopped_reason"):
        raise SystemExit("停止済みcampaignは自動再開しません。子run rootを読み直さず監査待ちです")
    schedule = load_or_create_mapping(campaign_dir / "run-slot-mapping.json", campaign, fingerprint)
    results = []
    stopped_reason = None
    atomic_json(active, {"phase": "preflight", "campaign": campaign,
                         "fingerprint": fingerprint, "campaign_binding_file": str(binding_file),
                         "campaign_binding_sha256": expected_binding["binding_sha256"],
                         "codex_executable": codex_executable, "driver_executable": driver_executable,
                         "driver_config": driver_config, "started_epoch": time.time()})
    try:
        require_preflight(campaign_dir, expected_binding, clock["deadline_monotonic"])
        preliminary = {"schema": 2, "campaign": campaign, "fingerprint": fingerprint,
                       "campaign_binding_file": str(binding_file),
                       "campaign_binding_sha256": expected_binding["binding_sha256"],
                       "codex_executable": codex_executable,
                       "driver_executable": driver_executable, "driver_config": driver_config,
                       "planned_runs": len(schedule), "completed_records": 0,
                       "schedule": schedule, "results": [], "stopped_reason": None}
        atomic_json(summary_file, preliminary)
        remove_private_file(active)
    except (PreflightFailure, BatchSignal, Exception) as exc:
        stopped_reason = "preflight_failure" if isinstance(exc, PreflightFailure) else "infrastructure_error"
    for slot in schedule if stopped_reason is None else []:
        task, condition, repeat, run_id = (slot["task_id"], slot["condition"],
                                            slot["repeat"], slot["run_id"])
        remaining = clock["deadline_monotonic"] - time.monotonic()
        if remaining < RUN_PARENT_SECONDS + FINALIZATION_GRACE_SECONDS:
            stopped_reason = "campaign_deadline"
            break
        require_campaign_binding(campaign_dir, expected_binding)
        run_file = campaign_dir / run_id / ".benchmark-result.json"
        if run_file.exists():
            recorded = json.loads(harness_run.safe_read(run_file))
            if not record_matches_slot(recorded, campaign, fingerprint, slot):
                raise SystemExit(f"resume不一致: {run_file}")
            results.append(recorded)
            stopped_reason = stop_reason(recorded)
            if stopped_reason:
                break
            continue
        if run_file.parent.exists():
            record = infrastructure_record(task, condition, repeat, campaign, fingerprint,
                                           "部分runが存在。自動再実行せず監査待ち")
            record["run_id"] = run_id
            results.append(record)
            stopped_reason = stop_reason(record)
            break
        remaining = clock["deadline_monotonic"] - time.monotonic()
        if remaining < RUN_PARENT_SECONDS + FINALIZATION_GRACE_SECONDS:
            stopped_reason = "campaign_deadline"
            break
        atomic_json(active, {"phase": "run", "task": task, "condition": condition,
                             "repeat": repeat, "run_id": run_id, "started_epoch": time.time(),
                             "campaign": campaign, "fingerprint": fingerprint,
                             "campaign_binding_file": str(binding_file),
                             "campaign_binding_sha256": expected_binding["binding_sha256"],
                             "codex_executable": codex_executable,
                             "driver_executable": driver_executable, "driver_config": driver_config})
        try:
            require_campaign_binding(campaign_dir, expected_binding)
            parent_deadline = min(time.monotonic() + RUN_PARENT_SECONDS,
                                  clock["deadline_monotonic"] - FINALIZATION_GRACE_SECONDS)
            child_deadline = parent_deadline - RUN_CHILD_GRACE_SECONDS
            if child_deadline <= time.monotonic():
                raise RuntimeError("run開始前に子run deadlineが切れました")
            execution = wait_private_process(
                [sys.executable, "-B", str(HERE / "run.py"), task, condition, str(repeat), "--run-id", run_id,
                 "--campaign", str(campaign_dir), "--fingerprint", fingerprint,
                 "--expected-binding-file", str(binding_file),
                 "--deadline-monotonic", str(child_deadline)],
                HERE.parents[2], campaign_dir, run_id, RUN_PARENT_SECONDS,
                deadline_monotonic=parent_deadline)
            require_campaign_binding(campaign_dir, expected_binding)
            code = execution["exit_code"]
            if code == 0:
                if run_file.exists():
                    record = json.loads(harness_run.safe_read(run_file))
                    if not record_matches_slot(record, campaign, fingerprint, slot):
                        raise ValueError("run resultがslot/campaignと不一致")
                else:
                    record = infrastructure_record(task, condition, repeat, campaign, fingerprint,
                                                   "正常終了後にrun resultがありません", code)
                    record["run_id"] = run_id
            else:
                # 非zero/timeout時は子run rootを読まない。
                record = infrastructure_record(task, condition, repeat, campaign, fingerprint,
                                               execution["error"] or "子runが正常終了しませんでした", code)
                record["run_id"] = run_id
                record["process_execution"] = execution
        except (BatchSignal, Exception) as exc:
            # Popen前後や正常wait後のsignalでもmarkerを維持し、子rootは読まない。
            record = infrastructure_record(task, condition, repeat, campaign, fingerprint,
                                           "batch operation interrupted", "signal" if isinstance(exc, BatchSignal) else "exception")
            record["run_id"] = run_id
        results.append(record)
        print(f"{task} {condition}{repeat}: {results[-1].get('pass_preliminary', 'infra_error')}", flush=True)
        stopped_reason = stop_reason(record)
        summary = {"schema": 2, "campaign": campaign, "fingerprint": fingerprint,
                   "campaign_binding_file": str(binding_file),
                   "campaign_binding_sha256": expected_binding["binding_sha256"],
                   "codex_executable": codex_executable,
                   "driver_executable": driver_executable, "driver_config": driver_config,
                   "planned_runs": len(schedule), "completed_records": len(results),
                   "elapsed_seconds": round(time.time() - clock["started_epoch"], 3),
                   "schedule": schedule, "run_slot_mapping_file": str(campaign_dir / "run-slot-mapping.json"),
                   "results": results, "stopped_reason": stopped_reason,
                   "stop_boundary": "after_current_run_before_next_run"}
        summary["preflight_file"] = str(campaign_dir / "sandbox-preflight.json")
        summary["clock_file"] = str(clock_file)
        summary["active_file"] = str(active)
        summary["private_artifact_policy_file"] = str(policy_file)
        summary["aggregate_policy"] = json.loads(harness_run.safe_read(policy_file))["aggregate"]
        atomic_json(summary_file, summary)
        if stopped_reason is None:
            remove_private_file(active)
        if stopped_reason:
            break
    summary = {"schema": 2, "planned_runs": len(schedule), "completed_records": len(results),
               "campaign": campaign, "fingerprint": fingerprint,
               "campaign_binding_file": str(binding_file),
               "campaign_binding_sha256": expected_binding["binding_sha256"],
               "codex_executable": codex_executable,
               "driver_executable": driver_executable, "driver_config": driver_config,
               "elapsed_seconds": round(time.time() - clock["started_epoch"], 3),
               "B_contract_sha256": {contract.parent.name: hashlib.sha256(contract.read_bytes()).hexdigest()
                                     for contract in contracts},
               "B_skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
               "schedule": schedule, "run_slot_mapping_file": str(campaign_dir / "run-slot-mapping.json"),
               "results": results, "stopped_reason": stopped_reason,
               "stop_boundary": "after_current_run_before_next_run"}
    summary["preflight_file"] = str(campaign_dir / "sandbox-preflight.json")
    summary["clock_file"] = str(clock_file)
    summary["active_file"] = str(campaign_dir / "active-run.json")
    summary["private_artifact_policy_file"] = str(policy_file)
    summary["aggregate_policy"] = json.loads(harness_run.safe_read(policy_file))["aggregate"]
    atomic_json(summary_file, summary)
    print(f"summary: {summary_file}", flush=True)


def main(campaign_deadline_monotonic=None):
    try:
        return _main(campaign_deadline_monotonic)
    except BatchSignal:
        # signalがwait後からsummary確定までに届いても、active markerを残して再開を拒否する。
        try:
            fingerprint = compute_harness_fingerprint(HERE)
            campaign_dir = WORK / f"p5-{fingerprint[:16]}"
            marker = campaign_dir / "active-run.json"
            if os.path.lexists(marker):
                summary_file = campaign_dir / "batch-summary.json"
                summary = json.loads(harness_run.safe_read(summary_file)) if summary_file.exists() else {
                    "schema": 2, "campaign": campaign_dir.name, "fingerprint": fingerprint,
                    "results": [], "completed_records": 0}
                summary["stopped_reason"] = "infrastructure_error"
                summary["interruption"] = "signal_during_active_operation"
                atomic_json(summary_file, summary)
        except Exception:
            # markerが永続化済みなら次回起動時の安全停止は維持される。
            pass
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-deadline-monotonic", required=True, type=float)
    arguments = parser.parse_args()
    main(arguments.campaign_deadline_monotonic)
