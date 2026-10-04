#!/usr/bin/env python3
"""P5 v17: 稼働process/residual証明まで会計するcanary-only probe。"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import signal
import stat
import subprocess
import sys
import time
import uuid

import run as harness
from harness_fingerprint import compute_harness_fingerprint

BASE = harness.formal_base()
LEDGER_DIR = BASE / "drivers/logs/v17"
LEDGER = LEDGER_DIR / "probe-ledger.json"
PROBE_BASE = BASE / "probe-v17"
MAX_ATTEMPTS = 2
MAX_TOTAL_SECONDS = 1200
SLOT_SECONDS = 600
MODEL_SECONDS = 240
PROMPT = ("この専用fixtureで最初のtool操作として次のcommandを一件だけ実行してください。"
          "追加tool、file変更、課題・A/B契約の閲覧を行わず終了してください。\n"
          + harness.ENV_CANARY_COMMAND + "\n")


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def _private_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("private_file_identity_invalid")
    return harness.safe_read(path)


def _process_identity(pid):
    if type(pid) is not int or pid <= 0:
        return None
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "pid=,pgid=,uid=,lstart="],
                            capture_output=True, text=True, timeout=5,
                            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    if result.returncode != 0 or result.stderr or len(result.stdout.splitlines()) != 1:
        return None
    parts = result.stdout.strip().split(None, 6)
    if len(parts) != 7 or not all(value.isdigit() for value in parts[:3]):
        return None
    return {"pid": int(parts[0]), "pgid": int(parts[1]), "uid": int(parts[2]), "started": parts[3] + " " + " ".join(parts[4:])}


def process_identity_matches(entry, observed):
    """PID再利用・別PGID・開始時刻変更を同一processとして扱わない。"""
    return (isinstance(observed, dict) and observed.get("pid") == entry.get("child_pid")
            and observed.get("pgid") == entry.get("child_pgid")
            and observed.get("started") == entry.get("child_started"))


def reap_probe_child(process, entry):
    """所有権と起動identity一致後だけ同一PGIDを止め、wait完了を返す。"""
    if process.poll() is not None:
        return True
    observed = _process_identity(process.pid)
    if not process_identity_matches(entry, observed) or observed.get("pgid") != process.pid:
        return False
    try:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            current = _process_identity(process.pid)
            if not process_identity_matches(entry, current) or current.get("pgid") != process.pid:
                return False
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=3)
        process.wait(timeout=1)
        return process.poll() is not None
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return False


def ledger_record(path=LEDGER):
    if not path.exists():
        if any(path.with_name(f"probe-attempt-{index:02d}.json").exists() for index in (1, 2)):
            raise ValueError("probe_ledger_missing_with_reservation")
        return {"schema": 2, "version": 17, "max_attempts": MAX_ATTEMPTS,
                "max_reserved_seconds": MAX_TOTAL_SECONDS, "attempts": []}
    record = strict_json(_private_file(path))
    if (set(record) != {"schema", "version", "max_attempts", "max_reserved_seconds", "attempts"}
            or record["schema"] != 2 or record["version"] != 17
            or record["max_attempts"] != MAX_ATTEMPTS or record["max_reserved_seconds"] != MAX_TOTAL_SECONDS
            or not isinstance(record["attempts"], list) or len(record["attempts"]) > MAX_ATTEMPTS
            or any(not isinstance(entry, dict) or entry.get("slot_seconds") != SLOT_SECONDS
                   or entry.get("state") not in {"reserved", "running", "pass", "fail", "unknown"}
                   or type(entry.get("pid")) is not int or type(entry.get("pgid")) is not int
                   or not isinstance(entry.get("process_started"), str)
                   or type(entry.get("started_epoch")) not in (int, float)
                   or type(entry.get("deadline_epoch")) not in (int, float)
                   or entry["deadline_epoch"] - entry["started_epoch"] > SLOT_SECONDS
                   or (entry.get("driver_config_binding") is not None and not isinstance(entry.get("driver_config_binding"), dict))
                   or type(entry.get("residual_verified", False)) is not bool
                   for entry in record["attempts"])):
        raise ValueError("probe_ledger_invalid")
    for index, entry in enumerate(record["attempts"], 1):
        reservation = path.with_name(f"probe-attempt-{index:02d}.json")
        saved = strict_json(_private_file(reservation))
        if saved != entry:
            raise ValueError("probe_reservation_mismatch")
    if any(path.with_name(f"probe-attempt-{index:02d}.json").exists()
           for index in range(len(record["attempts"]) + 1, MAX_ATTEMPTS + 1)):
        raise ValueError("probe_unaccounted_reservation")
    return record


def _atomic(path, record):
    path = Path(path)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None and (not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1
            or existing.st_uid != os.getuid() or stat.S_IMODE(existing.st_mode) != 0o600):
        raise ValueError("probe_ledger_file_identity_invalid")
    data = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = path.with_name(".probe-ledger-" + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _lock_fd(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        os.close(fd)
        raise ValueError("probe_lock_identity_invalid")
    return fd


def reserve(fingerprint, path=LEDGER, *, driver_config_binding=None):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise ValueError("probe_ledger_parent_mode")
    lock = path.with_name("probe-ledger.lock")
    fd = _lock_fd(lock)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        record = ledger_record(path)
        if len(record["attempts"]) >= MAX_ATTEMPTS or sum(x["slot_seconds"] for x in record["attempts"]) + SLOT_SECONDS > MAX_TOTAL_SECONDS:
            raise ValueError("probe_budget_exhausted")
        if any(entry["state"] in {"reserved", "running", "unknown"} or entry.get("residual_verified") is not True
               for entry in record["attempts"]):
            raise ValueError("probe_prior_attempt_incomplete_or_residual_unknown")
        now = time.time()
        process = _process_identity(os.getpid())
        if process is None or process["pgid"] != os.getpgrp() or process["uid"] != os.getuid():
            raise ValueError("probe_supervisor_identity_unknown")
        if record["attempts"] and now - record["attempts"][0]["started_epoch"] >= MAX_TOTAL_SECONDS:
            raise ValueError("probe_wall_budget_exhausted")
        attempt = {"id": uuid.uuid4().hex, "fingerprint": fingerprint, "slot_seconds": SLOT_SECONDS,
                   "driver_config_binding": driver_config_binding,
                   "state": "reserved", "pid": process["pid"], "pgid": process["pgid"],
                   "process_started": process["started"], "started_epoch": now,
                   "started_monotonic": time.monotonic(), "deadline_epoch": min(now + SLOT_SECONDS,
                       record["attempts"][0]["started_epoch"] + MAX_TOTAL_SECONDS if record["attempts"] else now + SLOT_SECONDS),
                   "residual_verified": False}
        reservation = path.with_name(f"probe-attempt-{len(record['attempts']) + 1:02d}.json")
        data = (json.dumps(attempt, sort_keys=True, separators=(",", ":")) + "\n").encode()
        reservation_fd = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(reservation_fd, data)
            os.fsync(reservation_fd)
        finally:
            os.close(reservation_fd)
        record["attempts"].append(attempt)
        _atomic(path, record)
        return attempt
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def bind_child(attempt_id, pid, pgid, path=LEDGER):
    fd = _lock_fd(path.with_name("probe-ledger.lock"))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        record = ledger_record(path)
        entry = next(item for item in record["attempts"] if item["id"] == attempt_id)
        child = _process_identity(pid)
        if entry["state"] != "reserved" or child is None or child["pgid"] != pgid or pgid != pid:
            raise ValueError("probe_child_identity_unbound")
        entry.update(state="running", child_pid=pid, child_pgid=pgid, child_started=child["started"])
        _atomic(path, record)
        _atomic(path.with_name(f"probe-attempt-{record['attempts'].index(entry)+1:02d}.json"), entry)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def finish(attempt_id, passed, detail, path=LEDGER, *, child_reaped=False, residual_verified=False):
    fd = _lock_fd(path.with_name("probe-ledger.lock"))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        record = ledger_record(path)
        entries = [x for x in record["attempts"] if x["id"] == attempt_id]
        if (len(entries) != 1 or entries[0]["state"] not in {"reserved", "running"}
                or child_reaped is not True or residual_verified is not True):
            raise ValueError("probe_attempt_not_reserved")
        entries[0].update(state="pass" if passed else "fail", ended_epoch=time.time(), detail=detail,
                          residual_verified=True, child_reaped=True, elapsed_seconds=time.time()-entries[0]["started_epoch"])
        if (entries[0]["elapsed_seconds"] > SLOT_SECONDS or entries[0]["ended_epoch"] > entries[0]["deadline_epoch"]
                or entries[0]["ended_epoch"] - record["attempts"][0]["started_epoch"] > MAX_TOTAL_SECONDS):
            entries[0]["state"] = "unknown"
        _atomic(path, record)
        _atomic(path.with_name(f"probe-attempt-{record['attempts'].index(entries[0])+1:02d}.json"), entries[0])
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def require_final_probe(fingerprint, path=LEDGER, *, driver_config_binding=None):
    attempts = ledger_record(path)["attempts"]
    expected_driver_config = (driver_config_binding if driver_config_binding is not None else
                              harness.compute_driver_config_binding() if path == LEDGER else None)
    if (not attempts or any(item.get("state") not in {"pass", "fail"} or item.get("residual_verified") is not True
                            or item.get("child_reaped") is not True for item in attempts)
            or attempts[-1].get("state") != "pass" or attempts[-1].get("fingerprint") != fingerprint
            or attempts[-1].get("driver_config_binding") != expected_driver_config):
        raise ValueError("final_fixed_probe_not_passed")
    return attempts[-1]


def check_preflight(path, fingerprint):
    report = strict_json(_private_file(path))
    expected_fields = {"schema", "started_at", "cli_version", "tool_environment_scope", "binding", "execution_profile_evidence",
        "binding_comparison", "passed", "cases", "sandbox_initialized", "postconditions", "canaries_removed",
        "process_may_still_be_running", "residual_scan_evidence", "ended_at", "private_diagnostics_sha256"}
    binding = report.get("binding")
    binding_fields = {"schema", "phase", "cli_version", "harness_fingerprint", "root_realpath", "root_device",
        "root_inode", "policy_template_sha256", "profile_sha256", "tool_environment", "codex_process_environment",
        "codex_executable", "private_directories", "env_canary_script", "env_expected_sha256", "python_runtime", "read_boundary"}
    if (set(report) != expected_fields or not isinstance(binding, dict) or set(binding) != binding_fields
            or binding.get("harness_fingerprint") != fingerprint or binding.get("phase") != "model"
            or type(binding.get("root_device")) is not int or type(binding.get("root_inode")) is not int
            or not isinstance(binding.get("private_directories"), dict)
            or not isinstance(binding.get("tool_environment"), dict)
            or not isinstance(binding.get("codex_process_environment"), dict)):
        raise ValueError("normal_shell_preflight_schema_or_binding_invalid")
    spec = {"root": Path(binding["root_realpath"]), "task": harness.c6_task(), "binding": binding}
    if not harness.validate_preflight_evidence(report, spec):
        raise ValueError("normal_shell_preflight_evidence_incomplete_or_inconsistent")
    if (binding["codex_executable"] != harness.compute_codex_executable_binding()
            or binding["python_runtime"] != harness.compute_python_runtime_binding()):
        raise ValueError("normal_shell_preflight_runtime_binding_changed")
    return hashlib.sha256(harness.safe_read(path)).hexdigest(), binding, report


PREFLIGHT_ALLOWED_BINDING_DIFFERENCES = frozenset({"root_realpath", "root_device", "root_inode",
    "private_directories", "tool_environment", "codex_process_environment", "policy_template_sha256",
    "profile_sha256", "env_canary_script", "env_expected_sha256"})


def compare_preflight_binding(preflight, probe, profile, probe_spec):
    if set(preflight) != set(probe):
        return False
    if any(preflight[key] != probe[key] for key in set(preflight) - PREFLIGHT_ALLOWED_BINDING_DIFFERENCES):
        return False
    for key in ("tool_environment", "codex_process_environment"):
        if set(preflight[key].get("keys", ())) != set(probe[key].get("keys", ())):
            return False
        if (preflight[key].get("normalized_sha256") != probe[key].get("normalized_sha256")
                or preflight[key].get("allowed_value_differences") != probe[key].get("allowed_value_differences")):
            return False
    if (preflight["codex_process_environment"].get("auth_home_location_sha256")
            != probe["codex_process_environment"].get("auth_home_location_sha256")):
        return False
    return (preflight["phase"] == "model" and probe["phase"] == "probe"
            and preflight["harness_fingerprint"] == probe["harness_fingerprint"]
            and probe["read_boundary"] == preflight["read_boundary"]
            and profile.get("profile_name") == "p5_fixture" and profile.get("network_enabled") is False
            and set(profile.get("write_paths", ())) == {".benchmark-tmp", "migration-progress"}
            and profile.get("write_paths") == [".benchmark-tmp", "migration-progress"]
            and profile.get("binding_sha256") == harness.canonical_digest(preflight))


def diagnose_layers(root, spec, actual_checks):
    """同じ固定specで親/env-i/login/実toolを比較し、keyと候補層を別項目にする。"""
    parent = {key: {"present": key in spec["env"], "expected_match": key in spec["env"]}
              for key in harness.REQUIRED_TOOL_ENV_KEYS}
    def run_check(command):
        try:
            result = subprocess.run(command, cwd=root, env=spec["env"], text=True,
                                    capture_output=True, timeout=15)
            if result.returncode != 0:
                return None
            payload = strict_json(result.stdout)
            checks = payload.get("required_checks")
            if not isinstance(checks, dict) or set(checks) != set(harness.REQUIRED_TOOL_ENV_KEYS):
                return None
            return checks
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    env_i = run_check(["/usr/bin/env", "-i", *[f"{key}={value}" for key, value in sorted(spec["env"].items())],
                       *shlex.split(harness.ENV_CANARY_COMMAND)])
    login = run_check(["/bin/zsh", "-lc", harness.ENV_CANARY_COMMAND])
    mismatched = [key for key, entry in actual_checks.items() if not entry.get("present") or not entry.get("expected_match")]
    layer = "none" if not mismatched else "unresolved"
    if mismatched and env_i is not None and login is not None:
        if all(env_i[key]["expected_match"] for key in mismatched) and all(not login[key]["expected_match"] for key in mismatched):
            layer = "login_shell_candidate"
        elif all(env_i[key]["expected_match"] and login[key]["expected_match"] for key in mismatched):
            layer = "cli_or_sandbox_or_tool_unresolved"
        elif any(not env_i[key]["expected_match"] for key in mismatched):
            layer = "env_i_layer_candidate"
    return {"schema": 1, "mismatched_required_keys": sorted(mismatched), "cause_layer": layer,
            "parent": parent, "env_i": env_i, "zsh_login": login, "actual_tool": actual_checks,
            "shell_identity_bound_by_fingerprint": True}


def probe(fingerprint, preflight_path):
    current = compute_harness_fingerprint(harness.HERE)
    if current != fingerprint:
        raise ValueError("fixed_fingerprint_changed")
    harness.require_source_directory()
    preflight_hash, preflight_binding, preflight_report = check_preflight(preflight_path, fingerprint)
    driver_config_binding = harness.compute_driver_config_binding()
    attempt = reserve(fingerprint, driver_config_binding=driver_config_binding)
    previous_handler = signal.signal(signal.SIGALRM, lambda _number, _frame: (_ for _ in ()).throw(TimeoutError("probe_slot_timeout")))
    signal.setitimer(signal.ITIMER_REAL, SLOT_SECONDS)
    result_code = "audit_unavailable"
    passed = False
    process = None
    root = None
    child_reaped = False
    residual_verified = False
    try:
        PROBE_BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
        root = PROBE_BASE / ("probe-" + attempt["id"])
        root.mkdir(mode=0o700)
        (root / ".benchmark-tmp/home").mkdir(mode=0o700, parents=True)
        harness._write_private(root / "AGENTS.md", "P5 canary-only fixture\n")
        harness.install_env_canary(root, fingerprint, "probe")
        task = {"id": "PROBE", "input": [], "fixture": []}
        spec = harness.canonical_execution_spec(root, task, harness.CLI_VERSION, fingerprint, "probe")
        preflight_root = Path(preflight_binding["root_realpath"])
        if (not preflight_root.is_relative_to(BASE / "preflight")
                or not root.resolve().is_relative_to(PROBE_BASE.resolve())):
            raise ValueError("preflight_or_probe_root_outside_expected_area")
        if (not compare_preflight_binding(preflight_binding, spec["binding"],
                                         preflight_report["execution_profile_evidence"], spec)
                or sorted(str(path.relative_to(root)) for path in harness.permission_policy(root, task, phase="probe"))
                   != [".benchmark-tmp"]):
            raise ValueError("normal_shell_preflight_binding_not_probe_equivalent")
        before = harness.tree_manifest(root)
        command = [harness.CODEX_EXECUTABLE, "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                   "--skip-git-repo-check", "--json", "--model", "gpt-6-astra", "-c", 'model_reasoning_effort="medium"',
                   "-c", 'model_provider="openai"', "-c", "features.hooks=false", "-c", 'default_permissions="p5_fixture"',
                   *sum((["-c", value] for value in spec["config"] + harness.tool_environment_config(spec)), []),
                   "-C", str(root), "-o", str(root / ".benchmark-answer.txt"), "-"]
        started = time.monotonic()
        process = subprocess.Popen(command, cwd=root, env=harness.process_env(spec), text=True,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        bind_child(attempt["id"], process.pid, process.pid)
        try:
            remaining = max(0.0, min(MODEL_SECONDS, attempt["deadline_epoch"] - time.time()))
            stdout, stderr = process.communicate(PROMPT, timeout=remaining)
        except subprocess.TimeoutExpired:
            result_code = "model_timeout"
            raise ValueError(result_code) from None
        if time.monotonic() - started > SLOT_SECONDS:
            raise ValueError("probe_slot_timeout")
        audit = harness.safe_events(stdout, expected_cwd=root, expected_env=spec["env"],
                                    forbidden_values=tuple(value for value in spec["env"].values() if value))
        raw = PROBE_BASE / (root.name + ".raw.jsonl")
        harness.save_raw_events(raw, stdout, forbidden_values=tuple(value for value in spec["env"].values() if value),
                                audit_passed=audit.get("event_audit", {}).get("passed") is True)
        harness.save(PROBE_BASE / (root.name + ".audit.json"), audit)
        diagnosis = diagnose_layers(root, spec, audit["env_canary_evidence"]["required_checks"])
        harness.save(PROBE_BASE / (root.name + ".diagnosis.json"), diagnosis)
        exact = (len(audit["commands"]) == 2 and len({item["item_id_sha256"] for item in audit["commands"]}) == 1
                 and all(item["command_sha256"] == harness.digest_bytes(harness.ENV_CANARY_COMMAND.encode())
                         for item in audit["commands"])
                 and audit["event_audit"]["item_categories"].get("tool") == 2)
        binding = harness.derive_canonical_binding(root, task, harness.CLI_VERSION, fingerprint, "probe") == spec["binding"]
        scope = harness.tree_manifest(root) == before
        residual = harness.scan_residual_processes(spec["env"]["P5_RUN_TOKEN"])
        process_context = harness.scan_residual_context(root, process.pid)
        runtime = harness.compute_python_runtime_binding() == spec["binding"]["python_runtime"]
        cli = harness.compute_codex_executable_binding() == spec["binding"]["codex_executable"]
        passed = (time.time() - attempt["started_epoch"] <= SLOT_SECONDS and process.returncode == 0 and exact and binding and scope and residual["passed"]
                  and process_context["passed"] and runtime and cli
                  and audit["env_canary_evidence"]["passed"] and audit["event_audit"]["passed"]
                  and audit["attempt_policy"]["passed"])
        result_code = "pass" if passed else "probe_gate_fail"
        harness.save(PROBE_BASE / (root.name + ".result.json"), {"schema": 2, "fingerprint": fingerprint,
            "preflight_sha256": preflight_hash, "passed": passed, "code": result_code,
            "driver_config_binding_sha256": harness.canonical_digest(driver_config_binding),
            "formal_binding_equivalence": {"same_cli_python_env_policy_profile_name_login_shell": True,
                "dedicated_differences": ["root_identity", "run_token", "task_specific_write_paths"],
                "profile_name": "p5_fixture"},
            "checks": {"exact": exact, "binding": binding, "scope": scope,
                       "residual": residual["passed"] and process_context["passed"],
                       "runtime": runtime, "cli": cli, "environment": audit["env_canary_evidence"]["passed"],
                       "event": audit["event_audit"]["passed"], "attempt": audit["attempt_policy"]["passed"]},
            "raw_sha256": hashlib.sha256(stdout.encode()).hexdigest(), "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest()})
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        if result_code == "audit_unavailable":
            result_code = type(error).__name__
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        try:
            if process is not None:
                entry = ledger_record()["attempts"][-1]
                child_reaped = reap_probe_child(process, entry)
                if not child_reaped:
                    raise ValueError("probe_child_reap_unconfirmed")
            token_scan = harness.scan_residual_processes(spec["env"]["P5_RUN_TOKEN"]) if spec else {"passed": True}
            context_scan = harness.scan_residual_context(root, process.pid if process is not None else 2147483647) if root else {"passed": True}
            residual_verified = token_scan.get("passed") is True and context_scan.get("passed") is True
            if not child_reaped or not residual_verified:
                raise ValueError("probe_residual_or_reap_unconfirmed")
            finish(attempt["id"], passed and result_code == "pass", result_code, child_reaped=True,
                   residual_verified=True)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            # 不確実なreservationをterminal化しない。後続probe/formalはledger guardで拒否される。
            pass
    if not passed:
        raise ValueError(result_code)
    return attempt["id"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    args = parser.parse_args()
    print(probe(args.fingerprint, args.preflight_report))


if __name__ == "__main__":
    main()
