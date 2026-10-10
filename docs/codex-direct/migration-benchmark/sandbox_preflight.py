#!/usr/bin/env python3
"""モデルを呼ばず、実runと同じ権限・CLI process env・tool envの境界を確認する。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
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
    runner.require_codex_binding(spec, "preflight", spec["binding"]["codex_executable"])
    runner.require_directory_binding(spec, "preflight")
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


BOUNDARY_LABELS = ("source_worktree", "main_repository", "other_run", "other_campaign", "accepted", "evidence", "driver")
TEMP_LABELS = tuple(f"platform_temp_{index}" for index in range(4))


def boundary_parents(root):
    return {"source_worktree": runner.REPOSITORY,
            "main_repository": runner.account_home() / "Workspace/agent-crew",
            "other_run": root.parent, "other_campaign": root.parent.parent,
            "accepted": root.parent / ".accepted", "evidence": root.parent / ".evidence",
            "driver": runner.formal_base() / "drivers"}


def platform_temp_parents():
    return dict(zip(TEMP_LABELS, map(Path, ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp"))))


def create_boundary_canaries(spec, token):
    """既存成果物は変更せず、専用0700 directory内の合成fileだけを検査する。"""
    roots = boundary_parents(spec["root"])
    roots.update(platform_temp_parents())
    entries = []
    try:
        for label, parent in roots.items():
            # systemの既知aliasはtemp probeに限ってrealpath化する。他のcomponentはnofollow。
            physical_parent = parent.resolve(strict=True) if label in TEMP_LABELS else parent
            directory = physical_parent / (".p5-boundary-" + token + "-" + label)
            if os.path.lexists(directory):
                raise runner.BoundaryError("boundary canaryを上書きしません")
            identity = runner.private_directory_identity(directory, create=True, include_parent=False)
            read = directory / "read-canary"
            write = directory / "write-canary"
            alias = spec["root"] / ".benchmark-tmp" / ("boundary-link-" + token + "-" + label)
            visible = parent / directory.name
            entry = {"label": label, "directory": directory, "identity": identity, "read": read,
                     "write": write, "sha256": None, "alias": alias, "visible": visible}
            entries.append(entry)
            runner._write_private(read, "synthetic boundary canary\n")
            entry["sha256"] = runner.sha(read)
            alias.symlink_to(directory)
    except BaseException:
        try:
            remove_boundary_canaries(entries)
            # Preserve rollback even if a platform's dir-fd rmdir reports success
            # while leaving an already-empty leaf visible.
            for entry in entries:
                directory = entry["directory"]
                if os.path.lexists(directory):
                    parent_fd = runner._open_directory(directory.parent)
                    try:
                        current = os.stat(directory.name, dir_fd=parent_fd, follow_symlinks=False)
                        expected = entry["identity"]["root"]
                        if ((current.st_dev, current.st_ino) != (expected["device"], expected["inode"])
                                or not stat.S_ISDIR(current.st_mode) or os.listdir(directory)):
                            raise runner.BoundaryError("partial boundary directory cleanup identity/content unknown")
                        os.rmdir(directory.name, dir_fd=parent_fd)
                    finally:
                        os.close(parent_fd)
        except BaseException as cleanup_error:
            raise runner.BoundaryError("boundary canary partial cleanup could not be verified") from cleanup_error
        raise
    return entries


def boundary_cases(entries):
    cases = []
    for entry in entries:
        name, visible, alias = entry["label"], entry["visible"], entry["alias"]
        cases.extend([(name + "_read", read_command(visible / "read-canary"), "deny"),
                      (name + "_write", write_command(visible / "write-canary"), "deny"),
                      (name + "_symlink_read", read_command(alias / "read-canary"), "deny"),
                      (name + "_symlink_write", write_command(alias / "write-canary"), "deny")])
        if name in TEMP_LABELS:
            cases.append((name + "_listing", [runner.PYTHON_EXECUTABLE, "-B", "-c",
                          "import os,sys; os.listdir(sys.argv[1])", str(visible.parent)], "deny"))
    return cases


def remove_boundary_canaries(entries):
    # identity/type/既知内容の照合後に、保持したfd相対で作成物だけをunlinkする。
    for entry in entries:
        directory = entry["directory"]
        if runner.private_directory_identity(directory, include_parent=False) != entry["identity"]:
            raise runner.BoundaryError("boundary canary directoryが差し替わりました")
        fd = runner._open_directory(directory)
        try:
            for name in os.listdir(fd):
                if name not in {"read-canary", "write-canary"}:
                    raise runner.BoundaryError("boundary canaryに未知fileがあります")
                if not runner._regular(os.stat(name, dir_fd=fd, follow_symlinks=False)):
                    raise runner.BoundaryError("boundary canaryのlink/typeが変更されました")
                os.unlink(name, dir_fd=fd)
        finally:
            os.close(fd)
        entry["alias"].unlink(missing_ok=True)
        parent_fd = runner._open_directory(directory.parent)
        try:
            current = os.stat(directory.name, dir_fd=parent_fd, follow_symlinks=False)
            expected = entry["identity"]["root"]
            if (current.st_dev, current.st_ino) != (expected["device"], expected["inode"]):
                raise runner.BoundaryError("cleanup前にcanaryが差し替わりました")
            os.rmdir(directory.name, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)


def check(spec):
    root = spec["root"]
    runner.require_formal_locations(root, root.parent)
    runner.require_source_directory()
    runner.require_codex_binding(spec, "preflight", spec["binding"]["codex_executable"])
    runner.require_directory_binding(spec, "preflight")
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
    boundaries = create_boundary_canaries(spec, token)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    spec["private_preflight_diagnostics"] = []
    spec["preflight_execution_incomplete"] = False
    report = {"schema": 3, "started_at": runner.stamp(), "cli_version": spec["binding"]["cli_version"],
              "tool_environment_scope": "auxiliary_env_i_probe_not_actual_exec_tool",
              "actual_tool_environment_normalization": runner.actual_tool_environment_evidence(os.environ),
              "binding": spec["binding"], "binding_comparison": "entire_canonical_binding_equal_before_model",
              "execution_profile_evidence": {"schema": 1, "profile_name": "p5_fixture", "network_enabled": False,
                  "read_boundary": spec["binding"]["read_boundary"],
                  "write_paths": sorted(str(path.relative_to(root)) for path in runner.permission_policy(root, spec["task"])),
                  "policy_template_sha256": spec["binding"]["policy_template_sha256"],
                  "profile_sha256": spec["binding"]["profile_sha256"],
                  "binding_sha256": runner.canonical_digest(spec["binding"])},
              "passed": False, "cases": []}
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
            ("uv_executable_read", read_command(runner.account_home() / ".local/bin/uv"), "deny"),
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
        # network caseを最後に保ち、全合成boundaryをモデル開始前に検査する。
        cases[-1:-1] = boundary_cases(boundaries)
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
        runner.require_codex_binding(spec, "preflight", spec["binding"]["codex_executable"])
        runner.require_directory_binding(spec, "preflight")
        try:
            rebound = runner.canonical_execution_spec(root, spec["task"], spec["binding"]["cli_version"], spec["binding"]["harness_fingerprint"], spec["binding"]["phase"])
        except (Exception, runner.RunSignal) as error:
            runner.abort_run(spec, "preflight", "preflight_binding_recalculation_error", details={"error_type": type(error).__name__})
        runner.require_runtime_binding(spec, "preflight", spec["binding"]["python_runtime"], rebound["binding"]["python_runtime"])
        runner.require_codex_binding(spec, "preflight", spec["binding"]["codex_executable"], rebound["binding"]["codex_executable"])
        conditions = {"canary_writes_observed": scratch.is_file() and task_write.is_file(),
                      "outside_writes_absent": not os.path.lexists(outside) and not os.path.lexists(repository_target)
                          and all(not os.path.lexists(entry["write"]) for entry in boundaries),
                      "private_sentinel_unchanged": runner.sha(sentinel) == sentinel_hash and all(
                          runner.sha(entry["read"]) == entry["sha256"] and
                          runner.private_directory_identity(entry["directory"], include_parent=False) == entry["identity"]
                          for entry in boundaries),
                      "task_file_contents_unchanged": all(runner.sha(path) == value for path, value in file_hashes.items()),
                      "python_runtime_unchanged": spec["binding"]["python_runtime"] == rebound["binding"]["python_runtime"],
                      "binding_unchanged": spec["binding"] == rebound["binding"]}
        report["postconditions"] = conditions
        report["passed"] = (report["actual_tool_environment_normalization"]["passed"] is True
                             and all(conditions.values()) and all(case_matches_expected(case) for case in report["cases"]))
    finally:
        listener.close()
    for path in (link, scratch, task_write, sentinel, outside, repository_target):
        path.unlink(missing_ok=True)
    remove_boundary_canaries(boundaries)
    report["canaries_removed"] = (all(not os.path.lexists(path) for path in (link, scratch, task_write, sentinel, outside, repository_target))
        and all(not os.path.lexists(entry[key]) for entry in boundaries for key in ("alias", "directory")))
    report["process_may_still_be_running"] = spec.pop("preflight_execution_incomplete")
    report["passed"] = report["passed"] and report["canaries_removed"] and not report["process_may_still_be_running"]
    # Post-case残存確認。各caseはcommunicate完了を確認しており、ここではrun-rootのopen fileを再走査する。
    residual = runner.scan_run_root_open_files(root)
    token_residual = runner.scan_residual_processes(spec["env"]["P5_RUN_TOKEN"])
    report["residual_scan_evidence"] = {"status": residual["status"], "passed": residual["passed"],
        "scan_pass": residual["scan_pass"], "run_root_open_file_process_count": residual.get("run_root_open_file_process_count"),
        "token_process_scan_pass": token_residual.get("passed") is True,
        "token_process_scan_count": token_residual.get("scan_count"),
        "complete_detection_claimed": False}
    report["passed"] = report["passed"] and residual["passed"] and token_residual.get("passed") is True
    report["ended_at"] = runner.stamp()
    diagnostics = root.parent / ".evidence" / root.name / "preflight.raw.json"
    runner.save(diagnostics, spec.pop("private_preflight_diagnostics", []))
    report["private_diagnostics_sha256"] = runner.sha(diagnostics)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--fingerprint")
    parser.add_argument("--expected-binding-file", type=Path)
    parser.add_argument("--report-output", type=Path,
                        help="private v17 logs内の新規schema3 report fileへ保存する")
    args = parser.parse_args()
    with runner.private_umask():
        runner.require_formal_locations()
        runner.require_source_directory()
        expected_cli = runner.compute_codex_executable_binding(runner.CODEX_EXECUTABLE)
        expected_runtime = runner.compute_python_runtime_binding()
        harness = runner.compute_harness_fingerprint(runner.HERE, codex_executable_binding=expected_cli,
                                                     python_runtime_binding=expected_runtime)
        if args.fingerprint is not None and args.fingerprint != harness:
            raise SystemExit("preflight campaign fingerprint不一致")
        campaign_binding = (runner.load_campaign_binding(args.expected_binding_file, args.expected_binding_file.parent, harness)
                            if args.expected_binding_file else None)
        if campaign_binding and (campaign_binding["record"]["codex_executable"] != expected_cli
                                 or campaign_binding["record"]["python_runtime"] != expected_runtime):
            raise SystemExit("preflight campaign CLI/runtime不一致")
        base = runner.prepare_formal_base() / "preflight"
        runner.private_directory_identity(base, create=True)
        directory = base / ("sandbox-preflight-" + uuid.uuid4().hex)
        runner.private_directory_identity(directory, create=True)
        runner.require_formal_locations(directory)
        fixture = directory / "fixture"
        fixture.mkdir(mode=0o700)
        runner._write_private(fixture / "AGENTS.md", "P5 synthetic fixture\n")
        runner.install_env_canary(fixture, harness)
        version = runner.run_trusted_command([runner.CODEX_EXECUTABLE, "--version"], capture_output=True, text=True, check=True,
                                 env={"PATH": runner.FIXED_PATH}).stdout.strip()
        if version != runner.CLI_VERSION:
            raise SystemExit("CLI版不一致")
        spec = runner.execution_spec(fixture, runner.c6_task(), version, harness)
        spec["campaign_binding"] = campaign_binding
        runner.require_codex_binding(spec, "preflight", expected_cli, spec["binding"]["codex_executable"])
        runner.require_runtime_binding(spec, "preflight", expected_runtime, spec["binding"]["python_runtime"])
        report = check(spec)
        if args.report_output is not None:
            destination = args.report_output
            expected_parent = runner.formal_base() / "drivers/logs/v19-final11"
            if (destination.parent != expected_parent or os.path.lexists(destination)):
                raise SystemExit("preflight report output pathはprivate v17 logsの新規fileに限定されます")
            runner.private_directory_identity(expected_parent)
            runner._write_private(destination, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.cleanup and not report.get("process_may_still_be_running"):
            shutil.rmtree(directory)
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
