#!/usr/bin/env python3
"""実モデルなしでpermission binding、監査、snapshot、再分類の境界を検証する。"""

import contextlib
import importlib.util
import io
import json
import os
import shlex
import signal
import struct
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tomllib
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("p5_run", HERE / "run.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
import sandbox_preflight as preflight
from harness_fingerprint import HARNESS_INPUTS, compute_harness_fingerprint

FAKE = '''#!/usr/bin/env python3.12
import json,os,pathlib,shlex,subprocess,sys,time,tomllib
if "--version" in sys.argv:
    print("codex-cli 0.155.1")
    raise SystemExit(0)
if "sandbox" in sys.argv:
    command=sys.argv[sys.argv.index("--")+1:]
    if "unittest" in command or "pytest" in command:
        raise SystemExit(0)
    raise SystemExit(subprocess.run(command).returncode)
mode=pathlib.Path(__file__).with_name("mode").read_text()
if mode == "fail":
    raise SystemExit(1)
assert "DATABASE_URL" not in os.environ and "SSH_AUTH_SOCK" not in os.environ
assert "CODEX_HOME" in os.environ
prompt=sys.stdin.read()
if "課題ID: C6" in prompt:
    subprocess.run([sys.executable,"-B","migration-progress/progress.py","set","--task","P0",
                    "--status","検証中","--current","fake更新","--next","fake再読込","--blocker","なし"],
                   capture_output=True,check=True)
if mode == "symlink":
    pathlib.Path("docs/plans/unsafe.md").symlink_to("../../AGENTS.md")
if mode == "extra":
    pathlib.Path("benchmark-tmp").mkdir()
    pathlib.Path("benchmark-tmp/unexpected").write_text("unexpected")
if mode == "scratch":
    pathlib.Path(".benchmark-tmp/expected").write_text("expected")
pathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_text("目的 検証 次の一手\\n")
command="python3.12 .benchmark-tmp/network.py" if mode == "unknown" else "pwd; true"
canary_command=@CANARY_COMMAND@
env_config=next(value for value in sys.argv if value.startswith("shell_environment_policy.set="))
tool_env=tomllib.loads(env_config)["shell_environment_policy"]["set"]
if mode == "env_leak":
    tool_env["CODEX_HOME"]=os.environ["CODEX_HOME"]
canary_output=subprocess.run(shlex.split(canary_command),env=tool_env,text=True,capture_output=True,check=True).stdout
print(json.dumps({"type":"thread.started","thread_id":"fixture"}))
print(json.dumps({"type":"turn.started"}))
if mode != "env_missing":
    print(json.dumps({"type":"item.started","item":{"id":"canary","type":"command_execution","command":canary_command,"status":"in_progress"}}))
    print(json.dumps({"type":"item.completed","item":{"id":"canary","type":"command_execution","command":canary_command,"status":"completed","exit_code":0,"aggregated_output":canary_output}}))
print(json.dumps({"type":"item.started","item":{"id":"cmd-1","type":"command_execution","command":command,"status":"in_progress"}}))
print(json.dumps({"type":"item.completed","item":{"id":"cmd-1","type":"command_execution","command":command,"status":"completed","exit_code":0,"aggregated_output":"OK"}}))
print(json.dumps({"type":"item.completed","item":{"id":"answer","type":"agent_message","text":"目的 検証 次"}}))
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":12,"cached_input_tokens":6,"cache_write_input_tokens":0,"output_tokens":3,"total_tokens":15}}))
'''.replace('@CANARY_COMMAND@', repr(runner.ENV_CANARY_COMMAND))


def expect_rejected(call):
    try:
        call()
    except (OSError, RuntimeError, ValueError):
        return
    raise AssertionError("境界違反を受け入れました")


def c1_task():
    return next(task for task in runner.load(runner.BASE / "comparison.json")["tasks"] if task["id"] == "C1")


def fingerprint_test(root):
    copied = root / "repo/docs/codex-direct/migration-benchmark"
    for name in HARNESS_INPUTS:
        destination = Path(os.path.abspath(copied / name))
        runner._write_private(destination, runner.safe_read(Path(os.path.abspath(HERE / name))))
    original = compute_harness_fingerprint(copied)
    assert len(original) == 64 and compute_harness_fingerprint(copied) == original
    module = copied / "harness_fingerprint.py"
    runner._write_private(module, runner.safe_read(module) + b"\n# self-inclusion canary\n")
    assert compute_harness_fingerprint(copied) != original
    input_file = copied / "run.py"
    data = runner.safe_read(input_file)
    changed = compute_harness_fingerprint(copied)
    runner._write_private(input_file, data + b"\n# runtime input canary\n")
    assert compute_harness_fingerprint(copied) != changed
    input_file.unlink()
    input_file.symlink_to(module)
    expect_rejected(lambda: compute_harness_fingerprint(copied))
    input_file.unlink()
    runner._write_private(input_file, data)
    os.link(input_file, copied / "hardlink-canary")
    expect_rejected(lambda: compute_harness_fingerprint(copied))
    print("fingerprint: ordered inputs/self inclusion/source change/link rejection OK", flush=True)


def permission_test(root):
    root.mkdir()
    untouched = (root.stat().st_mode, root.stat().st_mtime_ns, list(root.iterdir()))
    pure = runner.canonical_execution_spec(root, c1_task(), runner.CLI_VERSION, "fixed-harness")
    assert untouched == (root.stat().st_mode, root.stat().st_mtime_ns, list(root.iterdir()))
    assert not (root / ".benchmark-tmp").exists()
    spec = runner.execution_spec(root, c1_task(), runner.CLI_VERSION, "fixed-harness")
    assert spec == pure
    assert runner.derive_canonical_binding(root, c1_task(), runner.CLI_VERSION, "fixed-harness") == spec["binding"]
    assert "P5_RUN_TOKEN" in spec["env"]
    config = tomllib.loads("\n".join(spec["config"]))["permissions"]["p5_fixture"]
    assert "extends" not in config and config["filesystem"][":root"] == "deny"
    assert config["filesystem"][":minimal"] == "read" and config["filesystem"][str(root)] == "read"
    assert config["filesystem"][str(root / ".benchmark-tmp")] == "write" and config["network"]["enabled"] is False
    binding = spec["binding"]
    assert binding["harness_fingerprint"] == "fixed-harness"
    assert binding["codex_executable"]["sha256"] == runner.sha(Path(runner.CODEX_EXECUTABLE).resolve())
    assert binding["tool_environment"]["sha256"] == runner.canonical_digest(spec["env"])
    assert binding["codex_process_environment"]["sha256"] == runner.canonical_digest(runner.process_env(spec))
    assert "CODEX_HOME" not in binding["tool_environment"]["keys"]
    assert "CODEX_HOME" in binding["codex_process_environment"]["keys"]
    assert runner.AUTH_HOME not in json.dumps(binding)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "synthetic-secret"
    try:
        assert "DATABASE_URL" not in runner.limited_env(root)
        assert "synthetic-secret" not in json.dumps(binding)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    tools = tomllib.loads("\n".join(runner.tool_environment_config(spec)))["shell_environment_policy"]
    assert tools["inherit"] == "none" and tools["set"] == spec["env"]
    invocation = runner.sandbox_command(root, c1_task(), ["pwd"], spec)
    assert invocation[invocation.index("--") + 1:invocation.index("--") + 3] == ["/usr/bin/env", "-i"]
    assert not any(token.startswith("CODEX_HOME=") for token in invocation)
    validation = runner.execution_spec(root, c1_task(), runner.CLI_VERSION, "fixed-harness", "validation")
    policy = tomllib.loads("\n".join(validation["config"]))["permissions"]["p5_fixture"]["filesystem"]
    assert [key for key, value in policy.items() if value == "write"] == [str(root / ".benchmark-tmp")]
    other = root.parent / "rebound"
    other.mkdir()
    rebound = runner.execution_spec(other, c1_task(), runner.CLI_VERSION, "fixed-harness")
    assert rebound["binding"]["policy_template_sha256"] == binding["policy_template_sha256"]
    assert rebound["binding"]["profile_sha256"] != binding["profile_sha256"]
    assert rebound["binding"]["root_inode"] != binding["root_inode"]
    shared_parent = root / "existing-shared-parent"
    shared_parent.mkdir(mode=0o755)
    shared_parent.chmod(0o755)
    runner.save(shared_parent / "private.json", {"ok": True})
    assert shared_parent.stat().st_mode & 0o777 == 0o755
    assert (shared_parent / "private.json").stat().st_mode & 0o777 == 0o600
    executable = root / "fake-executable"
    runner._write_private(executable, b"executable before", 0o700)
    original_read, reads = runner.safe_read, []
    def counted_read(path):
        if Path(path) == executable:
            reads.append(path)
        return original_read(path)
    runner.safe_read = counted_read
    try:
        before_hash = runner.executable_sha256(executable)
        assert runner.executable_sha256(executable) == before_hash and len(reads) == 1
        runner._write_private(executable, b"executable after", 0o700)
        assert runner.executable_sha256(executable) != before_hash and len(reads) == 2
        os.link(executable, root / "executable-hardlink")
        expect_rejected(lambda: runner.executable_sha256(executable))
    finally:
        runner.safe_read = original_read
    print("permission: canonical/phase/root/tool+process env/auth hash/executable cache invalidation/harness/parent mode OK", flush=True)


def event_stream(command="pwd", code=0, extras=()):
    active = {"id": "cmd", "type": "command_execution", "command": command, "status": "in_progress"}
    completed = {**active, "status": "failed" if code else "completed", "exit_code": code, "aggregated_output": "private synthetic stdout"}
    return [{"type": "thread.started", "thread_id": "fixture"}, {"type": "turn.started"},
            {"type": "item.started", "item": active}, {"type": "item.completed", "item": completed}, *extras,
            {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}}]


def event_test(root):
    root.mkdir()
    def audit(command="pwd", code=0, extras=()):
        raw = "\n".join(json.dumps(event) for event in event_stream(command, code, extras))
        return runner.safe_events(raw, root / "events.json", root)
    normal = audit("false; true", 1, [{"type": "item.completed", "item": {"id": "patch", "type": "file_change", "status": "failed", "changes": []}}])
    assert normal["event_audit"]["passed"] and normal["attempt_policy"]["passed"]
    assert normal["commands"][0]["cwd_source"] == "not_reported"
    assert normal["commands"][0]["initial_cwd_source"] == "trusted_invocation_-C"
    assert "private synthetic stdout" not in (root / "events.json").read_text()
    regressions = {
        "cat 'unterminated /Users/example/.ssh/id_rsa": "unknown",
        "dd if=/Users/example/.ssh/id_rsa of=/dev/null": "fail",
        "awk '{print}' /Users/example/.ssh/id_rsa": "fail",
        "python3.12 .benchmark-tmp/network.py": "unknown",
    }
    for command, status in regressions.items():
        result = audit(command)
        assert result["event_audit"]["passed"] and result["attempt_policy"]["status"] == status, (command, result)
        assert not result["attempt_policy"]["passed"]
    for command in ("curl https://example.invalid", "cat ../outside", "cat /etc/passwd", "echo x >/tmp/outside",
                    "dd if=README.md of=/tmp/outside", "cat </Users/example/private", "cat README.md;curl https://example.invalid"):
        assert audit(command)["attempt_policy"]["status"] == "fail", command
    for command in ("unknown-program", "bash .benchmark-tmp/anything.sh", "rg --pre node pattern .", "python3.12 -m unittest", ".benchmark-tmp/cat", "/usr/bin/../../tmp/cat"):
        assert audit(command)["attempt_policy"]["status"] == "unknown", command
    for command in ("cat docs/plans/note.md", "rg 'https://example.invalid' README.md", "/bin/zsh -lc 'pwd; true'"):
        assert audit(command)["attempt_policy"]["passed"], command
    detached_attempts = (
        "env -u P5_RUN_TOKEN python3.12 task.py", "env --unset=P5_RUN_TOKEN true",
        "env --unset P5_RUN_TOKEN true", "env -uP5_RUN_TOKEN true", "env -i true",
        "env --ignore-environment true", "unset P5_RUN_TOKEN", "unset -v P5_RUN_TOKEN",
        "export P5_RUN_TOKEN=changed", "P5_RUN_TOKEN=changed true", "env P5_RUN_TOKEN=changed true",
        "declare -x P5_RUN_TOKEN=changed", "typeset P5_RUN_TOKEN=changed", "command unset P5_RUN_TOKEN",
        "setsid python3.12 task.py", "nohup python3.12 task.py", "disown", "daemon task", "launchctl print gui/501",
        "command nohup true", "env FOO=bar setsid true", "exec setsid true", "true &", "true & disown",
        "true &|", "/bin/zsh -lc 'env -u P5_RUN_TOKEN nohup true &'",
        "python3.12 -c \"import os; os.setsid()\"", "python3.12 -c \"import os; os.fork()\"",
        "python3.12 -c \"import os; os.environ.pop('P5_RUN_TOKEN')\"",
        "python3.12 -c \"import os; os.environ['P5_RUN_TOKEN']='changed'\"",
        "python3.12 -c \"import os; os.environ.clear()\"",
        "node -e \"delete process.env.P5_RUN_TOKEN\"",
        "node -e \"require('child_process').spawn('task', [], {detached:true})\"",
    )
    for command in detached_attempts:
        result = audit(command)
        assert result["attempt_policy"]["status"] == "fail", (command, result["attempt_policy"])
    for command in ("echo '&'", r"echo \&", "true && true", "true 2>&1", "echo P5_RUN_TOKEN", "echo 'P5_RUN_TOKEN=example'", "echo setsid"):
        assert audit(command)["attempt_policy"]["passed"], command
    valid_message = {"id": "answer", "type": "agent_message", "text": "目的 検証 次"}
    assert audit(extras=[{"type": "item.completed", "item": valid_message}])["event_audit"]["passed"]
    invalid_items = [
        ("item.completed", {"id": "answer", "type": "agent_message"}),
        ("item.completed", {"type": "agent_message", "text": "本文"}),
        ("item.started", valid_message),
        ("item.completed", {"id": "reason", "type": "reasoning", "text": 5}),
        ("item.completed", {"id": "todo", "type": "todo_list", "items": [{"text": "todo"}]}),
        ("item.completed", {"id": "unknown", "type": "context_compaction"}),
        ("item.completed", {"id": "tool", "type": "mcp_tool_call"}),
    ]
    for kind, item in invalid_items:
        assert not audit(extras=[{"type": kind, "item": item}])["event_audit"]["passed"], item
    orphan = {"type": "item.started", "item": {"id": "orphan", "type": "command_execution", "command": "pwd", "status": "in_progress"}}
    assert not audit(extras=[orphan])["event_audit"]["passed"]
    assert not runner.safe_events("not json", expected_cwd=root)["event_audit"]["passed"]
    assert (root / "events.json").stat().st_mode & 0o777 == 0o600
    print("events: 4 regressions/all-token paths/redirection/unknown code/non-tool schema/lifecycle OK", flush=True)


def snapshot_test(root):
    root.mkdir()
    tree = root / "run-01"
    tree.mkdir()
    runner._write_private(tree / "source", "accepted bytes")
    runner._write_private(tree / ".benchmark-tmp/scratch", "scratch")
    accepted, evidence, manifest = runner.accepted_snapshot(tree)
    assert evidence["matched"] and runner.safe_read(accepted / "source") == b"accepted bytes"
    assert not (accepted / ".benchmark-tmp").exists()
    (tree / "source").write_text("later")
    assert runner.safe_read(accepted / "source") == b"accepted bytes"
    expect_rejected(lambda: runner.accepted_snapshot(tree))
    (tree / "link").symlink_to(accepted / "source")
    expect_rejected(lambda: runner.safe_read(tree / "link"))
    expect_rejected(lambda: runner.tree_manifest(tree))
    expect_rejected(lambda: runner._write_private(tree / "link", "bad"))
    (tree / "link").unlink()
    (tree / "parent-link").symlink_to(accepted, target_is_directory=True)
    expect_rejected(lambda: runner.safe_read(tree / "parent-link/source"))
    (tree / "parent-link").unlink()
    os.link(tree / "source", tree / "hardlink")
    expect_rejected(lambda: runner.safe_read(tree / "source"))
    expect_rejected(lambda: runner._write_private(tree / "source", "bad"))
    (tree / "hardlink").unlink()
    os.mkfifo(tree / "fifo")
    expect_rejected(lambda: runner.tree_manifest(tree))
    (tree / "fifo").unlink()
    race = root / "run-02"
    race.mkdir()
    (race / "one").write_text("before")
    original, reads = runner.safe_read, 0
    def changing_read(path):
        nonlocal reads
        data = original(path)
        if Path(path) == race / "one":
            reads += 1
            if reads == 2:
                (race / "one").write_text("after")
        return data
    runner.safe_read = changing_read
    try:
        expect_rejected(lambda: runner.accepted_snapshot(race))
    finally:
        runner.safe_read = original
    source, destination = root / "fixed-source", root / "fixed-destination"
    runner._write_private(source, b"fixed verified bytes")
    expected_hash = runner.sha(source)
    reads = 0
    def source_swapped(path):
        nonlocal reads
        data = original(path)
        if Path(path) == source:
            reads += 1
            runner._write_private(source, b"untrusted swapped bytes")
        return data
    runner.safe_read = source_swapped
    try:
        runner.copy_verified_bytes(source, destination, expected_hash)
        assert reads == 1 and original(destination) == b"fixed verified bytes"
        expect_rejected(lambda: runner.copy_verified_bytes(source, destination, expected_hash))
    finally:
        runner.safe_read = original
    print("snapshot: links/FIFO/read+copy race/accepted independence/verified-same-bytes TOCTOU OK", flush=True)


def prepare_copy_test(root):
    root.mkdir()
    original_base, original_here, original_b_index = runner.BASE, runner.HERE, runner.B_INDEX
    original_read = runner.safe_read
    def copy_tree(source, destination):
        for name, entry in runner.tree_manifest(source, exclude_internal=False, exclude_bookkeeping=False).items():
            if entry["type"] == "file":
                runner._write_private(destination / name, original_read(source / name), 0o700 if entry["executable"] else 0o600)
    # 原repoではなく複製した固定fixtureだけを差し替える。
    cloned_base, cloned_here = root / "migration-baseline", root / "migration-benchmark"
    copy_tree(original_base, cloned_base)
    copy_tree(original_here / "b-contract", cloned_here / "b-contract")
    runner._write_private(cloned_here / "b-contract-index.json", original_read(original_b_index))
    runner.BASE, runner.HERE, runner.B_INDEX = cloned_base, cloned_here, cloned_here / "b-contract-index.json"
    try:
        index = runner.load(cloned_base / "snapshot-index.json")
        snapshot = next(entry for entry in index["entries"] if entry["repo"] == "agent_crew" and entry["source"] == "scripts/crew")
        fixed = cloned_base / snapshot["snapshot"]
        data = original_read(fixed)
        for serial, (condition, target, destination_name, expected) in enumerate([
            ("A", fixed, "scripts/crew", snapshot["sha256"]),
            ("B", cloned_here / "b-contract/agent_crew/AGENTS.md", "AGENTS.md",
             runner.load(runner.B_INDEX)["files"]["agent_crew/AGENTS.md"]),
        ], 1):
            # 前caseのsourceを戻してから、read直後に異なるbytesへatomic置換する。
            runner._write_private(fixed, data)
            reads = []
            def swapped_source(path):
                value = original_read(path)
                if Path(path) == target:
                    reads.append(path)
                    runner._write_private(target, b"changed after verified read")
                return value
            runner.safe_read = swapped_source
            prepared, _, _ = runner.prepare("C1", condition, 1, str(root / "campaign"), f"run-{serial:02}")
            runner.safe_read = original_read
            assert len(reads) == 1 and runner.sha(prepared / destination_name) == expected
            assert runner.sha(target) != expected
    finally:
        runner.BASE, runner.HERE, runner.B_INDEX, runner.safe_read = original_base, original_here, original_b_index, original_read
    print("prepare: real A fixture/B contract source swapped after read; copied verified bytes only OK", flush=True)


def preflight_test(root):
    root.mkdir()
    runner._write_private(root / "AGENTS.md", "fixture")
    for name in c1_task()["input"] + c1_task()["fixture"]:
        runner._write_private(root / name, "fixed fixture")
    spec = runner.execution_spec(root, c1_task(), runner.CLI_VERSION, "fixture-fingerprint")
    original = preflight.run_case
    seen = []
    def fake_case(name, passed_spec, command, expected):
        assert passed_spec is spec
        seen.append(name)
        if expected == "allow":
            result = subprocess.run(command, cwd=root, env=spec["env"], capture_output=True)
            assert result.returncode == 0, result.stderr
        return {"name": name, "expected": expected, "outcome": "allowed" if expected == "allow" else "sandbox_denied",
                "exit_code": 0 if expected == "allow" else 1, "binding_sha256": runner.canonical_digest(spec["binding"]),
                "command_sha256": runner.canonical_digest(command), "stdout_sha256": "0" * 64, "stderr_sha256": "0" * 64}
    preflight.run_case = fake_case
    try:
        report = preflight.check(spec)
        assert report["passed"] and report["binding"] == spec["binding"] and report["canaries_removed"]
        assert runner.validate_preflight_evidence(report, spec)
        for mutation in ({"cases": report["cases"][:-1]}, {"cases": report["cases"] + report["cases"][:1]},
                         {"canaries_removed": False}, {"postconditions": {}}, {"tool_environment_scope": "exec_verified"}):
            assert not runner.validate_preflight_evidence({**report, **mutation}, spec)
        changed_cases = json.loads(json.dumps(report["cases"]))
        changed_cases[-1]["binding_sha256"] = "0" * 64
        assert not runner.validate_preflight_evidence({**report, "cases": changed_cases}, spec)
        assert {"tool_environment_exact", "outside_private_read", "symlink_outside_private_read", "repository_read", "repository_write", "network_connect"} <= set(seen)
        preflight.run_case = lambda name, *_args: {"name": name, "expected": "allow", "outcome": "preflight_error"}
        assert not preflight.check(spec)["passed"]
    finally:
        preflight.run_case = original
    print("preflight: exact binding/tool env/canary cleanup/fail closed OK (sandbox outcomes mocked)", flush=True)


def preflight_timeout_test(root):
    root.mkdir()
    runner._write_private(root / "AGENTS.md", "fixture")
    spec = runner.execution_spec(root, runner.c6_task(), runner.CLI_VERSION, "fixture-fingerprint")
    originals = preflight.subprocess.Popen, runner.os.kill, runner.os.killpg
    processes, signals = [], []
    class MockCanary:
        pid = 987654321
        returncode = None
        def __init__(self):
            self.stdin, self.stdout, self.stderr = None, io.StringIO(), io.StringIO()
        def communicate(self, **_kwargs):
            raise subprocess.TimeoutExpired("synthetic canary", 20, output=b"partial", stderr=b"diagnostic")
        def kill(self):
            raise AssertionError("preflight Popen.kill禁止")
        def terminate(self):
            raise AssertionError("preflight Popen.terminate禁止")
        def send_signal(self, _signal):
            raise AssertionError("preflight Popen.send_signal禁止")
    def popen(*_args, **_kwargs):
        process = MockCanary()
        processes.append(process)
        return process
    def forbidden_signal(*args):
        signals.append(args)
        raise AssertionError("preflightで自動killしました")
    preflight.subprocess.Popen, runner.os.kill, runner.os.killpg = popen, forbidden_signal, forbidden_signal
    try:
        report = preflight.check(spec)
        assert not report["passed"] and report["process_may_still_be_running"]
        assert len(processes) == 1 and not signals
        assert report["cases"][0]["exit_code"] == "timeout"
        assert all(case["outcome"] == "not_run_preflight_error" for case in report["cases"][1:])
        assert "987654321" not in json.dumps(report)
        diagnostics = root.parent / ".evidence" / root.name / "preflight.raw.json"
        assert diagnostics.stat().st_mode & 0o777 == 0o600
        detail = runner.load(diagnostics)[0]
        assert detail["process_may_still_be_running"] and detail["leader_pid_at_launch"] == MockCanary.pid
        assert not detail["automatic_termination"]
    finally:
        preflight.subprocess.Popen, runner.os.kill, runner.os.killpg = originals
    print("preflight timeout: no kill/next case blocked/private diagnostic/no model (mock) OK", flush=True)


def fake_preflight_report(spec):
    return {"schema": 3, "passed": True, "binding": spec["binding"], "cli_version": runner.CLI_VERSION,
            "binding_comparison": "entire_canonical_binding_equal_before_model",
            "tool_environment_scope": "auxiliary_env_i_probe_not_actual_exec_tool",
            "sandbox_initialized": True, "canaries_removed": True,
            "postconditions": {name: True for name in ("canary_writes_observed", "outside_writes_absent",
                "private_sentinel_unchanged", "task_file_contents_unchanged", "binding_unchanged")},
            "cases": [{"name": name, "expected": expected,
                "outcome": "allowed" if expected == "allow" else "sandbox_denied", "exit_code": 0 if expected == "allow" else 1,
                "binding_sha256": runner.canonical_digest(spec["binding"]), "command_sha256": "0" * 64,
                "stdout_sha256": "0" * 64, "stderr_sha256": "0" * 64}
                for name, expected in runner.required_preflight_cases(spec).items()]}


def clean_process_evidence(_token):
    return {"status": "pass", "passed": True, "scan_pass": True, "detected_count": 0, "kill_count": 0,
            "remaining_count": 0, "scan_count": 3, "clean_after_scan": True,
            "detection_scope": "exact_inherited_environment_token_including_detached_sessions",
            "complete_descendant_detection_claimed": False}


def integration_test(root):
    root.mkdir()
    fake = root / "codex"
    fake.write_text(FAKE)
    fake.chmod(0o700)
    originals = runner.CODEX_EXECUTABLE, runner.per_run_preflight, runner.CLI_TIMEOUT_SECONDS, runner.scan_residual_processes
    runner.CODEX_EXECUTABLE = str(fake)
    runner.per_run_preflight = fake_preflight_report
    runner.scan_residual_processes = clean_process_evidence
    fingerprint = compute_harness_fingerprint(HERE)
    campaign = root / ("p5-" + fingerprint[:16])
    summary_path = campaign / "batch-summary.json"
    runner.save(summary_path, {"schema": 2, "campaign": campaign.name, "fingerprint": fingerprint})
    serial = 0
    def invoke(task="C1", mode="normal", expected_exit=None):
        nonlocal serial
        serial += 1
        (root / "mode").write_text(mode)
        args = SimpleNamespace(task=task, condition="A", repeat=1, run_id=f"run-{serial:02}", campaign=str(campaign), fingerprint=fingerprint)
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                runner.run(args)
            except SystemExit as error:
                assert expected_exit is not None and error.code == expected_exit
            else:
                assert expected_exit is None
        path = campaign / args.run_id / ".benchmark-result.json"
        return args, runner.load(path), path
    try:
        args, result, result_path = invoke(mode="scratch")
        assert result["pass_preliminary"], result
        assert result["run_id"] == "run-01" and result["cached_input_tokens"] == 6
        assert result["isolation_gate"]["binding"] == result["isolation_gate"]["preflight_binding"]
        assert result["isolation_gate"]["env_canary_pass"] and result["env_canary_evidence"]["passed"]
        assert result["isolation_gate"]["residual_process_count"] == 0 and result["isolation_gate"]["residual_scan_pass"]
        assert runner.sha(campaign / result["preflight_evidence_relative_path"]) == result["preflight_evidence_sha256"]
        assert runner.validate_preflight_evidence(runner.load(campaign / result["preflight_evidence_relative_path"]),
                runner.canonical_execution_spec(result_path.parent, c1_task(), runner.CLI_VERSION, fingerprint))
        assert result["validation"]["binding"]["phase"] == "validation" and result["validation"]["manifest_unchanged"]
        assert result["validation"]["derived_from_model_profile_sha256"] == result["isolation_gate"]["binding"]["profile_sha256"]
        raw = campaign / result["raw_event_evidence"]["path_relative_to_campaign"]
        assert raw.stat().st_mode & 0o777 == 0o600
        record_hash, raw_hash = runner.sha(result_path), runner.sha(raw)
        report_path = campaign / ".reviews/run-01-replay.json"
        replay = runner.reclassify_result(result_path, report_path)
        assert replay["raw_event_sha256"] == raw_hash and replay["source_result_sha256"] == record_hash
        assert replay["event_audit"] == result["event_audit"] and replay["attempt_policy"] == result["attempt_policy"]
        assert replay["env_canary_evidence"] == result["env_canary_evidence"]
        assert runner.sha(result_path) == record_hash and runner.sha(raw) == raw_hash
        assert replay["classifier_sha256"] == runner.sha(HERE / "run.py")
        assert replay["harness_fingerprint"] == fingerprint and replay["run_id"] == args.run_id
        assert report_path.stat().st_mode & 0o777 == 0o600
        assert report_path.parent.stat().st_mode & 0o777 == 0o700
        # 出力先をaccepted/evidence/元run/別run/共有parentへ広げられない。
        accepted_before = runner.tree_manifest(campaign / ".accepted/run-01", exclude_bookkeeping=False)
        for wrong in (campaign / ".accepted/run-01/replay.json", raw, result_path,
                      campaign / "run-02/replay.json", campaign / ".reviews/run-02-replay.json",
                      campaign / ".reviews/arbitrary.json", root / "replay.json",
                      raw.parent / "../run-01/events.raw.jsonl"):
            expect_rejected(lambda wrong=wrong: runner.reclassify_result(result_path, wrong))
        assert runner.tree_manifest(campaign / ".accepted/run-01", exclude_bookkeeping=False) == accepted_before
        assert runner.sha(result_path) == record_hash and runner.sha(raw) == raw_hash
        # record、campaign summary、現行harnessのいずれのfingerprint不一致も拒否する。
        result_original = runner.safe_read(result_path)
        summary_original = runner.safe_read(summary_path)
        runner.save(result_path, {**result, "fingerprint": "0" * 64})
        expect_rejected(lambda: runner.reclassify_result(result_path, report_path))
        runner._write_private(result_path, result_original)
        runner.save(summary_path, {"schema": 2, "campaign": campaign.name, "fingerprint": "0" * 64})
        expect_rejected(lambda: runner.reclassify_result(result_path, report_path))
        runner._write_private(summary_path, summary_original)
        original_compute = runner.compute_harness_fingerprint
        runner.compute_harness_fingerprint = lambda _here: "0" * 64
        try:
            expect_rejected(lambda: runner.reclassify_result(result_path, report_path))
        finally:
            runner.compute_harness_fingerprint = original_compute
        # exact pathでもsymlinkを介してrawへ書けない。共有parentのmodeも変えない。
        report_original = runner.safe_read(report_path)
        report_path.unlink()
        report_path.symlink_to(raw)
        expect_rejected(lambda: runner.reclassify_result(result_path, report_path))
        report_path.unlink()
        runner._write_private(report_path, report_original)
        root_mode = root.stat().st_mode & 0o777
        report_path.parent.chmod(0o755)
        runner.reclassify_result(result_path, report_path)
        assert report_path.parent.stat().st_mode & 0o777 == 0o700
        assert root.stat().st_mode & 0o777 == root_mode
        assert runner.sha(result_path) == record_hash and runner.sha(raw) == raw_hash
        raw_original = runner.safe_read(raw)
        runner._write_private(raw, raw_original + b"\n")
        expect_rejected(lambda: runner.reclassify_result(result_path))
        runner._write_private(raw, raw_original)
        expect_rejected(lambda: runner.run(args))
        _, unknown, unknown_path = invoke(mode="unknown")
        assert unknown["attempt_policy"]["status"] == "unknown" and not unknown["pass_preliminary"]
        assert unknown["acceptance_gate"]["passed"] and runner.reclassify_result(unknown_path)["attempt_policy"]["status"] == "unknown"
        _, unsafe, _ = invoke(mode="symlink")
        assert not unsafe["pass_preliminary"] and unsafe["validation"]["exit_code"] == "not_run"
        _, extra, _ = invoke(mode="extra")
        assert "benchmark-tmp/unexpected" in extra["scope_violations"]
        _, c6, c6_path = invoke("C6")
        assert c6["pass_preliminary"] and c6["c6_validator_consistent"], c6
        accepted = campaign / ".accepted" / c6_path.parent.name
        assert not (accepted / "validate_c6.py").exists()
        assert c6["validation"]["command"][2].startswith(".benchmark-tmp/validate_c6-")
        assert c6["validation"]["manifest_before_sha256"] == c6["validation"]["manifest_after_sha256"]
        assert c6["snapshot_evidence"]["accepted_sha256"] == c6["validation"]["manifest_after_sha256"]
        # 非scratchのbookkeeping名もvalidatorの書換えとして必ず拒否する。
        original_execute = runner.execute_command
        def mutate_snapshot(_command, validation_root, *_args, **_kwargs):
            runner._write_private(validation_root / ".benchmark-answer.txt", "unexpected")
            return 0, "OK", ""
        runner.execute_command = mutate_snapshot
        try:
            invalid = runner.validate(c1_task(), campaign / ".accepted/run-01", harness_fingerprint="fixture-fingerprint")
            assert invalid["exit_code"] == "validator_changed_snapshot" and not invalid["manifest_unchanged"]
        finally:
            runner.execute_command = original_execute
        for mode in ("env_missing", "env_leak"):
            _, invalid_environment, _ = invoke(mode=mode)
            assert not invalid_environment["isolation_gate"]["passed"] and not invalid_environment["isolation_gate"]["env_canary_pass"]
            assert invalid_environment["validation"]["exit_code"] == "not_run"
        def residual_found(token):
            return {**clean_process_evidence(token), "status": "fail", "passed": False, "detected_count": 1, "kill_count": 0}
        runner.scan_residual_processes = residual_found
        _, detached, _ = invoke()
        assert not detached["isolation_gate"]["passed"] and detached["isolation_gate"]["residual_process_count"] > 0
        assert detached["validation"]["exit_code"] == "not_run"
        runner.scan_residual_processes = clean_process_evidence
        _, failed, _ = invoke(mode="fail")
        assert failed["cli_exit"] == 1 and not failed["pass_preliminary"]
        original_snapshot, original_validate = runner.accepted_snapshot, runner.validate
        def forbidden_snapshot(*_args, **_kwargs):
            raise AssertionError("timeout/signal後にsnapshot/validatorを実行しました")
        runner.accepted_snapshot = runner.validate = forbidden_snapshot
        try:
            for incomplete_code in ("timeout", "signal:15"):
                def interrupted_execute(_command, _root, env, *_args, **_kwargs):
                    # 完全な成功eventがあっても、実行完了未確認なら受入禁止。
                    events = event_stream(runner.ENV_CANARY_COMMAND)
                    events[3]["item"]["aggregated_output"] = json.dumps({key: value for key, value in env.items() if key != "CODEX_HOME"})
                    return incomplete_code, "\n".join(json.dumps(event) for event in events), ""
                runner.execute_command = interrupted_execute
                _, timed, timed_path = invoke(expected_exit=143 if incomplete_code == "signal:15" else None)
                assert timed["cli_exit"] == incomplete_code and not timed["pass_preliminary"]
                assert not timed["isolation_gate"]["passed"] and not timed["acceptance_gate"]["passed"]
                assert timed["validation"]["exit_code"] == "not_run" and not timed["snapshot_evidence"]["matched"]
                assert timed["residual_process_evidence"]["model"]["kill_count"] == 0
                assert not (campaign / ".accepted" / timed_path.parent.name).exists()
        finally:
            runner.execute_command, runner.accepted_snapshot, runner.validate = original_execute, original_snapshot, original_validate
        runner.execute_command = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preflight失敗後にmodelを起動"))
        runner.per_run_preflight = lambda spec: {"passed": True, "binding": {**spec["binding"], "harness_fingerprint": "wrong"}}
        try:
            _, blocked, _ = invoke()
            assert blocked["cli_exit"] == "not_run" and not blocked["isolation_gate"]["preflight_bound"]
        finally:
            runner.execute_command = original_execute
    finally:
        runner.CODEX_EXECUTABLE, runner.per_run_preflight, runner.CLI_TIMEOUT_SECONDS, runner.scan_residual_processes = originals
    print("integration: 4 gates/exact replay path/fingerprint+hash tamper/non-mutating result/C6 scratch validator/full manifest/timeout/binding block OK", flush=True)


def environment_canary_test(root):
    root.mkdir()
    expected = runner.limited_env(root, "fixture-fingerprint")
    command = runner.ENV_CANARY_COMMAND
    def audit(canary_command=command, output=None, prefix=()):
        events = event_stream(canary_command)
        events[3]["item"]["aggregated_output"] = json.dumps(expected) if output is None else output
        if prefix:
            events[2:2] = prefix
        return runner.safe_events("\n".join(json.dumps(event) for event in events), expected_cwd=root, expected_env=expected)
    assert audit()["env_canary_evidence"]["passed"]
    assert audit("/bin/zsh -lc " + shlex.quote(command))["env_canary_evidence"]["passed"]
    assert not audit(command + "; true")["env_canary_evidence"]["passed"]
    assert not audit("pwd")["env_canary_evidence"]["passed"]
    assert not audit(output="{}")["env_canary_evidence"]["passed"]
    assert not audit(output=json.dumps({**expected, "CODEX_HOME": "/synthetic/auth"}))["env_canary_evidence"]["passed"]
    assert not audit(output=json.dumps({key: value for key, value in expected.items() if key != "P5_RUN_TOKEN"}))["env_canary_evidence"]["passed"]
    assert not audit(output=json.dumps({**expected, "P5_RUN_TOKEN": "different"}))["env_canary_evidence"]["passed"]
    patch = {"type": "item.completed", "item": {"id": "patch", "type": "file_change", "status": "completed", "changes": []}}
    assert not audit(prefix=[patch])["env_canary_evidence"]["passed"]
    prior = event_stream("pwd")[2:4]
    for event in prior:
        event["item"]["id"] = "prior"
    assert not audit(prefix=prior)["env_canary_evidence"]["passed"]
    evidence = json.dumps(audit())
    assert expected["P5_RUN_TOKEN"] not in evidence and expected["HOME"] not in evidence
    print("env canary: actual command/order/strict env/missing/leak/token tamper/no public values OK", flush=True)


def residual_process_test():
    token = "a" * 64
    marker = ("P5_RUN_TOKEN=" + token).encode()
    # argvに同じ文字列があっても環境には存在しない。
    payload = struct.pack("=i", 2) + b"/usr/bin/python\0\0" + b"python\0" + marker + b"\0PATH=/usr/bin\0"
    assert marker not in runner.parse_macos_procargs_environment(payload)
    with_env = payload + marker + b"\0"
    assert marker in runner.parse_macos_procargs_environment(with_env)
    originals = runner.candidate_process_ids, runner.process_environment_entries, runner.os.kill, runner.time.sleep
    processes = {901: (marker,), 902: (marker + b"-suffix",), 903: (b"OTHER=" + marker,), 904: (b"PATH=/usr/bin",)}
    calls = []
    runner.candidate_process_ids = lambda: list(processes)
    runner.process_environment_entries = lambda pid: processes[pid]
    runner.time.sleep = lambda _seconds: None
    def kill(pid, signum):
        calls.append((pid, signum))
        raise AssertionError("残留scanがPIDを自動killしました")
    runner.os.kill = kill
    try:
        result = runner.scan_residual_processes(token)
        # 901は元group外/setsid済みを表す。検出するがPIDへsignalを送らない。
        assert calls == [] and result["detected_count"] == 1 and result["kill_count"] == 0
        assert not result["clean_after_scan"] and not result["passed"] and result["scan_count"] == 3
        assert set(processes) == {901, 902, 903, 904}
        del processes[901]  # trustedテスト側で終了を模擬する。
        assert runner.scan_residual_processes(token)["passed"]
        processes[905] = (marker,)
        reads = 0
        def reused_pid(pid):
            nonlocal reads
            if pid == 905:
                reads += 1
                return (marker,) if reads == 1 else (b"PATH=/usr/bin",)
            return processes[pid]
        runner.process_environment_entries = reused_pid
        result = runner.scan_residual_processes(token)
        assert calls == [] and result["detected_count"] == 1 and not result["passed"]
        assert result["clean_after_scan"] and result["kill_count"] == 0
        runner.process_environment_entries = lambda _pid: (_ for _ in ()).throw(PermissionError("mock denied"))
        result = runner.scan_residual_processes(token)
        assert not result["scan_pass"] and not result["passed"] and calls == []
        assert "901" not in json.dumps(result) and token not in json.dumps(result)
    finally:
        runner.candidate_process_ids, runner.process_environment_entries, runner.os.kill, runner.time.sleep = originals
    print("residual: detached exact-env scan/argv false positive/PID reuse/no kill/unrelated preservation/fail closed OK (mock)", flush=True)


def process_test(root):
    root.mkdir()
    originals = runner.subprocess.Popen, runner.os.kill, runner.os.killpg
    created, signals = [], []
    mode = "normal"
    class MockProcess:
        pid = 123456789
        returncode = 0
        def __init__(self):
            self.stdin, self.stdout, self.stderr = io.StringIO(), io.StringIO(), io.StringIO()
            self.calls = 0
        def communicate(self, **_kwargs):
            self.calls += 1
            if mode == "timeout":
                raise subprocess.TimeoutExpired("mock", 1, output=b"partial raw", stderr=b"partial diagnostic")
            if mode == "signal":
                runner.terminate_handler(signal.SIGTERM, None)
            return "complete raw", ""
        def kill(self):
            raise AssertionError("Popen.kill禁止")
        def terminate(self):
            raise AssertionError("Popen.terminate禁止")
        def send_signal(self, _signal):
            raise AssertionError("Popen.send_signal禁止")
        def wait(self, **_kwargs):
            raise AssertionError("timeout後のwait禁止")
    def popen(*_args, **_kwargs):
        process = MockProcess()
        created.append(process)
        return process
    def forbidden_signal(*args):
        signals.append(args)
        raise AssertionError("PID/PGID自動signal禁止")
    runner.subprocess.Popen, runner.os.kill, runner.os.killpg = popen, forbidden_signal, forbidden_signal
    try:
        for mode, expected in (("normal", 0), ("timeout", "timeout"), ("signal", "signal:15")):
            target = root / mode / "run-01"
            target.mkdir(parents=True)
            code, stdout, _stderr = runner.execute_command(["mock"], target, {}, 1)
            assert code == expected and created[-1].calls == 1 and not signals
            assert all(getattr(created[-1], name).closed for name in ("stdin", "stdout", "stderr"))
            if mode != "normal":
                evidence = target.parent / ".evidence/run-01/process-model-interruption.json"
                diagnostic = runner.load(evidence)
                assert evidence.stat().st_mode & 0o777 == 0o600
                assert diagnostic["process_may_still_be_running"] and not diagnostic["automatic_termination"]
            else:
                assert stdout == "complete raw"
        mode = "signal"
        try:
            runner.run_trusted_command(["mock helper"], capture_output=True, text=True, check=True)
        except runner.RunSignal as error:
            assert error.code == 143 and not signals
        else:
            raise AssertionError("補助commandのsignalを握り潰した")
        # validator timeoutでは、実行後manifestを読まず不合格を返す。
        validation_root = root / "validation"
        validation_root.mkdir()
        original_manifest = runner.tree_manifest
        manifests = []
        def once_manifest(*_args, **_kwargs):
            manifests.append(True)
            assert len(manifests) == 1, "timeout後にvalidator snapshotを読んだ"
            return {}
        runner.tree_manifest = once_manifest
        mode = "timeout"
        try:
            result = runner.validate(c1_task(), validation_root, timeout=1)
            assert result["exit_code"] == "timeout" and not result["manifest_unchanged"] and not signals
        finally:
            runner.tree_manifest = original_manifest
        try:
            runner.terminate_handler(signal.SIGTERM, None)
        except runner.RunSignal as error:
            assert error.code == 143 and not signals
        else:
            raise AssertionError("signalをfail-closed exitへ変換しなかった")
    finally:
        runner.subprocess.Popen, runner.os.kill, runner.os.killpg = originals
    print("process: normal/timeout/signal no kill+killpg/no wait/private diagnostic/no post-timeout validation (mock) OK", flush=True)


def c6_process_test(root):
    root.mkdir()
    spec = importlib.util.spec_from_file_location("p5_c6_validator", HERE / "validate_c6.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    originals = validator.subprocess.Popen, runner.os.kill, runner.os.killpg
    mode, signals, created = "normal", [], []
    class MockReload:
        pid = 192837465
        returncode = 0
        def __init__(self):
            self.stdin, self.stdout, self.stderr = None, io.StringIO(), io.StringIO()
        def communicate(self, **_kwargs):
            if mode == "timeout":
                raise subprocess.TimeoutExpired("C6 synthetic reload", 10)
            if mode == "exception":
                raise OSError("synthetic observation failure")
            if mode == "interrupt":
                raise KeyboardInterrupt()
            return "P0 [検証中]", ""
        def kill(self):
            raise AssertionError("C6 Popen.kill禁止")
        def terminate(self):
            raise AssertionError("C6 Popen.terminate禁止")
        def send_signal(self, _signal):
            raise AssertionError("C6 Popen.send_signal禁止")
    def popen(*_args, **_kwargs):
        process = MockReload()
        created.append(process)
        return process
    def forbidden_signal(*args):
        signals.append(args)
        raise AssertionError("C6でPID/PGIDを自動killしました")
    validator.subprocess.Popen, runner.os.kill, runner.os.killpg = popen, forbidden_signal, forbidden_signal
    try:
        for mode in ("normal", "timeout", "exception", "interrupt"):
            target = root / mode
            (target / ".benchmark-tmp").mkdir(parents=True)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                try:
                    completed = validator.run_reload_no_kill(target / "progress.py", target)
                except SystemExit as error:
                    assert mode != "normal" and error.code == 1
                else:
                    assert mode == "normal" and completed.returncode == 0 and "P0" in completed.stdout
            assert not signals and created[-1].stdout.closed and created[-1].stderr.closed
            if mode != "normal":
                diagnostic = target / ".benchmark-tmp/c6-reload-interruption.json"
                assert diagnostic.stat().st_mode & 0o777 == 0o600
                detail = runner.load(diagnostic)
                assert not detail["automatic_termination"] and detail["process_may_still_be_running"]
                assert "192837465" not in output.getvalue()
    finally:
        validator.subprocess.Popen, runner.os.kill, runner.os.killpg = originals
    print("C6 reload: normal/timeout/exception/interrupt no kill/private scratch evidence/validation fail (mock) OK", flush=True)


def main():
    # managed macOS sandboxのmount cleanup停止を避け、private test rootを保持する。
    root = Path(tempfile.mkdtemp(prefix="p5-security-selftest-", dir="/private/tmp"))
    assert len(runner.verified_a_inputs()) == 1 and len(runner.verified_b_inputs()) == 7
    fingerprint_test(root / "fingerprint")
    permission_test(root / "permissions")
    event_test(root / "events")
    environment_canary_test(root / "env-canary")
    residual_process_test()
    snapshot_test(root / "snapshots")
    prepare_copy_test(root / "prepare-copy")
    preflight_test(root / "preflight")
    preflight_timeout_test(root / "preflight-timeout")
    integration_test(root / "integration")
    process_test(root / "process")
    c6_process_test(root / "c6-process")
    print("P5 security selftest: all passed; 実sandbox/実model呼出しなし; private root:", root)


if __name__ == "__main__":
    main()
