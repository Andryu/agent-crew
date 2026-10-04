#!/usr/bin/env python3
"""実モデルなしでpermission binding、監査、snapshot、再分類の境界を検証する。"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pwd
import shlex
import signal
import struct
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tomllib
import fnmatch
from unittest.mock import patch
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("p5_run", HERE / "run.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
DRIVER_SPEC = importlib.util.spec_from_file_location("p5_driver_source", HERE / "driver.py")
driver_source = importlib.util.module_from_spec(DRIVER_SPEC)
DRIVER_SPEC.loader.exec_module(driver_source)
import sandbox_preflight as preflight
from harness_fingerprint import HARNESS_INPUTS
import harness_fingerprint as fingerprint_module


def compute_harness_fingerprint(here, **kwargs):
    # 合成CLIを使う統合caseでは、campaignも同じ合成実体へbindingする。
    kwargs.setdefault("codex_executable_binding", runner.compute_codex_executable_binding(runner.CODEX_EXECUTABLE))
    return fingerprint_module.compute_harness_fingerprint(here, **kwargs)

FAKE = '''#!/usr/bin/env python3.12
import json,os,pathlib,pwd,shlex,subprocess,sys,time,tomllib
if "--version" in sys.argv:
    mode_path=pathlib.Path(__file__).with_name("mode")
    print("codex-cli 0.155.1" if mode_path.exists() and mode_path.read_text() == "version_mismatch" else "codex-cli 0.160.0")
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
tool_env.update({"CODEX_CI":"1","CODEX_PERMISSION_PROFILE":"p5_fixture","CODEX_SANDBOX":"seatbelt",
 "CODEX_SANDBOX_NETWORK_DISABLED":"1","CODEX_SESSION_ID":"abcdefab-cdef-7abc-8def-abcdefabcdef",
 "CODEX_THREAD_ID":"abcdefab-cdef-7abc-8def-abcdefabcdee","CODEX_VERSION":"0.160.0",
 "COLORTERM":"","GH_PAGER":"cat","GIT_PAGER":"cat","LC_CTYPE":"C.UTF-8",
 "LOGNAME":pwd.getpwuid(os.getuid()).pw_name,"NO_COLOR":"1","OLDPWD":str(pathlib.Path.cwd()),
 "PAGER":"cat","PWD":str(pathlib.Path.cwd()),"SHLVL":"0","TERM":"dumb",
 "_":shlex.split(canary_command)[0]})
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
    runner.install_env_canary(root)
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
    assert {key for key, value in config["filesystem"].items() if value == "read"} == {
        ":minimal", str(root), str(runner.PYTHON_RUNTIME)}
    assert str(Path.home()) not in config["filesystem"] and str(Path.home() / ".local") not in config["filesystem"]
    assert config["filesystem"][str(root / ".benchmark-tmp")] == "write" and config["network"]["enabled"] is False
    binding = spec["binding"]
    assert binding["harness_fingerprint"] == "fixed-harness"
    assert binding["env_canary_script"]["sha256"] == runner.digest_bytes(runner.ENV_CANARY_BYTES)
    assert binding["env_canary_script"]["command_sha256"] == runner.digest_bytes(runner.ENV_CANARY_COMMAND.encode())
    runner._write_private(root / runner.ENV_CANARY_NAME, runner.ENV_CANARY_BYTES + b"# tamper\n")
    expect_rejected(lambda: runner.derive_canonical_binding(root, c1_task(), runner.CLI_VERSION, "fixed-harness"))
    runner._write_private(root / runner.ENV_CANARY_NAME, runner.ENV_CANARY_BYTES)
    assert runner.derive_canonical_binding(root, c1_task(), runner.CLI_VERSION, "fixed-harness")["env_canary_script"]["sha256"] == binding["env_canary_script"]["sha256"]
    assert binding["codex_executable"]["sha256"] == runner.sha(Path(runner.CODEX_EXECUTABLE).resolve())
    runtime = binding["python_runtime"]
    assert runtime == fingerprint_module.compute_python_runtime_binding()
    assert runtime["root_realpath"] == str(runner.PYTHON_RUNTIME)
    assert runtime["executable_realpath"] == str(Path(sys.executable).resolve())
    assert runtime["executable_sha256"] == runner.sha(Path(runner.PYTHON_EXECUTABLE))
    assert runtime["root_device"] == runner.PYTHON_RUNTIME.stat().st_dev
    assert runtime["root_inode"] == runner.PYTHON_RUNTIME.stat().st_ino
    assert runtime["python_version"] == [3, 12, 13] and runtime["architecture"] == "arm64"
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
    assert {key for key, value in policy.items() if value == "read"} == {":minimal", str(root), str(runner.PYTHON_RUNTIME)}
    assert validation["binding"]["python_runtime"] == binding["python_runtime"]
    other = root.parent / "rebound"
    other.mkdir()
    runner.install_env_canary(other)
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


def prompt_contract_test():
    for task in (c1_task(), runner.c6_task()):
        prompt = runner.prompt_for(task)
        assert runner.ENV_CANARY_COMMAND in prompt
        for required in ("heredoc", "here-string", "process substitution", "<<", "<<<", "<(、>(",
                         "/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp",
                         runner.PYTHON_EXECUTABLE + " -I -B -c", ".benchmark-tmp/", "相対script fileの実行はbytesを固定できないため禁止"):
            assert required in prompt, (task["id"], required)
        assert "python -c" not in prompt
    print("prompt: fixed absolute Python -I -B -c / relative script禁止 OK", flush=True)


def python_runtime_test(root):
    root.mkdir()
    runner.install_env_canary(root)
    spec = runner.execution_spec(root, c1_task(), runner.CLI_VERSION, "runtime-regression")
    assert spec["env"]["PATH"].split(os.pathsep)[0] == str(Path(runner.PYTHON_EXECUTABLE).parent)
    assert Path(runner.PYTHON_EXECUTABLE).parent.parent == runner.PYTHON_RUNTIME
    assert not Path(runner.PYTHON_EXECUTABLE).is_symlink()
    # 従来profileで読めるsystem PATHだけだと、端末上にもPython 3.12は存在せずexit 127となる。
    # OS sandboxのdeny再現ではなく、同じenv起動失敗と実runtime解決を確認する回帰試験。
    failed = runner.run_trusted_command(["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "python3.12", "-B", "-c", "print('runtime-ok')"],
        cwd=root, capture_output=True, text=True)
    assert failed.returncode == 127 and "No such file or directory" in failed.stderr, failed
    assert preflight.classify_denial(failed.returncode, failed.stdout, failed.stderr) == "preflight_error"
    for executable in ("python3.12", runner.PYTHON_EXECUTABLE):
        executed = runner.run_trusted_command([executable, "-I", "-B", "-c",
            "import json,sys; print(json.dumps({'executable':sys.executable,'version':list(sys.version_info[:2])}))"],
            cwd=root, env=spec["env"], capture_output=True, text=True, check=True)
        assert json.loads(executed.stdout) == {"executable": runner.PYTHON_EXECUTABLE, "version": [3, 12]}
    assert shlex.split(runner.ENV_CANARY_COMMAND)[0] == runner.PYTHON_EXECUTABLE
    checked = runner.run_trusted_command(preflight.runtime_command(spec["binding"]["python_runtime"]),
        cwd=root, env=spec["env"], capture_output=True, text=True, check=True)
    assert checked.returncode == 0
    mismatched = {**spec["binding"]["python_runtime"], "architecture": "x86_64"}
    rejected = runner.run_trusted_command(preflight.runtime_command(mismatched),
        cwd=root, env=spec["env"], capture_output=True, text=True)
    assert rejected.returncode == 1
    # 小さい合成runtimeで、stdlibのbytes・link target・型の変化を検出する。
    synthetic = root / "synthetic-runtime"
    runner._write_private(synthetic / "lib/stdlib.py", b"before")
    runner._write_private(synthetic / "lib/alternate.py", b"alternate")
    link = synthetic / "lib/current.py"
    link.symlink_to("stdlib.py")
    before, _ = fingerprint_module._runtime_tree_manifest(synthetic)
    runner._write_private(synthetic / "lib/stdlib.py", b"after")
    after, _ = fingerprint_module._runtime_tree_manifest(synthetic)
    assert before != after
    link.unlink()
    link.symlink_to("alternate.py")
    switched, _ = fingerprint_module._runtime_tree_manifest(synthetic)
    assert switched != after
    link.unlink()
    link.symlink_to("../../outside.py")
    expect_rejected(lambda: fingerprint_module._runtime_tree_manifest(synthetic))
    link.unlink()
    os.link(synthetic / "lib/stdlib.py", link)
    expect_rejected(lambda: fingerprint_module._runtime_tree_manifest(synthetic))
    link.unlink()
    os.mkfifo(link)
    expect_rejected(lambda: fingerprint_module._runtime_tree_manifest(synthetic))
    link.unlink()
    alias = root / "runtime-alias"
    alias.symlink_to(synthetic)
    expect_rejected(lambda: fingerprint_module._runtime_tree_manifest(alias))
    # runtime変更はcampaign identityも変える。旧campaign再開を許さない。
    original_runtime = fingerprint_module.compute_python_runtime_binding
    fingerprint = compute_harness_fingerprint(HERE)
    try:
        runtime = spec["binding"]["python_runtime"]
        fingerprint_module.compute_python_runtime_binding = lambda: {**runtime, "manifest_sha256": "0" * 64}
        assert compute_harness_fingerprint(HERE) != fingerprint
    finally:
        fingerprint_module.compute_python_runtime_binding = original_runtime
    print("python runtime: exit127 regression/absolute runtime/canary identity/tree bytes+links+types/campaign identity OK", flush=True)


def event_stream(command="pwd", code=0, extras=()):
    active = {"id": "cmd", "type": "command_execution", "command": command, "status": "in_progress"}
    completed = {**active, "status": "failed" if code else "completed", "exit_code": code, "aggregated_output": "private synthetic stdout"}
    return [{"type": "thread.started", "thread_id": "fixture"}, {"type": "turn.started"},
            {"type": "item.started", "item": active}, {"type": "item.completed", "item": completed}, *extras,
            {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}}]


def event_test(root):
    root.mkdir()
    scratch = root / ".benchmark-tmp"
    scratch.mkdir(mode=0o700)
    runner._write_private(scratch / "task.py", "print('fixture')\n")
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
    fixed_script = shlex.join([runner.PYTHON_EXECUTABLE, "-I", "-B", ".benchmark-tmp/task.py"])
    assert audit(fixed_script)["attempt_policy"]["status"] == "unknown"
    assert audit("/bin/zsh -lc " + shlex.quote(fixed_script))["attempt_policy"]["status"] == "unknown"
    code = "from pathlib import Path; Path('.benchmark-tmp/note.py').write_text('/old fixture data')"
    assert audit(shlex.join([runner.PYTHON_EXECUTABLE, "-I", "-B", "-c", code]))["attempt_policy"]["passed"]
    for code in ("print('/old fixture data')", "assert '/old' != '/new'", "from pathlib import Path; Path('.benchmark-tmp/x').write_text('/old')"):
        assert audit(shlex.join([runner.PYTHON_EXECUTABLE, "-I", "-B", "-c", code]))["attempt_policy"]["passed"]
    for code in ("targets=['/private/tmp/out']; open(targets[0],'w').write('x')",
                 "targets=['/private/tmp/out'];\nfor target in targets: open(target,'w')",
                 "from pathlib import Path; Path('/private/tmp/out').write_text('x')",
                 "import os; os.path.exists('/private/tmp/out')",
                 "import os as x; x.remove('/private/tmp/out')",
                 "from os import remove as rm; rm('/private/tmp/out')",
                 "import shutil; shutil.copy('.benchmark-tmp/x','/private/tmp/out')",
                 "import shutil; shutil.copy('README.md','/private/tmp/out')",
                 "import shutil; shutil.copy(src='README.md',dst='/private/tmp/out')",
                 "import shutil; shutil.copy(src='/private/tmp/out',dst='.benchmark-tmp/x')",
                 "import shutil as s; s.copy(src='.benchmark-tmp/x',dst='/private/tmp/out')",
                 "from pathlib import Path; Path('.benchmark-tmp/link').symlink_to('/private/tmp')",
                 "from pathlib import Path as P; P('.benchmark-tmp/link').symlink_to(target='/private/tmp')",
                 "import os; os.symlink(src='.benchmark-tmp/x',dst='/private/tmp/link')",
                 "import os; os.rename(src='.benchmark-tmp/x',dst='/private/tmp/out')"):
        assert audit(shlex.join([runner.PYTHON_EXECUTABLE, "-I", "-B", "-c", code]))["attempt_policy"]["status"] == "fail"
    for code in ("open(dynamic_path,'w')", "eval('1+1')", "exec('pass')", "compile('x=1','x','exec')", "__import__('os')",
                 "targets=['/private/tmp/out']; targets=['.benchmark-tmp/safe']; open(targets[0],'w')",
                 "f=open; f('/private/tmp/out','w')",
                 "import os as x; x.system('touch /private/tmp/out')",
                 "import socket as s; s.create_connection(('127.0.0.1',80))",
                 "import builtins as b; b.eval('1+1')",
                 "import mystery as m; m.unknown('/private/tmp/out')",
                 "import os as x; x=object(); x.getcwd()",
                 "import mystery as x; import os as x; x.getcwd()"):
        assert audit(shlex.join([runner.PYTHON_EXECUTABLE, "-I", "-B", "-c", code]))["attempt_policy"]["status"] == "unknown"
    for code in ("open('/private/tmp/out', 'w')", "open('../outside', 'w')",
                 "import os; os.environ.pop('P5_RUN_TOKEN')"):
        command = shlex.join([runner.PYTHON_EXECUTABLE, "-I", "-B", "-c", code])
        assert audit(command)["attempt_policy"]["status"] == "fail", command
    for command in (fixed_script + " <<EOF", fixed_script + " >/private/tmp/out",
                    shlex.join([runner.PYTHON_EXECUTABLE, "-I", "-B", "../outside.py"])):
        assert not audit(command)["attempt_policy"]["passed"], command
    runner._write_private(scratch / "task.py", "open('/private/tmp/out','w')\n", 0o600)
    assert audit(fixed_script)["attempt_policy"]["status"] == "unknown"
    (scratch / "task.py").unlink()
    assert audit(fixed_script)["attempt_policy"]["status"] == "unknown"
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
    print("events: inline path-sink dataflow/relative script TOCTOU unknown/external/heredoc fail-closed OK", flush=True)


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
            assert runner.ENV_CANARY_NAME.encode() not in runner.run_trusted_command(
                ["git", "ls-files", "-z"], cwd=prepared, capture_output=True, check=True,
                env=runner.limited_env(prepared)).stdout
            status = runner.run_trusted_command(["git", "status", "--porcelain=v1"], cwd=prepared,
                capture_output=True, text=True, check=True, env=runner.limited_env(prepared)).stdout
            assert status == ""
            accepted, _, _ = runner.accepted_snapshot(prepared)
            assert not (accepted / runner.ENV_CANARY_NAME).exists()
            accepted_status = runner.run_trusted_command(["git", "status", "--porcelain=v1"], cwd=accepted,
                capture_output=True, text=True, check=True, env=runner.limited_env(accepted)).stdout
            assert accepted_status == ""
    finally:
        runner.BASE, runner.HERE, runner.B_INDEX, runner.safe_read = original_base, original_here, original_b_index, original_read
    print("prepare: real A fixture/B contract source swapped after read; copied verified bytes only OK", flush=True)


def preflight_test(root):
    root.mkdir()
    runner.install_env_canary(root)
    runner._write_private(root / "AGENTS.md", "fixture")
    for name in c1_task()["input"] + c1_task()["fixture"]:
        runner._write_private(root / name, "fixed fixture")
    spec = runner.execution_spec(root, c1_task(), runner.CLI_VERSION, "fixture-fingerprint")
    original = preflight.run_case
    seen = []
    def fake_case(name, passed_spec, command, expected):
        assert passed_spec is spec
        assert command[0] == runner.PYTHON_EXECUTABLE
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


@contextlib.contextmanager
def forbid_after_outcome(roots, modules=(runner,)):
    """outcome観測後はroot操作と監査・再bindingを禁止し、root外診断だけ許す。"""
    locked, originals, violations = [False], [], []
    def activate():
        locked[0] = True
    def root_path(path):
        candidate = Path(path)
        return any(candidate == root or root in candidate.parents for root in roots)
    def replace(owner, name, value):
        originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)
    def forbidden(name, original, path_only=False):
        def call(*args, **kwargs):
            if locked[0] and (not path_only or root_path(args[0])):
                violations.append(name)
                raise AssertionError("失敗outcome後に禁止helperを呼んだ: " + name)
            return original(*args, **kwargs)
        return call
    for module in modules:
        for name in ("safe_events", "safe_read", "sha", "tree_manifest", "accepted_snapshot", "host_guard",
                     "execution_spec", "canonical_execution_spec", "derive_canonical_binding", "permission_policy"):
            replace(module, name, forbidden(name, getattr(module, name)))
        for name in ("_open_directory", "_write_private", "save"):
            replace(module, name, forbidden(name, getattr(module, name), path_only=True))
    for name in ("exists", "is_file", "is_dir", "stat", "lstat", "read_text", "read_bytes", "unlink", "open", "resolve"):
        replace(Path, name, forbidden("Path." + name, getattr(Path, name), path_only=name != "unlink"))
    try:
        yield activate
    finally:
        for owner, name, original in reversed(originals):
            setattr(owner, name, original)
        # production側が例外を捕捉しても、禁止アクセスの試行自体を見逃さない。
        assert not violations, "失敗後の禁止helper呼出し: " + repr(violations)


def preflight_timeout_test(root):
    root.mkdir()
    originals = preflight.subprocess.Popen, runner.os.kill, runner.os.killpg
    signals = []
    def forbidden_signal(*args):
        signals.append(args)
        raise AssertionError("preflightで自動killしました")
    runner.os.kill, runner.os.killpg = forbidden_signal, forbidden_signal
    try:
        for mode in ("timeout", "signal", "nonzero", "spawn_error"):
            target = root / mode / "run-01"
            target.mkdir(parents=True)
            runner._write_private(target / "AGENTS.md", "fixture")
            runner.install_env_canary(target)
            spec = runner.execution_spec(target, runner.c6_task(), runner.CLI_VERSION, "fixture-fingerprint")
            processes = []
            with forbid_after_outcome([target], modules=(runner, preflight.runner)) as activate:
                class MockCanary:
                    pid = 987654321
                    returncode = 1
                    def __init__(self, *_args, **_kwargs):
                        processes.append(self)
                        self.stdin, self.stdout, self.stderr = None, io.StringIO(), io.StringIO()
                        if mode == "spawn_error":
                            activate()
                            raise OSError("synthetic spawn failure")
                    def communicate(self, **_kwargs):
                        activate()
                        if mode == "timeout":
                            raise subprocess.TimeoutExpired("canary", 20, output=b"partial", stderr=b"diagnostic")
                        if mode == "signal":
                            raise preflight.runner.RunSignal(15)
                        return "", "sandbox initialization failed"
                    def kill(self):
                        raise AssertionError("preflight Popen.kill禁止")
                    def terminate(self):
                        raise AssertionError("preflight Popen.terminate禁止")
                preflight.subprocess.Popen = MockCanary
                try:
                    preflight.check(spec)
                except SystemExit as error:
                    assert error.code == 1
                else:
                    raise AssertionError("preflight失敗後にreport/cleanupへ進んだ")
            assert len(processes) == 1 and not signals
            assert list((target / ".benchmark-tmp").glob("outside-link-*")), "canaryをunlinkした"
            assert list(target.parent.glob(".p5-private-*")), "private sentinelをunlinkした"
            assert not (target / ".benchmark-isolation.json").exists()
            diagnostic = target.parent / ".evidence" / target.name / "preflight-interruption.json"
            assert diagnostic.stat().st_mode & 0o777 == 0o600
            detail = runner.load(diagnostic)
            assert not detail["root_access_after_failure"] and detail["phase"] == "preflight"
        # 正常なdenyのnonzeroはinfra失敗と区別する。
        class Denied:
            pid = 123456789
            returncode = 1
            stdin = stdout = stderr = None
            def communicate(self, **_kwargs):
                return "", "Operation not permitted"
        preflight.subprocess.Popen = lambda *_args, **_kwargs: Denied()
        case = preflight.run_case("normal-denial", spec, ["true"], "deny")
        assert case["outcome"] == "sandbox_denied" and case["exit_code"] == 1
        Denied.returncode = -15
        try:
            preflight.run_case("signalled-denial", spec, ["true"], "deny")
        except SystemExit as error:
            assert error.code == 1
        else:
            raise AssertionError("signal終了を正常denyと誤認した")
    finally:
        preflight.subprocess.Popen, runner.os.kill, runner.os.killpg = originals
    print("preflight: timeout/signal/nonzero/spawn immediate root-free abort/no cleanup/normal denial OK (mock)", flush=True)


def fake_preflight_report(spec):
    return {"schema": 3, "passed": True, "binding": spec["binding"], "cli_version": runner.CLI_VERSION,
            "binding_comparison": "entire_canonical_binding_equal_before_model",
            "tool_environment_scope": "auxiliary_env_i_probe_not_actual_exec_tool",
            "sandbox_initialized": True, "canaries_removed": True,
            "postconditions": {name: True for name in ("canary_writes_observed", "outside_writes_absent",
                "private_sentinel_unchanged", "task_file_contents_unchanged", "binding_unchanged", "python_runtime_unchanged")},
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


def run_synthetic(args):
    """正式path契約を保ち、合成caseごとのprivate WORKにだけ差し替える。"""
    campaign = Path(args.campaign)
    path = campaign / "campaign-binding.json"
    if not path.exists():
        value = {"schema": 1, "fingerprint": args.fingerprint,
                 "codex_executable": runner.compute_codex_executable_binding(runner.CODEX_EXECUTABLE),
                 "python_runtime": fingerprint_module.compute_python_runtime_binding(),
                 "driver_executable": fingerprint_module.compute_driver_executable_binding(),
                 "driver_config": fingerprint_module.compute_driver_config_binding(),
                 "private_directories": runner.private_directory_identity(campaign)}
        value["binding_sha256"] = runner.canonical_digest(value)
        runner.save(path, value)
    args.expected_binding_file = path
    with patch.object(runner, "WORK", campaign.parent):
        return runner.run(args)


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
                run_synthetic(args)
            except SystemExit as error:
                assert expected_exit is not None and error.code == expected_exit
            else:
                assert expected_exit is None
        path = campaign / args.run_id / ".benchmark-result.json"
        if expected_exit is not None:
            assert not path.exists()
            return args, None, path
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
        expect_rejected(lambda: run_synthetic(args))
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
        assert c6["validation"]["command"][0] == runner.PYTHON_EXECUTABLE
        assert c6["validation"]["manifest_before_sha256"] == c6["validation"]["manifest_after_sha256"]
        assert c6["snapshot_evidence"]["accepted_sha256"] == c6["validation"]["manifest_after_sha256"]
        # 非scratchのbookkeeping名もvalidatorの書換えとして必ず拒否する。
        original_execute = runner.execute_command
        def mutate_snapshot(_command, validation_root, *_args, **_kwargs):
            runner._write_private(validation_root / ".benchmark-answer.txt", "unexpected")
            return 0, "OK", ""
        runner.execute_command = mutate_snapshot
        try:
            invalid = runner.validate(c1_task(), campaign / ".accepted/run-01", harness_fingerprint="fixture-fingerprint",
                                      expected_runtime_binding=runner.compute_python_runtime_binding())
            assert invalid["exit_code"] == "validator_changed_snapshot" and not invalid["manifest_unchanged"]
        finally:
            runner.execute_command = original_execute
        (root / "mode").write_text("version_mismatch")
        mismatch_args = SimpleNamespace(task="C1", condition="A", repeat=1, run_id="run-24",
                                        campaign=str(campaign), fingerprint=fingerprint)
        with patch.object(runner, "prepare", side_effect=AssertionError("CLI版不一致後にfixtureを作成")), \
                patch.object(runner, "execute_command", side_effect=AssertionError("CLI版不一致後にmodel起動")):
            expect_rejected(lambda: run_synthetic(mismatch_args))
        assert not (campaign / "run-24").exists()
        for mode in ("env_missing", "env_leak"):
            _, invalid_environment, _ = invoke(mode=mode)
            assert not invalid_environment["isolation_gate"]["passed"] and not invalid_environment["isolation_gate"]["env_canary_pass"]
            assert invalid_environment["validation"]["exit_code"] == "not_run"
            assert invalid_environment["validation"]["reason"] == "isolation_gate_not_pass"
            assert "unsafe_or_unstable_snapshot" not in invalid_environment["scope_violations"]
        def residual_found(token):
            return {**clean_process_evidence(token), "status": "fail", "passed": False, "detected_count": 1, "kill_count": 0}
        runner.scan_residual_processes = residual_found
        _, _, detached_path = invoke(expected_exit=1)
        assert runner.load(campaign / ".evidence" / detached_path.parent.name / "model-interruption.json")["reason"] == "residual_detected_or_scan_unconfirmed"
        runner.scan_residual_processes = clean_process_evidence
        _, _, failed_path = invoke(mode="fail", expected_exit=1)
        assert runner.load(campaign / ".evidence" / failed_path.parent.name / "model-interruption.json")["exit_status"] == 1
        original_snapshot, original_validate = runner.accepted_snapshot, runner.validate
        def forbidden_snapshot(*_args, **_kwargs):
            raise AssertionError("timeout/signal後にsnapshot/validatorを実行しました")
        runner.accepted_snapshot = runner.validate = forbidden_snapshot
        try:
            for incomplete_code in ("timeout", "signal:15"):
                def interrupted_execute(_command, _root, env, *_args, **_kwargs):
                    # 完全な成功eventがあっても、実行完了未確認なら受入禁止。
                    events = event_stream(runner.ENV_CANARY_COMMAND)
                    events[3]["item"]["aggregated_output"] = synthetic_canary_from_process_env(env, _root)
                    return incomplete_code, "\n".join(json.dumps(event) for event in events), ""
                runner.execute_command = interrupted_execute
                _, _, timed_path = invoke(expected_exit=1)
                evidence = runner.load(campaign / ".evidence" / timed_path.parent.name / "model-interruption.json")
                assert evidence["exit_status"] == incomplete_code and not evidence["root_access_after_failure"]
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
    print("integration: 4 gates/exact replay path/fingerprint+hash tamper/non-mutating result/C6 scratch validator/full manifest/timeout/binding/version mismatch block OK", flush=True)


def immediate_abort_test(root):
    root.mkdir()
    fake = root / "codex"
    fake.write_text(FAKE)
    fake.chmod(0o700)
    (root / "mode").write_text("normal")
    originals = runner.CODEX_EXECUTABLE, runner.per_run_preflight, runner.execute_command, runner.scan_residual_processes
    runner.CODEX_EXECUTABLE, runner.per_run_preflight = str(fake), fake_preflight_report
    fingerprint = compute_harness_fingerprint(HERE)
    try:
        for phase in ("model", "validation"):
            for outcome in ("timeout", "signal:15", 1, "residual", "scan_error", "scan_exception"):
                campaign = root / (phase + "-" + str(outcome).replace(":", "-")) / ("p5-" + fingerprint[:16])
                runner.private_directory_identity(campaign, create=True)
                model_root, accepted_root = campaign / "run-01", campaign / ".accepted/run-01"
                args = SimpleNamespace(task="C1", condition="A", repeat=1, run_id="run-01",
                                       campaign=str(campaign), fingerprint=fingerprint)
                scan_count = [0]
                with forbid_after_outcome([model_root, accepted_root]) as activate:
                    def execute(command, execution_root, env, *_args, **_kwargs):
                        current_phase = "validation" if execution_root.parent.name == ".accepted" else "model"
                        if current_phase == phase and outcome not in {"residual", "scan_error", "scan_exception"}:
                            activate()
                            return outcome, "untrusted partial raw", "partial stderr"
                        if current_phase == "model":
                            runner._write_private(execution_root / ".benchmark-answer.txt", "目的 検証 次")
                            events = event_stream(runner.ENV_CANARY_COMMAND)
                            events[3]["item"]["aggregated_output"] = synthetic_canary_from_process_env(env, execution_root)
                            return 0, "\n".join(json.dumps(event) for event in events), ""
                        return 0, "OK", ""
                    def scan(token):
                        scan_count[0] += 1
                        current_phase = "model" if scan_count[0] == 1 else "validation"
                        evidence = clean_process_evidence(token)
                        if current_phase == phase and outcome in {"residual", "scan_error", "scan_exception"}:
                            activate()
                            if outcome == "scan_exception":
                                raise OSError("synthetic scan failure")
                            evidence.update(status="fail", passed=False)
                            if outcome == "residual":
                                evidence.update(detected_count=1, remaining_count=1, clean_after_scan=False)
                            else:
                                evidence.update(scan_pass=False, clean_after_scan=False)
                        return evidence
                    runner.execute_command, runner.scan_residual_processes = execute, scan
                    with contextlib.redirect_stdout(io.StringIO()):
                        try:
                            run_synthetic(args)
                        except SystemExit as error:
                            assert error.code == 1
                        else:
                            raise AssertionError("root停止条件から正常returnした")
                assert not (model_root / ".benchmark-result.json").exists()
                if phase == "model":
                    assert not accepted_root.exists() and not (model_root / ".benchmark-events.json").exists()
                diagnostic = campaign / ".evidence/run-01" / (phase + "-interruption.json")
                assert diagnostic.stat().st_mode & 0o777 == 0o600
                data = runner.load(diagnostic)
                assert data["phase"] == phase and not data["root_access_after_failure"]
                assert not data["automatic_termination"]
    finally:
        runner.CODEX_EXECUTABLE, runner.per_run_preflight, runner.execute_command, runner.scan_residual_processes = originals
    print("run abort: model+validator timeout/signal/nonzero/residual/scan-error; no root helper/audit/result after outcome OK (mock)", flush=True)


def campaign_destination_test(root):
    root.mkdir()
    fingerprint = "a" * 64
    work = root / "formal"
    campaign = work / ("p5-" + fingerprint[:16])
    runner.private_directory_identity(campaign, create=True)
    alt = root / "alternate" / campaign.name
    directories = runner.private_directory_identity(alt, create=True)
    value = {"schema": 1, "fingerprint": fingerprint, "codex_executable": {},
             "python_runtime": {}, "driver_executable": fingerprint_module.compute_driver_executable_binding(),
             "driver_config": fingerprint_module.compute_driver_config_binding(),
             "private_directories": directories}
    value["binding_sha256"] = runner.canonical_digest(value)
    runner.save(alt / "campaign-binding.json", value)
    assert runner.load_campaign_binding(alt / "campaign-binding.json", alt, fingerprint)["record"] == value
    def forbidden(*_args, **_kwargs):
        raise AssertionError("不正campaignからCLI/fixture/modelを開始した")
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(runner, "WORK", work))
        stack.enter_context(patch.object(runner, "compute_harness_fingerprint", lambda *_args, **_kwargs: fingerprint))
        stack.enter_context(patch.object(runner, "compute_python_runtime_binding", lambda: {}))
        stack.enter_context(patch.object(runner, "compute_codex_executable_binding", lambda *_args: {}))
        for name in ("prepare", "run_trusted_command", "execute_command"):
            stack.enter_context(patch.object(runner, name, forbidden))
        for destination, binding in (
            (runner.account_home() / "Library/Caches/alternate" / campaign.name, alt / "campaign-binding.json"),
            (campaign.name, Path(campaign.name) / "campaign-binding.json"),
            (alt, alt / "campaign-binding.json"),
            (campaign, alt / "campaign-binding.json"),
            (str(work) + "/../formal/" + campaign.name, campaign / "campaign-binding.json"),
            (campaign, None),
        ):
            args = SimpleNamespace(campaign=destination, fingerprint=fingerprint, run_id="run-01", expected_binding_file=binding)
            expect_rejected(lambda: runner._run(args))
        # 正しい文字列でも、正式directory componentのsymlinkを許可しない。
        alias_work = root / "formal-alias"
        alias_work.symlink_to(work)
        with patch.object(runner, "WORK", alias_work):
            args = SimpleNamespace(campaign=alias_work / campaign.name, fingerprint=fingerprint, run_id="run-01",
                                   expected_binding_file=alias_work / campaign.name / "campaign-binding.json")
            expect_rejected(lambda: runner._run(args))
    assert not (campaign / "run-01").exists() and not (alt / "run-01").exists()
    print("campaign destination: non-temp alternate/relative/self-signed binding/alias/binding path reject before CLI+fixture OK", flush=True)


def directory_completion_abort_test(root):
    root.mkdir()
    fake = root / "codex"
    runner._write_private(fake, FAKE, 0o700)
    original_identity = runner.private_directory_identity
    with patch.object(runner, "CODEX_EXECUTABLE", str(fake)), patch.object(runner, "per_run_preflight", fake_preflight_report), \
            patch.object(runner, "scan_residual_processes", clean_process_evidence):
        fingerprint = compute_harness_fingerprint(HERE)
        for phase in ("model", "validation"):
            for replaced in ("root", "parent", "campaign"):
                campaign = root / (phase + "-" + replaced) / ("p5-" + fingerprint[:16])
                original_identity(campaign, create=True)
                model, accepted = campaign / "run-01", campaign / ".accepted/run-01"
                args = SimpleNamespace(task="C1", condition="A", repeat=1, run_id="run-01", campaign=str(campaign), fingerprint=fingerprint)
                state, identities, visited = {"done": False}, {}, []
                target = model if phase == "model" else accepted
                with forbid_after_outcome([model, accepted]) as activate:
                    def identity(path, *positional, **kwargs):
                        path = Path(path)
                        if not state["done"]:
                            result = original_identity(path, *positional, **kwargs)
                            identities[path] = json.loads(json.dumps(result))
                            return result
                        visited.append(path)
                        result = json.loads(json.dumps(identities[path]))
                        if (replaced == "campaign" and path == campaign) or (replaced != "campaign" and path == target):
                            result["root" if replaced == "campaign" else replaced]["inode"] += 1
                        return result
                    def execute(_command, execution_root, env, *_args, **_kwargs):
                        current_phase = "validation" if execution_root.parent.name == ".accepted" else "model"
                        if current_phase == phase:
                            state["done"] = True
                            activate()
                            return 0, "unadopted normal process output", ""
                        runner._write_private(execution_root / ".benchmark-answer.txt", "目的 検証 次")
                        events = event_stream(runner.ENV_CANARY_COMMAND)
                        events[3]["item"]["aggregated_output"] = synthetic_canary_from_process_env(env, execution_root)
                        return 0, "\n".join(json.dumps(event) for event in events), ""
                    with patch.object(runner, "private_directory_identity", identity), patch.object(runner, "execute_command", execute):
                        try:
                            with contextlib.redirect_stdout(io.StringIO()):
                                run_synthetic(args)
                        except SystemExit as error:
                            assert error.code == 1
                        else:
                            raise AssertionError("正常終了後のdirectory差替えを採用した")
                assert target in visited and (replaced != "campaign" or campaign in visited)
                assert not (model / ".benchmark-result.json").exists()
                if phase == "model":
                    assert not accepted.exists()
                    assert not (campaign / ".evidence/run-01/events.raw.jsonl").exists()
                    assert not (model / ".benchmark-events.json").exists()
                diagnostic = campaign / ".evidence/run-01" / (phase + "-interruption.json")
                data = runner.load(diagnostic)
                assert data["reason"] in {"private_directory_changed", "private_directory_recalculation_error"}
                assert not data["root_access_after_failure"] and diagnostic.stat().st_mode & 0o777 == 0o600
    print("directory completion: model+validation root/parent/campaign inode swap abort before root/raw/event/result OK (mock)", flush=True)


def model_rebound_abort_test(root):
    root.mkdir()
    fake = root / "codex"
    runner._write_private(fake, FAKE, 0o700)
    original_derive = runner.derive_canonical_binding
    with patch.object(runner, "CODEX_EXECUTABLE", str(fake)), patch.object(runner, "per_run_preflight", fake_preflight_report), \
            patch.object(runner, "scan_residual_processes", clean_process_evidence):
        fingerprint = compute_harness_fingerprint(HERE)
        for field in ("root_inode", "profile_sha256", "tool_environment"):
            campaign = root / field / ("p5-" + fingerprint[:16])
            runner.private_directory_identity(campaign, create=True)
            model = campaign / "run-01"
            args = SimpleNamespace(task="C1", condition="A", repeat=1, run_id="run-01", campaign=str(campaign), fingerprint=fingerprint)
            with forbid_after_outcome([model]) as activate:
                def changed_binding(*positional, **kwargs):
                    observed = original_derive(*positional, **kwargs)
                    if field == "root_inode":
                        observed[field] += 1
                    elif field == "profile_sha256":
                        observed[field] = "0" * 64
                    else:
                        observed[field] = {**observed[field], "sha256": "0" * 64}
                    activate()
                    return observed
                with patch.object(runner, "derive_canonical_binding", changed_binding), \
                        patch.object(runner, "execute_command", lambda *_args, **_kwargs: (0, "must not save raw", "")):
                    try:
                        with contextlib.redirect_stdout(io.StringIO()):
                            run_synthetic(args)
                    except SystemExit as error:
                        assert error.code == 1
                    else:
                        raise AssertionError("再導出binding不一致から正常returnした")
            assert not (campaign / ".evidence/run-01/events.raw.jsonl").exists()
            assert not (model / ".benchmark-events.json").exists()
            assert not (model / ".benchmark-result.json").exists()
            assert not (campaign / ".accepted/run-01").exists()
            diagnostic = campaign / ".evidence/run-01/model-interruption.json"
            record = runner.load(diagnostic)
            assert record["reason"] == "model_binding_changed" and not record["root_access_after_failure"]
            assert diagnostic.stat().st_mode & 0o777 == 0o600
    print("model rebound: identity/profile/tool env mismatch abort before raw/event/result/root helper OK (mock)", flush=True)


def campaign_fingerprint_guard_test():
    originals = runner.compute_harness_fingerprint, runner.prepare, runner.run_trusted_command
    def forbidden(*_args, **_kwargs):
        raise AssertionError("fingerprint不一致後にprepare/CLIを起動した")
    runner.prepare = runner.run_trusted_command = forbidden
    try:
        for mode in ("mismatch", "exception"):
            def fingerprint(_here, **_kwargs):
                if mode == "exception":
                    raise OSError("synthetic runtime fingerprint failure")
                return "0" * 64
            runner.compute_harness_fingerprint = fingerprint
            try:
                runner._run(SimpleNamespace(fingerprint="1" * 64))
            except SystemExit:
                pass
            else:
                raise AssertionError("旧campaign fingerprintを許可した")
    finally:
        runner.compute_harness_fingerprint, runner.prepare, runner.run_trusted_command = originals
    print("campaign fingerprint: mismatch/recalculation exception stop before root/prepare/CLI OK", flush=True)


def runtime_abort_test(root):
    root.mkdir()
    fake = root / "codex"
    runner._write_private(fake, FAKE, 0o700)
    runtime = runner.compute_python_runtime_binding()
    fingerprint = compute_harness_fingerprint(HERE, codex_executable_binding=runner.compute_codex_executable_binding(fake))
    names = ("CODEX_EXECUTABLE", "per_run_preflight", "execute_command", "scan_residual_processes",
             "compute_python_runtime_binding", "execution_spec")
    originals = {name: getattr(runner, name) for name in names}
    runner.CODEX_EXECUTABLE, runner.per_run_preflight = str(fake), fake_preflight_report
    runner.scan_residual_processes = clean_process_evidence
    try:
        for stage in ("initial_spec", "model_before", "model_after", "validation_before", "validation_launch", "validation_after"):
            for outcome in ("mismatch", "exception"):
                campaign = root / (stage + "-" + outcome) / ("p5-" + fingerprint[:16])
                runner.private_directory_identity(campaign, create=True)
                model, accepted = campaign / "run-01", campaign / ".accepted/run-01"
                args = SimpleNamespace(task="C1", condition="A", repeat=1, run_id="run-01",
                                       campaign=str(campaign), fingerprint=fingerprint)
                phase = {"spec_started": False, "model_done": False, "validation_started": False, "validation_done": False,
                         "runtime_calls": 0, "validation_runtime_calls": 0}
                def marking_spec(*args, **kwargs):
                    phase["spec_started"] = True
                    if kwargs.get("phase") == "validation":
                        phase["validation_started"] = True
                    return originals["execution_spec"](*args, **kwargs)
                runner.execution_spec = marking_spec
                with forbid_after_outcome([model, accepted]) as activate:
                    def changing_runtime():
                        phase["runtime_calls"] += 1
                        if phase["validation_started"]:
                            phase["validation_runtime_calls"] += 1
                        fail = ((stage == "initial_spec" and phase["spec_started"])
                                or (stage == "model_before" and phase["runtime_calls"] >= 3)
                                or (stage == "model_after" and phase["model_done"])
                                or (stage == "validation_before" and phase["validation_started"])
                                or (stage == "validation_launch" and phase["validation_runtime_calls"] >= 2)
                                or (stage == "validation_after" and phase["validation_done"]))
                        if fail:
                            activate()
                            if outcome == "exception":
                                raise OSError("synthetic runtime read failure")
                            return {**runtime, "manifest_sha256": "0" * 64}
                        return runtime
                    def execute(_command, execution_root, env, *_args, **_kwargs):
                        if execution_root.parent.name == ".accepted":
                            phase["validation_done"] = True
                            return 0, "OK", ""
                        runner._write_private(execution_root / ".benchmark-answer.txt", "目的 検証 次")
                        events = event_stream(runner.ENV_CANARY_COMMAND)
                        events[3]["item"]["aggregated_output"] = synthetic_canary_from_process_env(env, execution_root)
                        phase["model_done"] = True
                        return 0, "\n".join(json.dumps(event) for event in events), ""
                    runner.compute_python_runtime_binding, runner.execute_command = changing_runtime, execute
                    with contextlib.redirect_stdout(io.StringIO()):
                        try:
                            run_synthetic(args)
                        except SystemExit as error:
                            assert error.code == 1
                        else:
                            raise AssertionError("runtime不一致/例外から正常returnした")
                phase_name = "model" if stage in {"initial_spec", "model_before", "model_after"} else "validation"
                diagnostic = campaign / ".evidence/run-01" / (phase_name + "-interruption.json")
                assert diagnostic.stat().st_mode & 0o777 == 0o600
                assert not runner.load(diagnostic)["root_access_after_failure"]
                assert not (model / ".benchmark-result.json").exists()
                if stage in {"initial_spec", "model_before", "model_after"}:
                    assert not accepted.exists()
                    assert not (campaign / ".evidence/run-01/events.raw.jsonl").exists()
                    assert not (model / ".benchmark-events.json").exists()
                if stage in {"validation_before", "validation_launch"}:
                    assert not phase["validation_done"]
                if stage in {"initial_spec", "model_before"}:
                    assert not phase["model_done"]
    finally:
        for name, original in originals.items():
            setattr(runner, name, original)
    print("runtime abort: fingerprint-to-spec/model-before+after/validation-spec+before+after mismatch+exception; root/result/raw untouched OK (mock)", flush=True)


def preflight_runtime_abort_test(root):
    root.mkdir()
    current = preflight.runner
    runtime = current.compute_python_runtime_binding()
    originals = current.compute_python_runtime_binding, preflight.run_case
    try:
        for stage in ("post_check", "rebound"):
            for outcome in ("mismatch", "exception"):
                target = root / (stage + "-" + outcome) / "run-01"
                current._write_private(target / "AGENTS.md", "fixture")
                current.install_env_canary(target)
                spec = current.execution_spec(target, current.c6_task(), current.CLI_VERSION, "fixture-fingerprint")
                calls, cases = [0], []
                with forbid_after_outcome([target], modules=(runner, current)) as activate:
                    def changing_runtime():
                        calls[0] += 1
                        if calls[0] >= (2 if stage == "post_check" else 3):
                            activate()
                            if outcome == "exception":
                                raise OSError("synthetic preflight runtime failure")
                            return {**runtime, "manifest_sha256": "0" * 64}
                        return runtime
                    def fake_case(name, _spec, _command, expected):
                        cases.append(name)
                        return {"name": name, "expected": expected,
                                "outcome": "allowed" if expected == "allow" else "sandbox_denied"}
                    current.compute_python_runtime_binding, preflight.run_case = changing_runtime, fake_case
                    try:
                        preflight.check(spec)
                    except SystemExit as error:
                        assert error.code == 1
                    else:
                        raise AssertionError("preflight runtime failureからpostcondition/cleanupへ進んだ")
                current.compute_python_runtime_binding = originals[0]
                assert cases[-1] == "network_connect"
                assert list(target.parent.glob(".p5-private-*")), "失敗後にsentinelをcleanupした"
                assert list((target / ".benchmark-tmp").glob("outside-link-*")), "失敗後にcanaryをcleanupした"
                diagnostic = target.parent / ".evidence/run-01/preflight-interruption.json"
                assert diagnostic.stat().st_mode & 0o777 == 0o600
                assert not current.load(diagnostic)["root_access_after_failure"]
                assert not (target.parent / ".evidence/run-01/preflight.raw.json").exists()
    finally:
        current.compute_python_runtime_binding, preflight.run_case = originals
    print("preflight runtime abort: post-check/rebound mismatch+exception; no root access/cleanup OK (mock)", flush=True)


def synthetic_tool_env(required, root):
    return {**required, "CODEX_CI": "1", "CODEX_PERMISSION_PROFILE": "p5_fixture",
            "CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1",
            "CODEX_SESSION_ID": "abcdefab-cdef-7abc-8def-abcdefabcdef",
            "CODEX_THREAD_ID": "abcdefab-cdef-7abc-8def-abcdefabcdee", "CODEX_VERSION": "0.160.0",
            "COLORTERM": "", "GH_PAGER": "cat", "GIT_PAGER": "cat", "LC_CTYPE": "C.UTF-8",
            "LOGNAME": pwd.getpwuid(os.getuid()).pw_name, "NO_COLOR": "1", "OLDPWD": str(root),
            "PAGER": "cat", "PWD": str(root), "SHLVL": "0", "TERM": "dumb", "_": runner.PYTHON_EXECUTABLE}


def synthetic_canary_output(environment, root):
    result = subprocess.run(shlex.split(runner.ENV_CANARY_COMMAND), cwd=root, env=environment,
                            text=True, capture_output=True, check=True)
    return result.stdout.strip()


def synthetic_canary_from_process_env(environment, root):
    required = {key: value for key, value in environment.items() if key in runner.REQUIRED_TOOL_ENV_KEYS}
    return synthetic_canary_output(synthetic_tool_env(required, root), root)


def environment_canary_test(root):
    root.mkdir()
    runner.install_env_canary(root)
    expected = runner.limited_env(root, "fixture-fingerprint")
    injected = synthetic_tool_env(expected, root)
    command = runner.ENV_CANARY_COMMAND
    def audit(canary_command=command, output=None, prefix=()):
        events = event_stream(canary_command)
        events[3]["item"]["aggregated_output"] = synthetic_canary_output(injected, root) if output is None else output
        if prefix:
            events[2:2] = prefix
        return runner.safe_events("\n".join(json.dumps(event) for event in events), expected_cwd=root, expected_env=expected)
    assert audit()["env_canary_evidence"]["passed"]
    assert audit("/bin/zsh -lc " + shlex.quote(command))["env_canary_evidence"]["passed"]
    assert not audit(command + "; true")["env_canary_evidence"]["passed"]
    assert not audit("pwd")["env_canary_evidence"]["passed"]
    assert not audit(output="{}")["env_canary_evidence"]["passed"]
    for changed in ({**injected, "CODEX_HOME": "/synthetic/auth"},
                    {key: value for key, value in injected.items() if key != "P5_RUN_TOKEN"},
                    {**injected, "P5_RUN_TOKEN": "different"},
                    {key: value for key, value in injected.items() if key != "CODEX_CI"},
                    *({**injected, name: value} for name, value in (
                        ("PWD", "/private/tmp/escape"), ("OLDPWD", "/private/tmp/escape"),
                        ("CODEX_PERMISSION_PROFILE", "danger"), ("CODEX_SANDBOX", "none"),
                        ("CODEX_SANDBOX_NETWORK_DISABLED", "0"), ("CODEX_VERSION", "0.155.1"),
                        ("CODEX_SESSION_ID", "invalid"), ("CODEX_THREAD_ID", "invalid"),
                        ("LOGNAME", "other"), ("TERM", "xterm"),
                        ("_", "/private/tmp/python3.12")))):
        assert not audit(output=synthetic_canary_output(changed, root))["env_canary_evidence"]["passed"]
    assert not audit(output=json.dumps(injected))["env_canary_evidence"]["passed"]
    patch = {"type": "item.completed", "item": {"id": "patch", "type": "file_change", "status": "completed", "changes": []}}
    assert not audit(prefix=[patch])["env_canary_evidence"]["passed"]
    prior = event_stream("pwd")[2:4]
    for event in prior:
        event["item"]["id"] = "prior"
    assert not audit(prefix=prior)["env_canary_evidence"]["passed"]
    evidence = json.dumps(audit())
    assert expected["P5_RUN_TOKEN"] not in evidence and expected["HOME"] not in evidence
    sanitized = synthetic_canary_output(injected, root)
    assert expected["P5_RUN_TOKEN"] not in sanitized and injected["CODEX_SESSION_ID"] not in sanitized
    assert injected["CODEX_THREAD_ID"] not in sanitized and injected["PWD"] not in sanitized
    assert set(json.loads(sanitized)["runtime_checks"]) == runner.RUNTIME_TOOL_ENV_KEYS
    print("env canary: allowed runtime injection/unknown/missing/tamper/unsafe cwd+profile/redacted values OK", flush=True)


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
            self.timeout_seen = _kwargs.get("timeout")
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
        if mode == "late_popen":
            clock[0] += 7
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
        original_monotonic = runner.time.monotonic
        clock = [1000.0]
        mode = "late_popen"
        try:
            runner.time.monotonic = lambda: clock[0]
            target = root / "late-popen/run-01"
            target.mkdir(parents=True)
            code, _, _ = runner.execute_command(["mock"], target, {}, 100,
                                                 deadline_monotonic=1100.0, reserve_seconds=10)
            assert code == 0 and created[-1].timeout_seen == 83.0
            count = len(created)
            try:
                runner.execute_command(["mock"], target, {}, 100,
                                       deadline_monotonic=1009.0, reserve_seconds=10)
            except RuntimeError:
                assert len(created) == count
            else:
                raise AssertionError("期限切れでprocessを起動した")
        finally:
            runner.time.monotonic = original_monotonic
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
            try:
                runner.validate(c1_task(), validation_root, timeout=1,
                                expected_runtime_binding=runner.compute_python_runtime_binding())
            except SystemExit as error:
                assert error.code == 1 and not signals
            else:
                raise AssertionError("validator timeout後に処理を続けた")
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
    print("process: normal/timeout/signal/late Popen monotonic再計測/no kill+killpg/no wait/private diagnostic (mock) OK", flush=True)


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
            if mode != "normal":
                activate()
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
            with forbid_after_outcome([target]) as activate, contextlib.redirect_stdout(output):
                try:
                    completed = validator.run_reload_no_kill(target / "progress.py", target)
                except SystemExit as error:
                    assert mode != "normal" and error.code == 1
                else:
                    assert mode == "normal" and completed.returncode == 0 and "P0" in completed.stdout
            assert not signals and created[-1].stdout.closed and created[-1].stderr.closed
            if mode != "normal":
                assert not (target / ".benchmark-tmp/c6-reload-interruption.json").exists()
                assert "192837465" not in output.getvalue()
    finally:
        validator.subprocess.Popen, runner.os.kill, runner.os.killpg = originals
    print("C6 reload: normal/timeout/exception/interrupt no kill/no root diagnostic/validation fail (mock) OK", flush=True)


def _synthetic_main():
    # managed macOS sandboxのmount cleanup停止を避け、private test rootを保持する。
    root = Path(tempfile.mkdtemp(prefix="p5-security-selftest-", dir="/private/tmp"))
    assert len(runner.verified_a_inputs()) == 1 and len(runner.verified_b_inputs()) == 7
    fingerprint_test(root / "fingerprint")
    permission_test(root / "permissions")
    prompt_contract_test()
    python_runtime_test(root / "python-runtime")
    event_test(root / "events")
    environment_canary_test(root / "env-canary")
    residual_process_test()
    snapshot_test(root / "snapshots")
    prepare_copy_test(root / "prepare-copy")
    preflight_test(root / "preflight")
    preflight_timeout_test(root / "preflight-timeout")
    integration_test(root / "integration")
    immediate_abort_test(root / "immediate-abort")
    campaign_fingerprint_guard_test()
    campaign_destination_test(root / "campaign-destination")
    directory_completion_abort_test(root / "directory-completion")
    model_rebound_abort_test(root / "model-rebound")
    driver_identity_test(root / "driver-identity")
    driver_summary_test(root / "driver-summary")
    deadline_phase_test(root / "deadline-phase")
    runtime_abort_test(root / "runtime-abort")
    preflight_runtime_abort_test(root / "preflight-runtime-abort")
    process_test(root / "process")
    c6_process_test(root / "c6-process")
    print("P5 security selftest: all passed; 実sandbox/実model呼出しなし; private root:", root)


def temp_boundary_test(root):
    root.mkdir(mode=0o700)
    patterns = fingerprint_module.PLATFORM_TEMP_DENY_GLOBS
    assert len(patterns) == 8
    # exactとdescendantを独立に確認し、root-only globで済ませる回帰を防ぐ。
    for target in ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp"):
        exact, deep = target.replace("tmp", "t[m]p"), target.replace("tmp", "t[m]p") + "/**"
        assert exact in patterns and deep in patterns
        for name in (target, target + "/canary", target + "/deep/nested/canary"):
            assert any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)
        expect_rejected(lambda target=target: fingerprint_module.reject_platform_temp(Path(target) / "formal/run-01"))
    alias = root / "temp-alias"
    alias.symlink_to("/private/tmp")
    expect_rejected(lambda: fingerprint_module.reject_platform_temp(alias / "formal"))
    with patch.dict(os.environ, {"HOME": "/private/tmp/fake-home"}):
        assert fingerprint_module.formal_base() == fingerprint_module.account_home() / "Library/Caches/agent-crew-p5-benchmark"
    private = root / "private"
    before = runner.private_directory_identity(private, create=True)
    private.chmod(0o755)
    expect_rejected(lambda: runner.private_directory_identity(private))
    assert private.stat().st_mode & 0o777 == 0o755
    private.chmod(0o700)
    original_fstat = os.fstat
    def replaced_identity(fd):
        value = original_fstat(fd)
        return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino + 1, st_uid=value.st_uid, st_mode=value.st_mode)
    with patch.object(os, "fstat", replaced_identity):
        assert runner.private_directory_identity(private) != before
    alias_private = root / "private-alias"
    alias_private.symlink_to(private)
    expect_rejected(lambda: runner.private_directory_identity(alias_private))
    # production入口guardはprepare/model/sandboxの前にtemp sourceを拒否する。
    expect_rejected(lambda: runner.require_formal_locations(root))
    print("temp boundary: eight exact+descendant globs/account HOME/realpath alias/private identity+mode OK", flush=True)


def codex_binding_test(root):
    root.mkdir(mode=0o700)
    executable = root / "codex"
    runner._write_private(executable, b"same-version-before", 0o700)
    original = fingerprint_module.compute_codex_executable_binding(executable)
    runtime = fingerprint_module.compute_python_runtime_binding()
    old_fp = fingerprint_module.compute_harness_fingerprint(HERE, python_runtime_binding=runtime, codex_executable_binding=original)
    runner._write_private(executable, b"same-version-after!", 0o700)
    changed = fingerprint_module.compute_codex_executable_binding(executable)
    assert changed != original and changed["sha256"] != original["sha256"]
    assert fingerprint_module.compute_harness_fingerprint(HERE, python_runtime_binding=runtime, codex_executable_binding=changed) != old_fp
    executable.unlink()
    executable.symlink_to(runner.CODEX_EXECUTABLE)
    expect_rejected(lambda: fingerprint_module.compute_codex_executable_binding(executable))
    campaign = root / "campaign"
    directories = runner.private_directory_identity(campaign, create=True)
    record = {"schema": 1, "fingerprint": old_fp, "codex_executable": original,
              "python_runtime": runtime,
              "driver_executable": fingerprint_module.compute_driver_executable_binding(),
              "driver_config": fingerprint_module.compute_driver_config_binding(),
              "private_directories": directories}
    record["binding_sha256"] = runner.canonical_digest(record)
    path = campaign / "campaign-binding.json"
    runner.save(path, record)
    assert runner.load_campaign_binding(path, campaign, old_fp)["record"] == record
    path.chmod(0o644)
    expect_rejected(lambda: runner.load_campaign_binding(path, campaign, old_fp))
    path.chmod(0o600)
    runner.save(path, {**record, "codex_executable": changed})
    expect_rejected(lambda: runner.load_campaign_binding(path, campaign, old_fp))
    runner.save(path, record)
    spec = {"root": campaign / "run-01", "binding": {"harness_fingerprint": old_fp}}
    for mode in ("mismatch", "exception"):
        def observed(*_args):
            if mode == "exception":
                raise OSError("synthetic CLI swap")
            return changed
        with patch.object(runner, "compute_codex_executable_binding", observed), forbid_after_outcome([spec["root"]]) as activate:
            activate()
            try:
                runner.require_codex_binding(spec, "model", original)
            except SystemExit as error:
                assert error.code == 1
            else:
                raise AssertionError("CLI差替えから停止しませんでした")
    assert (campaign / ".evidence/run-01/model-interruption.json").stat().st_mode & 0o777 == 0o600
    print("CLI binding: same-version bytes/stat/symlink/fingerprint/private campaign file/root-free abort OK", flush=True)


def deadline_phase_test(root):
    root.mkdir(mode=0o700)
    fake = root / "codex"
    runner._write_private(fake, FAKE, 0o700)
    fingerprint = compute_harness_fingerprint(HERE, codex_executable_binding=runner.compute_codex_executable_binding(fake))
    original_cli, original_preflight, original_manifest, original_execute = (
        runner.CODEX_EXECUTABLE, runner.per_run_preflight, runner.tree_manifest, runner.execute_command)
    real_monotonic = time.monotonic
    try:
        runner.CODEX_EXECUTABLE = str(fake)
        for stage in ("preflight", "manifest"):
            campaign = root / stage / ("p5-" + fingerprint[:16])
            runner.private_directory_identity(campaign, create=True)
            model = campaign / "run-01"
            clock = [real_monotonic()]
            deadline = clock[0] + 200
            phase = {"preflight_done": False, "expired": False}
            args = SimpleNamespace(task="C1", condition="A", repeat=1, run_id="run-01",
                                   campaign=str(campaign), fingerprint=fingerprint,
                                   deadline_monotonic=deadline)
            with forbid_after_outcome([model]) as activate, patch.object(runner.time, "monotonic", lambda: clock[0]):
                def slow_preflight(spec):
                    report = fake_preflight_report(spec)
                    phase["preflight_done"] = True
                    if stage == "preflight":
                        clock[0] = deadline + 1
                        phase["expired"] = True
                        activate()
                    return report
                def slow_manifest(path, *a, **kw):
                    value = original_manifest(path, *a, **kw)
                    if stage == "manifest" and phase["preflight_done"] and Path(path) == model and not phase["expired"]:
                        clock[0] = deadline + 1
                        phase["expired"] = True
                        activate()
                    return value
                runner.per_run_preflight, runner.tree_manifest = slow_preflight, slow_manifest
                runner.execute_command = lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("期限後のmodel起動"))
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        run_synthetic(args)
                    except SystemExit as error:
                        assert error.code == 1
                    else:
                        raise AssertionError("期限切れから停止しませんでした")
            assert phase["expired"]
            assert not (model / ".benchmark-result.json").exists()
            diagnostic = campaign / ".evidence/run-01" / (stage + "-interruption.json")
            assert diagnostic.exists() and runner.load(diagnostic)["root_access_after_failure"] is False
    finally:
        runner.CODEX_EXECUTABLE, runner.per_run_preflight, runner.tree_manifest, runner.execute_command = (
            original_cli, original_preflight, original_manifest, original_execute)
    print("deadline: slow preflight/manifest root-free abort before model OK (mock)", flush=True)


def driver_identity_test(root):
    root.mkdir(mode=0o700)
    head = "abcdef0" + "0" * 33
    source = root / "source/agent-crew-p5-abcdef0-sparse"
    here = source / "docs/codex-direct/migration-benchmark"
    original = here / "driver.py"
    copy = root / "drivers/p5_driver_v7.py"
    config = root / "drivers/p5-driver-v7-config.json"
    content = (HERE / "driver.py").read_bytes()
    runner._write_private(original, content, 0o644)
    runner._write_private(copy, content, 0o700)
    runner._write_private(config, json.dumps({"schema": 1, "source": str(source),
                                              "head": head, "fingerprint": "a" * 64}), 0o600)
    with patch.object(driver_source, "BASE", root), patch.object(driver_source, "DRIVERS", root / "drivers"), \
            patch.object(driver_source, "CONFIG", config), patch.object(driver_source, "SOURCE", None), \
            patch.object(driver_source, "HERE", None):
        driver_source.load_config()
        assert driver_source.SOURCE == source and driver_source.HERE == here
        binding = driver_source.external_binding()
        assert binding["source"]["sha256"] == binding["copy"]["sha256"]
        runner._write_private(copy, content + b"# changed\n", 0o700)
        try:
            driver_source.external_binding()
        except driver_source.Stop:
            pass
        else:
            raise AssertionError("外部driver差替えを許可した")
    assert driver_source.CAMPAIGN_SECONDS == 24 * 1200 + 315 + 300
    assert driver_source.DRIVER_GRACE_SECONDS >= 60
    print("driver: source/copy/config fixed identity and deadline budget OK (synthetic)", flush=True)


def driver_summary_test(root):
    root.mkdir(mode=0o700)
    campaign = root / ("p5-" + "a" * 16)
    campaign.mkdir(mode=0o700)
    binding = {"fingerprint": "a" * 64, "codex_executable": {"sha256": "b" * 64},
               "python_runtime": {"sha256": "c" * 64},
               "driver_executable": {"sha256": "d" * 64},
               "driver_config": {"sha256": "e" * 64}}
    campaign_binding = {"schema": 1, **binding,
                        "private_directories": {"root": driver_source.directory_record(campaign),
                                                "parent": driver_source.directory_record(root)}}
    def seal(record):
        record["binding_sha256"] = hashlib.sha256(json.dumps(
            {key: value for key, value in record.items() if key != "binding_sha256"},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return record
    seal(campaign_binding)
    summary = {"campaign": campaign.name, "fingerprint": binding["fingerprint"],
               "planned_runs": 24, "completed_records": 24, "stopped_reason": None,
               "codex_executable": binding["codex_executable"],
               "driver_executable": binding["driver_executable"], "driver_config": binding["driver_config"],
               "campaign_binding_file": str(campaign / "campaign-binding.json"),
               "campaign_binding_sha256": campaign_binding["binding_sha256"],
               "results": [{"run_id": f"run-{index:02d}", "fingerprint": binding["fingerprint"],
                            "pass_preliminary": True} for index in range(1, 25)]}
    def write(record, result):
        runner._write_private(campaign / "campaign-binding.json", json.dumps(record), 0o600)
        runner._write_private(campaign / "batch-summary.json", json.dumps(result), 0o600)
    def rejected(record, result):
        write(record, result)
        try:
            driver_source.verify_summary(campaign, binding, io.StringIO())
        except driver_source.Stop:
            return
        raise AssertionError("不正なdriver bindingを含むsummaryを許可した")
    write(campaign_binding, summary)
    driver_source.verify_summary(campaign, binding, io.StringIO())
    for field in ("driver_executable", "driver_config"):
        for mutation in (None, {"sha256": "f" * 64}):
            changed_binding = json.loads(json.dumps(campaign_binding))
            if mutation is None:
                del changed_binding[field]
            else:
                changed_binding[field] = mutation
            seal(changed_binding)
            changed_summary = json.loads(json.dumps(summary))
            changed_summary["campaign_binding_sha256"] = changed_binding["binding_sha256"]
            rejected(changed_binding, changed_summary)
            changed_summary = json.loads(json.dumps(summary))
            if mutation is None:
                del changed_summary[field]
            else:
                changed_summary[field] = mutation
            rejected(campaign_binding, changed_summary)
    print("driver: 24-record summary accepts complete binding, rejects driver field loss/tamper OK (synthetic)", flush=True)


def main():
    os.umask(0o077)
    guard_root = Path(tempfile.mkdtemp(prefix="p5-boundary-selftest-", dir="/private/tmp"))
    temp_boundary_test(guard_root / "boundaries")
    codex_binding_test(guard_root / "cli")
    # 実sandboxを起動しない合成caseだけtempへ配置する。production guardは上で実検証。
    # 実repo/旧campaignにはcanaryを作らず、同じ作成/照合/cleanupを専用合成親で試す。
    with contextlib.ExitStack() as stack:
        removed_directories = set()
        actual_rmdir, actual_lexists = os.rmdir, os.path.lexists
        def mock_canary_rmdir(path, *, dir_fd=None):
            if dir_fd is not None and str(path).startswith(".p5-boundary-"):
                # managed outer sandboxは空directoryのrmdirも拒否するため、ここだけ模擬する。
                child = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
                try:
                    assert not os.listdir(child), "cleanupでcanary内容が残りました"
                finally:
                    os.close(child)
                removed_directories.add(str(path))
                return
            return actual_rmdir(path, dir_fd=dir_fd)
        def mock_removed_lexists(path):
            return False if Path(path).name in removed_directories else actual_lexists(path)
        stack.enter_context(patch.object(os, "rmdir", mock_canary_rmdir))
        stack.enter_context(patch.object(os.path, "lexists", mock_removed_lexists))
        for module in {runner, preflight.runner}:
            stack.enter_context(patch.object(module, "require_formal_locations", lambda *_args: None))
            stack.enter_context(patch.object(module, "require_source_directory", lambda: None))
        stack.enter_context(patch.object(runner, "compute_harness_fingerprint", compute_harness_fingerprint))
        stack.enter_context(patch.object(preflight, "boundary_parents", lambda root: {
            label: root.parent / "synthetic-boundaries" / label for label in preflight.BOUNDARY_LABELS}))
        stack.enter_context(patch.object(preflight, "platform_temp_parents", lambda: {
            label: guard_root for label in preflight.TEMP_LABELS}))
        _synthetic_main()


if __name__ == "__main__":
    main()
