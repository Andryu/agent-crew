#!/usr/bin/env python3
"""Fixed v20 diagnostic artifact driver. Supports model-free verify/preflight only."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile

ERROR = "v20_fixed_artifact_invalid"


def fail():
    print(ERROR, file=sys.stderr)
    raise SystemExit(2)


def strict_json(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError
            out[key] = value
        return out
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def file_binding(path, *, trusted_system=False):
    real = path.resolve(strict=True)
    before = path.lstat()
    owners = {0, os.getuid()} if trusted_system else {os.getuid()}
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid not in owners
            or (trusted_system and before.st_mode & 0o022)):
        raise ValueError
    data = path.read_bytes()
    after = path.lstat()
    sig1 = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_mode)
    sig2 = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_mode)
    if sig1 != sig2 or len(data) != before.st_size:
        raise ValueError
    return {"realpath": str(real), "sha256": hashlib.sha256(data).hexdigest(), "device": before.st_dev,
            "inode": before.st_ino, "size": before.st_size, "mtime_ns": before.st_mtime_ns,
            "ctime_ns": before.st_ctime_ns, "owner": before.st_uid, "mode": stat.S_IMODE(before.st_mode)}


def load_manifest(*, verify_cli=True):
    base = Path(__file__).resolve(strict=True).parent
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    import v20_diagnostic as v20
    manifest_path = base / "manifest.json"
    manifest = strict_json(manifest_path)
    if (set(manifest) != {"schema", "version", "fingerprint", "files", "source_files", "preflight_path"}
            or type(manifest["schema"]) is not int or manifest["schema"] != 1
            or type(manifest["version"]) is not int or manifest["version"] != 20
            or type(manifest["fingerprint"]) is not str or len(manifest["fingerprint"]) != 64
            or type(manifest["preflight_path"]) is not str):
        raise ValueError
    if type(manifest["files"]) is not dict or set(manifest["files"]) != {"driver.py", "v20_driver.py", "config.json", "launcher.sh", "v20_diagnostic.py", "v20_selftest.py", "v20_seed_fixture.json", "p5-v20-plan.md"}:
        raise ValueError
    for name, expected in manifest["files"].items():
        actual = file_binding(base / name)
        if actual != expected:
            raise ValueError
    expected_modes = {"driver.py": 0o500, "v20_driver.py": 0o400, "config.json": 0o400, "launcher.sh": 0o500,
                      "v20_diagnostic.py": 0o400, "v20_selftest.py": 0o400, "v20_seed_fixture.json": 0o400,
                      "p5-v20-plan.md": 0o400}
    if {name: binding["mode"] for name, binding in manifest["files"].items()} != expected_modes:
        raise ValueError
    config = strict_json(base / "config.json")
    if (set(config) != {"schema", "version", "source_head", "source_hashes", "driver_sha256",
                        "python_executable", "python_version", "python_binding", "shell_binding", "codex_binding",
                        "cli_version", "remote_budget_ref", "binding_spec_sha256", "command_sha256",
                        "repository_path", "plan_sha256", "seed_payload_sha256", "seed_commit_pin",
                        "sandbox_binding", "sandbox_profile_sha256",
                        "model_transport", "allowed_driver_modes", "actual_invocations_enabled", "hard_cap",
                        "prior_consumed", "diagnostic_limit", "final_probe_limit", "formal_run_count", "retry",
                        "global_ledger_directory", "diagnostic_root", "codex_home", "historical_attempts"}
            or type(config["schema"]) is not int or config["schema"] != 1
            or type(config["version"]) is not int or config["version"] != 20
            or config["remote_budget_ref"] != "refs/heads/codex/runtime-migration-p5-ledger"
            or config["model_transport"] != "OpenAI direct" or config["allowed_driver_modes"] != ["verify", "preflight", "sandbox-preflight", "bootstrap-seed", "diagnostic-once"]
            or config["cli_version"] != "codex-cli 0.162.1"
            or config["actual_invocations_enabled"] is not True or config["hard_cap"] != 28
            or config["prior_consumed"] != 2 or config["diagnostic_limit"] != 1 or config["final_probe_limit"] != 1
            or config["formal_run_count"] != 24 or config["retry"] is not False
            or config["python_executable"] != str(Path(sys.executable).resolve(strict=True))
            or config["python_version"] != list(sys.version_info[:3])
            or file_binding(Path(config["python_executable"])) != config["python_binding"]
            or file_binding(Path(config["shell_binding"]["realpath"]), trusted_system=True) != config["shell_binding"]
            or file_binding(Path(config["codex_binding"]["realpath"]), trusted_system=True) != config["codex_binding"]
            or config["sandbox_binding"] != file_binding(Path("/usr/bin/sandbox-exec"), trusted_system=True)
            or config["sandbox_profile_sha256"] != v20.SANDBOX_PROFILE_SHA256
            or config["binding_spec_sha256"] != v20.BINDING_SPEC_SHA256
            or config["command_sha256"] != v20.runner_command_sha256(config["codex_binding"]["realpath"])):
        raise ValueError
    expected_cache = Path(pwd.getpwuid(os.getuid()).pw_dir) / "Library/Caches/agent-crew-p5-benchmark"
    repository = Path(config["repository_path"])
    plan_path = base / "p5-v20-plan.md"
    plan_bytes = plan_path.read_bytes()
    plan_text = plan_bytes.decode("utf-8", "strict")
    pins = re.findall(r"^\s*- Remote seed commit pin: (UNPINNED|[0-9a-f]{40,64})\s*$", plan_text, re.M)
    expected_repository = Path(pwd.getpwuid(os.getuid()).pw_dir) / "Workspace/agent-crew"
    if (not repository.is_absolute() or repository.resolve(strict=True) != repository
            or repository != expected_repository
            or hashlib.sha256(plan_bytes).hexdigest() != config["plan_sha256"] or len(pins) != 1
            or config["seed_payload_sha256"] != v20.SEED_SHA256
            or config["seed_commit_pin"] != (None if pins[0] == "UNPINNED" else pins[0])
            or (config["seed_commit_pin"] is not None and not re.fullmatch(r"[0-9a-f]{40,64}", config["seed_commit_pin"]))):
        raise ValueError
    expected_artifact = expected_cache / "drivers" / f"p5-v20-diagnostic-{manifest['fingerprint'][:20]}"
    expected_preflight = expected_cache / "logs" / f"p5-v20-diagnostic-{manifest['fingerprint'][:20]}-preflight.json"
    expected_codex_home = expected_cache / "probe-v20-diagnostic" / "version-home"
    codex_home_info = Path(config["codex_home"]).lstat()
    if (base != expected_artifact or manifest["preflight_path"] != str(expected_preflight)
            or not re.fullmatch(r"[0-9a-f]{40}", config["source_head"])
            or config["source_hashes"] != {"v20_diagnostic.py": manifest["files"]["v20_diagnostic.py"]["sha256"],
                                            "v20_selftest.py": manifest["files"]["v20_selftest.py"]["sha256"],
                                            "v20_driver.py": manifest["files"]["v20_driver.py"]["sha256"],
                                            "v20_seed_fixture.json": manifest["files"]["v20_seed_fixture.json"]["sha256"],
                                            "p5-v20-plan.md": manifest["files"]["p5-v20-plan.md"]["sha256"]}
            or config["historical_attempts"] != [x["id"] for x in v20.HISTORICAL]
            or config["global_ledger_directory"] != str(expected_cache / "logs/v20-global-ledger")
            or config["diagnostic_root"] != str(expected_cache / "probe-v20-diagnostic")
            or config["codex_home"] != str(expected_codex_home)
            or not stat.S_ISDIR(codex_home_info.st_mode) or codex_home_info.st_uid != os.getuid()
            or stat.S_IMODE(codex_home_info.st_mode) != 0o700
            or any(Path(config[key]).is_relative_to("/private/tmp") for key in ("global_ledger_directory", "diagnostic_root", "codex_home"))):
        raise ValueError
    if verify_cli:
        version = subprocess.run([config["codex_binding"]["realpath"], "--version"], capture_output=True,
                                 timeout=10, env={"HOME": pwd.getpwuid(os.getuid()).pw_dir,
                                                 "CODEX_HOME": config["codex_home"],
                                                 "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                                                 "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
        if version.returncode != 0 or version.stderr or version.stdout.decode("utf-8", "strict").strip() != config["cli_version"]:
            raise ValueError
    if (config["source_hashes"] != {name: manifest["files"][name]["sha256"] for name in manifest["source_files"]}
            or config["driver_sha256"] != manifest["files"]["driver.py"]["sha256"]):
        raise ValueError
    fingerprint_input = {"source": config["source_hashes"], "driver": config["driver_sha256"],
                         "config": manifest["files"]["config.json"]["sha256"],
                         "launcher_template_sha256": manifest["files"]["launcher.sh"]["sha256"],
                         "remote_ref": config["remote_budget_ref"], "hard_cap": config["hard_cap"],
                         "modes": expected_modes}
    canonical = (json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if hashlib.sha256(canonical).hexdigest() != manifest["fingerprint"]:
        raise ValueError
    return base, manifest


def run_tests(base):
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("v20_selftest_fixed", base / "v20_selftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    counts = module.run_all()
    for name in ("v20_diagnostic.py", "v20_selftest.py", "v20_driver.py", "driver.py"):
        compile((base / name).read_bytes(), name, "exec")
    if sum(counts.values()) < 1:
        raise ValueError
    return counts


def write_preflight(base, manifest, counts):
    target = Path(manifest["preflight_path"])
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    parent_info = target.parent.lstat()
    if (not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.getuid()
            or stat.S_IMODE(parent_info.st_mode) != 0o700):
        raise ValueError
    if os.path.lexists(target):
        raise ValueError
    # The report contains fixed identities and counts only; no environment values or process output.
    config = strict_json(base / "config.json")
    report = {"schema": 1, "version": 20, "fingerprint": manifest["fingerprint"],
              "manifest_sha256": hashlib.sha256((base / "manifest.json").read_bytes()).hexdigest(),
              "files": manifest["files"],
              "runtime_bindings": {"python": config["python_binding"], "shell": config["shell_binding"],
                                   "codex": config["codex_binding"], "sandbox_exec": config["sandbox_binding"],
                                   "sandbox_profile_sha256": config["sandbox_profile_sha256"],
                                   "cli_version": config["cli_version"]},
              "selftest_counts": counts, "model_calls": 0, "probe_attempts": 0, "formal_runs": 0,
              "result": "pass"}
    payload = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd, temp_name = tempfile.mkstemp(prefix=".v20-preflight-", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, target, follow_symlinks=False)
        os.unlink(temp_name)
        dfd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return target


HISTORICAL_RESULT_FILES = (
    ("probe-v18/probe-7425e11b51a4411bbaa1ad3078271387.result.json", 18,
     "0d34083162295255d680626619bf3960fd45e698b1402e0e1d998d6a22fac321",
     "7c16dae0ff7dd580a89b4cc23d2bc9371ad4ab003bd12828fb6e3aa3f30b7785"),
    ("probe-v19-final12/probe-799912cad216402fbfb4711b8d8b6b60.result.json", 19,
     "81205c4f7c3989b439dc4baa4ed95d04329ddd3553bb320013edc4df7f0f62e6",
     "2eecef40bb3b3e7fd5f1d1f6a8e9cc9a2c8f2e2c6e943ec332eadf17ae37089b"))


def validate_historical_seed_inputs(base, *, result_paths=None):
    import v20_diagnostic as v20
    cache = Path(pwd.getpwuid(os.getuid()).pw_dir) / "Library/Caches/agent-crew-p5-benchmark"
    paths = tuple(Path(x) for x in result_paths) if result_paths is not None else tuple(cache / x[0] for x in HISTORICAL_RESULT_FILES)
    if len(paths) != 2:
        raise ValueError
    for path, (_, version, fingerprint, result_sha) in zip(paths, HISTORICAL_RESULT_FILES):
        before = path.lstat()
        data = path.read_bytes()
        after = path.lstat()
        parsed = v20.strict_json(data)
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                           before.st_ctime_ns, before.st_mode, before.st_uid, before.st_nlink)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                          after.st_ctime_ns, after.st_mode, after.st_uid, after.st_nlink)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or identity_before != identity_after
                or len(data) != before.st_size or hashlib.sha256(data).hexdigest() != result_sha
                or type(parsed) is not dict or parsed.get("schema") != 2 or parsed.get("fingerprint") != fingerprint
                or parsed.get("passed") is not False or parsed.get("code") != "probe_gate_fail"):
            raise ValueError
    fixture = (base / "v20_seed_fixture.json").read_bytes()
    if hashlib.sha256(fixture).hexdigest() != v20.SEED_SHA256:
        raise ValueError
    v20.validate_seed_payload(fixture)
    return fixture


def bootstrap_seed(base, config, *, remote_factory=None, result_paths=None, ledger_root=None):
    import v20_diagnostic as v20
    if config["seed_commit_pin"] is not None:
        raise v20.LedgerError("seed_already_pinned")
    seed_payload = validate_historical_seed_inputs(base, result_paths=result_paths)
    remote = (remote_factory(config) if remote_factory is not None else
              v20.GitRemote(Path(config["repository_path"]), seed_commit_pin=None))
    root = Path(ledger_root) if ledger_root is not None else Path(config["global_ledger_directory"])
    ledger = v20.GlobalLedger(root, remote)
    commit = ledger.bootstrap(seed_payload)
    return {"seed_payload_sha256": hashlib.sha256(seed_payload).hexdigest(), "seed_commit_sha": commit}


def _write_new_private(path, payload, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())


def _binding_for_root(base, manifest, config, root):
    import v20_diagnostic as v20
    root = Path(root).resolve(strict=True)
    preflight = Path(manifest["preflight_path"])
    preflight_bytes = preflight.read_bytes()
    preflight_identity = file_binding(preflight)
    if preflight_identity["owner"] != os.getuid() or preflight_identity["mode"] != 0o600:
        raise ValueError
    preflight_obj = v20.strict_json(preflight_bytes)
    expected_runtime = {"python": config["python_binding"], "shell": config["shell_binding"],
        "codex": config["codex_binding"], "sandbox_exec": config["sandbox_binding"],
        "sandbox_profile_sha256": config["sandbox_profile_sha256"], "cli_version": config["cli_version"]}
    if (preflight_obj.get("fingerprint") != manifest["fingerprint"] or preflight_obj.get("result") != "pass"
            or preflight_obj.get("manifest_sha256") != hashlib.sha256((base / "manifest.json").read_bytes()).hexdigest()
            or preflight_obj.get("files") != manifest["files"] or preflight_obj.get("runtime_bindings") != expected_runtime
            or preflight_obj.get("model_calls") != 0 or preflight_obj.get("probe_attempts") != 0
            or preflight_obj.get("formal_runs") != 0 or type(preflight_obj.get("selftest_counts")) is not dict
            or not preflight_obj["selftest_counts"] or any(type(v) is not int or v < 0 for v in preflight_obj["selftest_counts"].values())):
        raise ValueError
    preflight_path = root / "preflight.json"
    _write_new_private(preflight_path, preflight_bytes, 0o400)
    root_info = root.lstat()
    root_identity = {"realpath": str(root), "device": root_info.st_dev, "inode": root_info.st_ino}
    manifest_path = base / "manifest.json"
    manifest_info = manifest_path.lstat()
    manifest_identity = {"absolute_path": str(manifest_path.absolute()), "realpath": str(manifest_path.resolve(strict=True)),
        "device": manifest_info.st_dev, "inode": manifest_info.st_ino, "owner": manifest_info.st_uid,
        "mode": stat.S_IMODE(manifest_info.st_mode)}
    preflight_sha = hashlib.sha256(preflight_bytes).hexdigest()
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    binding = {"fingerprint": "0"*64, "root_identity": root_identity, "artifact_root": str(base),
        "preflight_path": str(preflight_path), "manifest_identity": manifest_identity,
        "spec_sha256": config["binding_spec_sha256"], "command_sha256": config["command_sha256"],
        "preflight_sha256": preflight_sha, "manifest_sha256": manifest_sha}
    binding["fingerprint"] = hashlib.sha256(v20.canonical_bytes({"artifact_fingerprint": manifest["fingerprint"],
        "root_identity": root_identity, "spec_sha256": binding["spec_sha256"],
        "command_sha256": binding["command_sha256"], "preflight_sha256": preflight_sha})).hexdigest()
    return v20.validate_binding(binding)


def run_diagnostic_once(base, manifest, config):
    import v20_diagnostic as v20
    # This gate is deliberately before any git/remote operation, local ledger creation, or CLI start.
    if config["actual_invocations_enabled"] is not True or config["seed_commit_pin"] is None:
        raise v20.LedgerError("seed_commit_pin_missing")
    remote = v20.GitRemote(Path(config["repository_path"]), seed_commit_pin=config["seed_commit_pin"])
    ledger = v20.GlobalLedger(Path(config["global_ledger_directory"]), remote)
    local = ledger._read_local()
    _, records = ledger._verify_remote(local)
    if len(records) != 2:
        raise v20.LedgerError("prior_attempt_not_final")
    root_parent = Path(config["diagnostic_root"])
    parent_info = root_parent.lstat()
    if (not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.getuid()
            or stat.S_IMODE(parent_info.st_mode) != 0o700):
        raise ValueError
    root = root_parent / "diagnostic-once"
    root.mkdir(mode=0o700, exist_ok=False)
    binding = _binding_for_root(base, manifest, config, root)
    argv = (config["codex_binding"]["realpath"], *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)
    adapter = v20.FixedOpenAIDirectCodexAdapter(argv, command_sha256=config["command_sha256"],
        binding=binding, residual_scanner=v20._production_residual_scanner)
    def next_binding_factory(_report):
        final_root = root_parent / "final-probe-not-started"
        final_root.mkdir(mode=0o700, exist_ok=False)
        return _binding_for_root(base, manifest, config, final_root)
    v20.run_diagnostic_once(ledger, binding=binding, adapter=adapter,
        artifact_directory=root / "output", next_binding_factory=next_binding_factory, actual_enabled=True)
    final_records = ledger._read_local()["records"]
    item = final_records[-1]
    return {"attempt_id": item["id"], "state": item["state"], "determination": item.get("determination")}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {"verify", "preflight", "sandbox-preflight", "bootstrap-seed", "diagnostic-once"}:
        fail()
    try:
        mode = args[0]
        # Neither actual mode probes Codex before a diagnostic reservation. Bootstrap never starts Codex.
        base, manifest = load_manifest(verify_cli=mode in {"verify", "preflight", "sandbox-preflight"})
        if mode == "bootstrap-seed":
            config = strict_json(base / "config.json")
            result = bootstrap_seed(base, config)
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return
        if mode == "diagnostic-once":
            config = strict_json(base / "config.json")
            if config["seed_commit_pin"] is None:
                raise ValueError
            result = run_diagnostic_once(base, manifest, config)
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return
        counts = run_tests(base)
        if args[0] == "sandbox-preflight":
            module_path = base / "v20_diagnostic.py"
            sys.path.insert(0, str(base))
            import v20_diagnostic as v20
            outcome = v20.sandbox_boundary_preflight()
            print(f"v20 sandbox model-free preflight PASS: {outcome['profile_sha256']}")
        elif args[0] == "preflight":
            report = write_preflight(base, manifest, counts)
            print(f"v20 model-free preflight PASS: {report}")
        else:
            print("v20 model-free verify PASS")
    except Exception:
        fail()


if __name__ == "__main__":
    main()
