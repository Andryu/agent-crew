#!/usr/bin/env python3
"""P5 v16: private ledgerで上限を守るcanary-only実tool probe。"""

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
LEDGER_DIR = BASE / "drivers/logs/v16"
LEDGER = LEDGER_DIR / "probe-ledger.json"
PROBE_BASE = BASE / "probe-v16"
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


def ledger_record(path=LEDGER):
    if not path.exists():
        if any(path.with_name(f"probe-attempt-{index:02d}.json").exists() for index in (1, 2)):
            raise ValueError("probe_ledger_missing_with_reservation")
        return {"schema": 1, "version": 16, "max_attempts": MAX_ATTEMPTS,
                "max_reserved_seconds": MAX_TOTAL_SECONDS, "attempts": []}
    record = strict_json(_private_file(path))
    if (set(record) != {"schema", "version", "max_attempts", "max_reserved_seconds", "attempts"}
            or record["schema"] != 1 or record["version"] != 16
            or record["max_attempts"] != MAX_ATTEMPTS or record["max_reserved_seconds"] != MAX_TOTAL_SECONDS
            or not isinstance(record["attempts"], list) or len(record["attempts"]) > MAX_ATTEMPTS
            or any(not isinstance(entry, dict) or entry.get("slot_seconds") != SLOT_SECONDS
                   or entry.get("state") not in {"reserved", "pass", "fail"} for entry in record["attempts"])):
        raise ValueError("probe_ledger_invalid")
    for index, entry in enumerate(record["attempts"], 1):
        reservation = path.with_name(f"probe-attempt-{index:02d}.json")
        saved = strict_json(_private_file(reservation))
        if saved != {key: entry[key] for key in ("id", "fingerprint", "slot_seconds", "started_epoch")}:
            raise ValueError("probe_reservation_mismatch")
    if any(path.with_name(f"probe-attempt-{index:02d}.json").exists()
           for index in range(len(record["attempts"]) + 1, MAX_ATTEMPTS + 1)):
        raise ValueError("probe_unaccounted_reservation")
    return record


def _atomic(path, record):
    data = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = path.with_name(".probe-ledger-" + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)


def reserve(fingerprint, path=LEDGER):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise ValueError("probe_ledger_parent_mode")
    lock = path.with_name("probe-ledger.lock")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        record = ledger_record(path)
        if len(record["attempts"]) >= MAX_ATTEMPTS or sum(x["slot_seconds"] for x in record["attempts"]) + SLOT_SECONDS > MAX_TOTAL_SECONDS:
            raise ValueError("probe_budget_exhausted")
        attempt = {"id": uuid.uuid4().hex, "fingerprint": fingerprint, "slot_seconds": SLOT_SECONDS,
                   "state": "reserved", "started_epoch": time.time()}
        reservation = path.with_name(f"probe-attempt-{len(record['attempts']) + 1:02d}.json")
        data = (json.dumps({key: attempt[key] for key in ("id", "fingerprint", "slot_seconds", "started_epoch")},
                           sort_keys=True, separators=(",", ":")) + "\n").encode()
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


def finish(attempt_id, passed, detail, path=LEDGER):
    fd = os.open(path.with_name("probe-ledger.lock"), os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        record = ledger_record(path)
        entries = [x for x in record["attempts"] if x["id"] == attempt_id]
        if len(entries) != 1 or entries[0]["state"] != "reserved":
            raise ValueError("probe_attempt_not_reserved")
        entries[0].update(state="pass" if passed else "fail", ended_epoch=time.time(), detail=detail)
        _atomic(path, record)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def require_final_probe(fingerprint, path=LEDGER):
    attempts = ledger_record(path)["attempts"]
    if not attempts or attempts[-1].get("state") != "pass" or attempts[-1].get("fingerprint") != fingerprint:
        raise ValueError("final_fixed_probe_not_passed")
    return attempts[-1]


def check_preflight(path, fingerprint):
    report = strict_json(_private_file(path))
    if (report.get("passed") is not True or not isinstance(report.get("binding"), dict)
            or report["binding"].get("harness_fingerprint") != fingerprint):
        raise ValueError("normal_shell_preflight_not_passed_or_unbound")
    return hashlib.sha256(harness.safe_read(path)).hexdigest()


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
    preflight_hash = check_preflight(preflight_path, fingerprint)
    attempt = reserve(fingerprint)
    previous_handler = signal.signal(signal.SIGALRM, lambda _number, _frame: (_ for _ in ()).throw(TimeoutError("probe_slot_timeout")))
    signal.setitimer(signal.ITIMER_REAL, SLOT_SECONDS)
    result_code = "audit_unavailable"
    passed = False
    try:
        PROBE_BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
        root = PROBE_BASE / ("probe-" + attempt["id"])
        root.mkdir(mode=0o700)
        (root / ".benchmark-tmp/home").mkdir(mode=0o700, parents=True)
        harness._write_private(root / "AGENTS.md", "P5 canary-only fixture\n")
        harness.install_env_canary(root, fingerprint, "probe")
        task = {"id": "PROBE", "input": [], "fixture": []}
        spec = harness.canonical_execution_spec(root, task, harness.CLI_VERSION, fingerprint, "probe")
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
        try:
            stdout, stderr = process.communicate(PROMPT, timeout=MODEL_SECONDS)
        except subprocess.TimeoutExpired:
            result_code = "model_timeout_process_may_remain"
            raise ValueError(result_code) from None
        if time.monotonic() - started > SLOT_SECONDS:
            raise ValueError("probe_slot_timeout")
        raw = PROBE_BASE / (root.name + ".raw.jsonl")
        harness._write_private(raw, stdout)
        audit = harness.safe_events(stdout, expected_cwd=root, expected_env=spec["env"])
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
        harness.save(PROBE_BASE / (root.name + ".result.json"), {"schema": 1, "fingerprint": fingerprint,
            "preflight_sha256": preflight_hash, "passed": passed, "code": result_code,
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
        finish(attempt["id"], passed, result_code)
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
