#!/usr/bin/env python3
"""モデルを呼ばず、実runと同じ権限・CLI process env・tool envの境界を確認する。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import uuid

import run as runner

DENIAL_MARKERS = ("operation not permitted", "permission denied", "read-only file system", "sandbox denied",
                  "sandbox violation", "network is disabled", "network disabled", "not allowed")
INFRASTRUCTURE_MARKERS = ("sandbox-exec: sandbox_apply", "sandbox initialization failed", "unknown permission profile",
                          "failed to parse", "invalid configuration", "invalid config", "no such file or directory")


def classify_denial(exit_code, stdout, stderr):
    combined = (stdout + "\n" + stderr).lower()
    if exit_code == 0:
        return "unexpected_success"
    if any(marker in combined for marker in INFRASTRUCTURE_MARKERS):
        return "preflight_error"
    return "sandbox_denied" if any(marker in combined for marker in DENIAL_MARKERS) else "unexpected_failure"


def case_matches_expected(case):
    return (case["expected"], case["outcome"]) in {("allow", "allowed"), ("deny", "sandbox_denied")}


def read_command(path):
    return ["python3.12", "-B", "-c", "import sys; open(sys.argv[1], 'rb').read()", str(path)]


def write_command(path):
    return ["python3.12", "-B", "-c", "import sys; open(sys.argv[1], 'wb').write(b'P5 synthetic canary\\n')", str(path)]


def run_case(name, spec, command, expected):
    invocation = runner.sandbox_command(spec["root"], spec["task"], command, spec)
    try:
        completed = subprocess.run(invocation, text=True, capture_output=True, env=runner.process_env(spec),
                                   cwd=spec["root"], timeout=20, check=False)
        code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        outcome = ("allowed" if code == 0 else "preflight_error") if expected == "allow" else classify_denial(code, stdout, stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        outcome, code, stdout, stderr = "preflight_error", "spawn_or_timeout", "", str(error)
    spec.setdefault("private_preflight_diagnostics", []).append({"name": name, "command": command, "exit_code": code,
                                                               "stdout": stdout, "stderr": stderr})
    return {"name": name, "expected": expected, "outcome": outcome, "exit_code": code,
            "command_sha256": runner.canonical_digest(command), "binding_sha256": runner.canonical_digest(spec["binding"]),
            "stdout_sha256": runner.digest_bytes(stdout.encode()), "stderr_sha256": runner.digest_bytes(stderr.encode())}


def check(spec):
    root = spec["root"]
    token = uuid.uuid4().hex
    sentinel = root.parent / (".p5-private-" + token)
    outside = root.parent / (".p5-write-" + token)
    repository_target = runner.REPOSITORY / (".p5-preflight-" + token)
    scratch = root / ".benchmark-tmp" / ("canary-" + token)
    task_dir = root / ("migration-progress" if spec["task"]["id"] == "C6" else "docs/plans")
    task_write = task_dir / (".p5-canary-" + token)
    link = root / ".benchmark-tmp" / ("outside-link-" + token)
    runner._write_private(sentinel, "synthetic-private-canary\n")
    sentinel_hash = runner.sha(sentinel)
    link.symlink_to(sentinel)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    spec["private_preflight_diagnostics"] = []
    report = {"schema": 3, "started_at": runner.stamp(), "cli_version": spec["binding"]["cli_version"],
              "tool_environment_scope": "auxiliary_env_i_probe_not_actual_exec_tool",
              "binding": spec["binding"], "binding_comparison": "entire_canonical_binding_equal_before_model", "passed": False, "cases": []}
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        initial = run_case("sandbox_initialized", spec, ["python3.12", "-B", "-c", "print('runtime-ok')"], "allow")
        report["cases"].append(initial)
        report["sandbox_initialized"] = case_matches_expected(initial)
        cases = [
            ("tool_environment_exact", ["python3.12", "-B", "-c", "import json,os,sys; sys.exit(0 if dict(os.environ)==json.loads(sys.argv[1]) else 1)", json.dumps(spec["env"])], "allow"),
            ("fixture_read", read_command(root / "AGENTS.md"), "allow"),
            ("scratch_write", write_command(scratch), "allow"),
            ("task_directory_write", write_command(task_write), "allow"),
            ("outside_private_read", read_command(sentinel), "deny"),
            ("symlink_outside_private_read", read_command(link), "deny"),
            ("outside_write", write_command(outside), "deny"),
            ("repository_read", read_command(runner.REPOSITORY / "AGENTS.md"), "deny"),
            ("repository_write", write_command(repository_target), "deny"),
            ("network_connect", ["python3.12", "-B", "-c", "import socket,sys; socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=1)", str(port)], "deny"),
        ]
        file_hashes = {}
        for index, path in enumerate(runner.permission_policy(root, spec["task"])):
            if path.is_file():
                file_hashes[path] = runner.sha(path)
                cases.append((f"task_file_write_{index}", ["python3.12", "-B", "-c", "import sys; f=open(sys.argv[1],'r+b'); b=f.read(); f.seek(0); f.write(b); f.close()", str(path)], "allow"))
        if report["sandbox_initialized"]:
            report["cases"].extend(run_case(name, spec, command, expected) for name, command, expected in cases)
        else:
            report["cases"].extend({"name": name, "expected": expected, "outcome": "not_run_preflight_error"} for name, _, expected in cases)
        rebound = runner.canonical_execution_spec(root, spec["task"], spec["binding"]["cli_version"], spec["binding"]["harness_fingerprint"], spec["binding"]["phase"])
        conditions = {"canary_writes_observed": scratch.is_file() and task_write.is_file(),
                      "outside_writes_absent": not os.path.lexists(outside) and not os.path.lexists(repository_target),
                      "private_sentinel_unchanged": runner.sha(sentinel) == sentinel_hash,
                      "task_file_contents_unchanged": all(runner.sha(path) == value for path, value in file_hashes.items()),
                      "binding_unchanged": spec["binding"] == rebound["binding"]}
        report["postconditions"] = conditions
        report["passed"] = all(conditions.values()) and all(case_matches_expected(case) for case in report["cases"])
    finally:
        listener.close()
        for path in (link, scratch, task_write, sentinel, outside, repository_target):
            path.unlink(missing_ok=True)
        report["canaries_removed"] = all(not os.path.lexists(path) for path in (link, scratch, task_write, sentinel, outside, repository_target))
        report["passed"] = report["passed"] and report["canaries_removed"]
        report["ended_at"] = runner.stamp()
        diagnostics = root.parent / ".evidence" / root.name / "preflight.raw.json"
        runner.save(diagnostics, spec.pop("private_preflight_diagnostics", []))
        report["private_diagnostics_sha256"] = runner.sha(diagnostics)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    with runner.private_umask():
        directory = Path(tempfile.mkdtemp(prefix="agent-crew-p5-sandbox-preflight-", dir="/private/tmp"))
        fixture = directory / "fixture"
        fixture.mkdir(mode=0o700)
        runner._write_private(fixture / "AGENTS.md", "P5 synthetic fixture\n")
        version = subprocess.run([runner.CODEX_EXECUTABLE, "--version"], capture_output=True, text=True, check=True,
                                 env={"PATH": runner.FIXED_PATH}).stdout.strip()
        if version != runner.CLI_VERSION:
            raise SystemExit("CLI版不一致")
        harness = runner.canonical_digest({name: runner.sha(runner.HERE / name) for name in ("run.py", "sandbox_preflight.py")})
        report = check(runner.execution_spec(fixture, runner.c6_task(), version, harness))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.cleanup:
            shutil.rmtree(directory)
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
