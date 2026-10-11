#!/usr/bin/env python3
"""Create one immutable, model-free v20 diagnostic verify/preflight artifact set."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import pwd

HERE = Path(__file__).resolve().parent
CACHE = Path(pwd.getpwuid(os.getuid()).pw_dir) / "Library/Caches/agent-crew-p5-benchmark"
REMOTE_REF = "refs/heads/codex/runtime-migration-p5-ledger"
sys.path.insert(0, str(HERE))
import harness_fingerprint


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def bind(path, *, realpath=None):
    info = path.lstat()
    data = path.read_bytes()
    return {"realpath": str(path.resolve(strict=True)) if realpath is None else realpath, "sha256": hashlib.sha256(data).hexdigest(),
            "device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
            "owner": info.st_uid, "mode": stat.S_IMODE(info.st_mode)}


def build():
    result = subprocess.run(["git", "-C", str(HERE.parents[2]), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True)
    head = result.stdout.strip()
    if len(head) != 40:
        raise RuntimeError("source HEAD unavailable")
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache_stat = CACHE.lstat()
    if not stat.S_ISDIR(cache_stat.st_mode) or cache_stat.st_uid != os.getuid() or stat.S_IMODE(cache_stat.st_mode) != 0o700:
        raise RuntimeError("private Cache identity invalid")
    root = CACHE / "drivers"
    root.mkdir(mode=0o700, exist_ok=True)
    root_stat = root.lstat()
    if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.getuid() or stat.S_IMODE(root_stat.st_mode) != 0o700:
        raise RuntimeError("driver root identity invalid")
    names = ("v20_diagnostic.py", "v20_selftest.py", "v20_driver.py")
    source_data = {name: (HERE / name).read_bytes() for name in names}
    driver_data = (HERE / "v20_driver.py").read_bytes()
    py = str(Path(sys.executable).resolve(strict=True))
    py_binding = bind(Path(py))
    shell_binding = bind(Path("/bin/zsh").resolve(strict=True))
    codex_binding = harness_fingerprint.compute_codex_executable_binding()
    codex_home = CACHE / "probe-v20-diagnostic" / "version-home"
    codex_home.mkdir(parents=True, mode=0o700, exist_ok=True)
    codex_home_stat = codex_home.lstat()
    if not stat.S_ISDIR(codex_home_stat.st_mode) or codex_home_stat.st_uid != os.getuid() or stat.S_IMODE(codex_home_stat.st_mode) != 0o700:
        raise RuntimeError("dedicated Codex version-check home identity invalid")
    version_result = subprocess.run([codex_binding["realpath"], "--version"], capture_output=True, text=True,
                                    timeout=10, env={"HOME": str(CACHE.parents[2]), "CODEX_HOME": str(codex_home),
                                                    "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                                                    "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
    cli_version = version_result.stdout.strip()
    if version_result.returncode != 0 or version_result.stderr or cli_version != "codex-cli 0.162.1":
        raise RuntimeError("fixed Codex CLI version verification failed")
    config = {"schema": 1, "version": 20, "source_head": head,
              "source_hashes": {n: hashlib.sha256(source_data[n]).hexdigest() for n in names},
              "driver_sha256": hashlib.sha256(driver_data).hexdigest(),
              "python_executable": py, "python_version": list(sys.version_info[:3]), "python_binding": py_binding,
              "shell_binding": shell_binding, "codex_binding": {"realpath": codex_binding["realpath"],
                  "sha256": codex_binding["sha256"], "device": codex_binding["device"], "inode": codex_binding["inode"],
                  "size": codex_binding["size"], "mtime_ns": codex_binding["mtime_ns"], "ctime_ns": codex_binding["ctime_ns"],
                  "owner": codex_binding["owner"], "mode": codex_binding["mode"]}, "cli_version": cli_version,
              "remote_budget_ref": REMOTE_REF, "model_transport": "OpenAI direct",
              "allowed_driver_modes": ["verify", "preflight"], "actual_invocations_enabled": False,
              "hard_cap": 28, "prior_consumed": 2, "diagnostic_limit": 1, "final_probe_limit": 1,
              "formal_run_count": 24, "retry": False,
              "global_ledger_directory": str(CACHE / "logs" / "v20-global-ledger"),
              "diagnostic_root": str(CACHE / "probe-v20-diagnostic"),
              "codex_home": str(codex_home),
              "historical_attempts": [x["id"] for x in __import__("v20_diagnostic").HISTORICAL]}
    config_data = canonical(config)
    launcher_data = ("#!/bin/zsh\nset -eu\n"
                     "if [[ $# -ne 1 || ( $1 != verify && $1 != preflight ) ]]; then print -u2 v20_fixed_artifact_invalid; exit 2; fi\n"
                     f"base=${{0:A:h}}\nexec {py} -B \"$base/driver.py\" \"$1\"\n").encode()
    fp_input = {"source": config["source_hashes"], "driver": config["driver_sha256"],
                "config": hashlib.sha256(config_data).hexdigest(), "launcher_template_sha256": hashlib.sha256(launcher_data).hexdigest(),
                "remote_ref": REMOTE_REF, "hard_cap": 28,
                "modes": {"driver.py": 0o500, "v20_driver.py": 0o400, "config.json": 0o400, "launcher.sh": 0o500,
                          "v20_diagnostic.py": 0o400, "v20_selftest.py": 0o400}}
    fingerprint = hashlib.sha256(canonical(fp_input)).hexdigest()
    final = root / f"p5-v20-diagnostic-{fingerprint[:20]}"
    if final.exists():
        raise RuntimeError("fixed artifact already exists; refusing overwrite")
    stage = Path(tempfile.mkdtemp(prefix=".v20-stage-", dir=root))
    try:
        for name, data in source_data.items():
            p = stage / name
            p.write_bytes(data); p.chmod(0o400)
        p = stage / "driver.py"; p.write_bytes(driver_data); p.chmod(0o500)
        p = stage / "v20_driver.py"; p.write_bytes(driver_data); p.chmod(0o400)
        p = stage / "config.json"; p.write_bytes(config_data); p.chmod(0o400)
        p = stage / "launcher.sh"; p.write_bytes(launcher_data); p.chmod(0o500)
        preflight_path = str(CACHE / "logs" / f"p5-v20-diagnostic-{fingerprint[:20]}-preflight.json")
        files = {name: bind(stage / name, realpath=str(final / name)) for name in
                 ("driver.py", "config.json", "launcher.sh", *names)}
        manifest = {"schema": 1, "version": 20, "fingerprint": fingerprint, "files": files,
                    "source_files": list(names), "preflight_path": preflight_path}
        (stage / "manifest.json").write_bytes(canonical(manifest)); (stage / "manifest.json").chmod(0o400)
        stage.chmod(0o500)
        stage.rename(final)
        return final, fingerprint
    except BaseException:
        try:
            stage.chmod(0o700)
            for path in stage.iterdir():
                path.chmod(0o600)
            shutil.rmtree(stage)
        except OSError:
            pass
        raise


if __name__ == "__main__":
    path, fingerprint = build()
    print(json.dumps({"artifact_path": str(path), "fingerprint": fingerprint}, sort_keys=True))
