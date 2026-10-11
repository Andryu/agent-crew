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


def load_manifest():
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
    if type(manifest["files"]) is not dict or set(manifest["files"]) != {"driver.py", "config.json", "launcher.sh", "v20_diagnostic.py", "v20_selftest.py"}:
        raise ValueError
    for name, expected in manifest["files"].items():
        actual = file_binding(base / name)
        if actual != expected:
            raise ValueError
    expected_modes = {"driver.py": 0o500, "config.json": 0o400, "launcher.sh": 0o500,
                      "v20_diagnostic.py": 0o400, "v20_selftest.py": 0o400}
    if {name: binding["mode"] for name, binding in manifest["files"].items()} != expected_modes:
        raise ValueError
    config = strict_json(base / "config.json")
    if (set(config) != {"schema", "version", "source_head", "source_hashes", "driver_sha256",
                        "python_executable", "python_version", "python_binding", "shell_binding", "codex_binding",
                        "cli_version", "remote_budget_ref",
                        "model_transport", "allowed_driver_modes", "actual_invocations_enabled", "hard_cap",
                        "prior_consumed", "diagnostic_limit", "final_probe_limit", "formal_run_count", "retry",
                        "global_ledger_directory", "diagnostic_root", "historical_attempts"}
            or type(config["schema"]) is not int or config["schema"] != 1
            or type(config["version"]) is not int or config["version"] != 20
            or config["remote_budget_ref"] != "refs/heads/codex/runtime-migration-p5-ledger"
            or config["model_transport"] != "OpenAI direct" or config["allowed_driver_modes"] != ["verify", "preflight"]
            or config["cli_version"] != "codex-cli 0.162.1"
            or config["actual_invocations_enabled"] is not False or config["hard_cap"] != 28
            or config["prior_consumed"] != 2 or config["diagnostic_limit"] != 1 or config["final_probe_limit"] != 1
            or config["formal_run_count"] != 24 or config["retry"] is not False
            or config["python_executable"] != str(Path(sys.executable).resolve(strict=True))
            or config["python_version"] != list(sys.version_info[:3])
            or file_binding(Path(config["python_executable"])) != config["python_binding"]
            or file_binding(Path(config["shell_binding"]["realpath"]), trusted_system=True) != config["shell_binding"]
            or file_binding(Path(config["codex_binding"]["realpath"]), trusted_system=True) != config["codex_binding"]):
        raise ValueError
    expected_cache = Path(pwd.getpwuid(os.getuid()).pw_dir) / "Library/Caches/agent-crew-p5-benchmark"
    expected_artifact = expected_cache / "drivers" / f"p5-v20-diagnostic-{manifest['fingerprint'][:20]}"
    expected_preflight = expected_cache / "logs" / f"p5-v20-diagnostic-{manifest['fingerprint'][:20]}-preflight.json"
    if (base != expected_artifact or manifest["preflight_path"] != str(expected_preflight)
            or not re.fullmatch(r"[0-9a-f]{40}", config["source_head"])
            or config["source_hashes"] != {"v20_diagnostic.py": manifest["files"]["v20_diagnostic.py"]["sha256"],
                                            "v20_selftest.py": manifest["files"]["v20_selftest.py"]["sha256"]}
            or config["historical_attempts"] != [x["id"] for x in v20.HISTORICAL]
            or config["global_ledger_directory"] != str(expected_cache / "logs/v20-global-ledger")
            or config["diagnostic_root"] != str(expected_cache / "probe-v20-diagnostic")
            or any(Path(config[key]).is_relative_to("/private/tmp") for key in ("global_ledger_directory", "diagnostic_root"))):
        raise ValueError
    version = subprocess.run([config["codex_binding"]["realpath"], "--version"], capture_output=True,
                             timeout=10, env={"HOME": pwd.getpwuid(os.getuid()).pw_dir,
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
    for name in ("v20_diagnostic.py", "v20_selftest.py", "driver.py"):
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
                                   "codex": config["codex_binding"], "cli_version": config["cli_version"]},
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


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    # This immutable artifact cannot initiate any invocation or contact a model.
    if len(args) != 1 or args[0] not in {"verify", "preflight"}:
        fail()
    try:
        base, manifest = load_manifest()
        counts = run_tests(base)
        if args[0] == "preflight":
            report = write_preflight(base, manifest, counts)
            print(f"v20 model-free preflight PASS: {report}")
        else:
            print("v20 model-free verify PASS")
    except Exception:
        fail()


if __name__ == "__main__":
    main()
