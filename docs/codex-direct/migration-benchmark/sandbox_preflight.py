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
    return [runner.PYTHON_EXECUTABLE, "-B", "-c", "import sys; open(sys.argv[1], 'rb').read()", str(path)]


def write_command(path):
    return [runner.PYTHON_EXECUTABLE, "-B", "-c", "import sys; open(sys.argv[1], 'wb').write(b'P5 synthetic canary\\n')", str(path)]


def runtime_command(binding):
    expected = {key: binding[key] for key in ("executable_realpath", "root_realpath", "python_version",
                                            "architecture", "implementation", "cache_tag")}
    return [runner.PYTHON_EXECUTABLE, "-I", "-B", "-c",
            "import _ssl,_ctypes,zlib,unicodedata,json,os,platform,sys; "
            "observed={'executable_realpath':os.path.realpath(sys.executable),'root_realpath':os.path.realpath(sys.base_prefix),"
            "'python_version':list(sys.version_info[:3]),'architecture':platform.machine(),"
            "'implementation':sys.implementation.name,'cache_tag':sys.implementation.cache_tag}; "
            "sys.exit(0 if observed==json.loads(sys.argv[1]) else 1)", json.dumps(expected)]


def sibling_runtime_read_target(fallback):
    # 存在する3.11 runtimeを優先する。aliasは固定実pathへ解決し、sandbox内では再検索しない。
    for path in sorted(runner.PYTHON_RUNTIME.parent.glob("cpython-3.11*/bin/python3.11")):
        target = path.resolve(strict=True)
        if target.is_file() and not target.is_relative_to(runner.PYTHON_RUNTIME):
            return target
    return fallback


def run_case(name, spec, command, expected):
    invocation = runner.sandbox_command(spec["root"], spec["task"], command, spec)
    process, completion_confirmed, interrupted = None, False, None
    def decoded(value):
        return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
    try:
        process = subprocess.Popen(invocation, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=runner.process_env(spec), cwd=spec["root"])
        stdout, stderr = process.communicate(timeout=20)
        code = process.returncode
        completion_confirmed = True
        outcome = ("allowed" if code == 0 else "preflight_error") if expected == "allow" else classify_denial(code, stdout, stderr)
    except subprocess.TimeoutExpired as error:
        outcome, code = "preflight_error", "timeout"
        stdout, stderr = decoded(error.stdout), decoded(error.stderr)
        spec["preflight_execution_incomplete"] = True
    except runner.RunSignal as error:
        outcome, code, stdout, stderr = "preflight_error", f"signal:{error.signum}", "", ""
        spec["preflight_execution_incomplete"] = True
        interrupted = error
    except OSError as error:
        outcome, code, stdout, stderr = "preflight_error", "spawn_error", "", str(error)
    finally:
        if process is not None:
            runner.close_process_streams(process)
    spec.setdefault("private_preflight_diagnostics", []).append({"name": name, "command": command, "exit_code": code,
        "stdout": stdout, "stderr": stderr, "automatic_termination": False,
        "leader_pid_at_launch": process.pid if process is not None else None,
        "pid_current_ownership_unverified": True,
        "process_may_still_be_running": process is not None and not completion_confirmed})
    if (outcome in {"preflight_error", "unexpected_failure"} or interrupted is not None or not completion_confirmed
            or type(code) is not int or code < 0):
        runner.abort_run(spec, "preflight", "case_execution_unconfirmed", code,
                         {"case": name, "private_cases": spec["private_preflight_diagnostics"]})
    return {"name": name, "expected": expected, "outcome": outcome, "exit_code": code,
            "command_sha256": runner.canonical_digest(command), "binding_sha256": runner.canonical_digest(spec["binding"]),
            "stdout_sha256": runner.digest_bytes(stdout.encode()), "stderr_sha256": runner.digest_bytes(stderr.encode())}


def check(spec):
    root = spec["root"]
    runner.require_runtime_binding(spec, "preflight", spec["binding"]["python_runtime"])
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
    spec["preflight_execution_incomplete"] = False
    report = {"schema": 3, "started_at": runner.stamp(), "cli_version": spec["binding"]["cli_version"],
              "tool_environment_scope": "auxiliary_env_i_probe_not_actual_exec_tool",
              "binding": spec["binding"], "binding_comparison": "entire_canonical_binding_equal_before_model", "passed": False, "cases": []}
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        initial = run_case("sandbox_initialized", spec, [runner.PYTHON_EXECUTABLE, "-B", "-c", "print('runtime-ok')"], "allow")
        report["cases"].append(initial)
        report["sandbox_initialized"] = case_matches_expected(initial)
        cases = [
            ("python_runtime_import", runtime_command(spec["binding"]["python_runtime"]), "allow"),
            ("python_runtime_parent_listing", [runner.PYTHON_EXECUTABLE, "-B", "-c", "import os,sys; os.listdir(sys.argv[1])", str(runner.PYTHON_RUNTIME.parent)], "deny"),
            ("python_sibling_read", read_command(sibling_runtime_read_target(sentinel)), "deny"),
            ("uv_executable_read", read_command(Path.home() / ".local/bin/uv"), "deny"),
            ("python_runtime_write", [runner.PYTHON_EXECUTABLE, "-B", "-c", "import sys; open(sys.argv[1],'r+b').close()", runner.PYTHON_EXECUTABLE], "deny"),
            ("tool_environment_exact", [runner.PYTHON_EXECUTABLE, "-B", "-c", "import json,os,sys; sys.exit(0 if dict(os.environ)==json.loads(sys.argv[1]) else 1)", json.dumps(spec["env"])], "allow"),
            ("fixture_read", read_command(root / "AGENTS.md"), "allow"),
            ("scratch_write", write_command(scratch), "allow"),
            ("task_directory_write", write_command(task_write), "allow"),
            ("outside_private_read", read_command(sentinel), "deny"),
            ("symlink_outside_private_read", read_command(link), "deny"),
            ("outside_write", write_command(outside), "deny"),
            ("repository_read", read_command(runner.REPOSITORY / "AGENTS.md"), "deny"),
            ("repository_write", write_command(repository_target), "deny"),
            ("network_connect", [runner.PYTHON_EXECUTABLE, "-B", "-c", "import socket,sys; socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=1)", str(port)], "deny"),
        ]
        file_hashes = {}
        for index, path in enumerate(runner.permission_policy(root, spec["task"])):
            if path.is_file():
                file_hashes[path] = runner.sha(path)
                cases.append((f"task_file_write_{index}", [runner.PYTHON_EXECUTABLE, "-B", "-c", "import sys; f=open(sys.argv[1],'r+b'); b=f.read(); f.seek(0); f.write(b); f.close()", str(path)], "allow"))
        for name, command, expected in cases:
            if report["sandbox_initialized"] and not spec["preflight_execution_incomplete"]:
                report["cases"].append(run_case(name, spec, command, expected))
            else:
                report["cases"].append({"name": name, "expected": expected, "outcome": "not_run_preflight_error"})
        # runtime不一致を通常のpostcondition失敗に落とさず、root確認・cleanup前に停止する。
        runner.require_runtime_binding(spec, "preflight", spec["binding"]["python_runtime"])
        try:
            rebound = runner.canonical_execution_spec(root, spec["task"], spec["binding"]["cli_version"], spec["binding"]["harness_fingerprint"], spec["binding"]["phase"])
        except (Exception, runner.RunSignal) as error:
            runner.abort_run(spec, "preflight", "preflight_binding_recalculation_error", details={"error_type": type(error).__name__})
        runner.require_runtime_binding(spec, "preflight", spec["binding"]["python_runtime"], rebound["binding"]["python_runtime"])
        conditions = {"canary_writes_observed": scratch.is_file() and task_write.is_file(),
                      "outside_writes_absent": not os.path.lexists(outside) and not os.path.lexists(repository_target),
                      "private_sentinel_unchanged": runner.sha(sentinel) == sentinel_hash,
                      "task_file_contents_unchanged": all(runner.sha(path) == value for path, value in file_hashes.items()),
                      "python_runtime_unchanged": spec["binding"]["python_runtime"] == rebound["binding"]["python_runtime"],
                      "binding_unchanged": spec["binding"] == rebound["binding"]}
        report["postconditions"] = conditions
        report["passed"] = all(conditions.values()) and all(case_matches_expected(case) for case in report["cases"])
    finally:
        listener.close()
    for path in (link, scratch, task_write, sentinel, outside, repository_target):
        path.unlink(missing_ok=True)
    report["canaries_removed"] = all(not os.path.lexists(path) for path in (link, scratch, task_write, sentinel, outside, repository_target))
    report["process_may_still_be_running"] = spec.pop("preflight_execution_incomplete")
    report["passed"] = report["passed"] and report["canaries_removed"] and not report["process_may_still_be_running"]
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
        version = runner.run_trusted_command([runner.CODEX_EXECUTABLE, "--version"], capture_output=True, text=True, check=True,
                                 env={"PATH": runner.FIXED_PATH}).stdout.strip()
        if version != runner.CLI_VERSION:
            raise SystemExit("CLI版不一致")
        harness = runner.canonical_digest({name: runner.sha(runner.HERE / name) for name in ("run.py", "sandbox_preflight.py")})
        report = check(runner.execution_spec(fixture, runner.c6_task(), version, harness))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.cleanup and not report.get("process_may_still_be_running"):
            shutil.rmtree(directory)
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
