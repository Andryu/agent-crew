#!/usr/bin/env python3
"""Run the v20 model-free selftest straight from the source tree.

The selftest binds to an immutable artifact layout (manifest/config/mode bits). This entry builds
that layout inside a private temporary home with the normal artifact builder, then runs the same
checks against it. Nothing is written to the source directory, the real benchmark cache, or any
remote; no model client, seed bootstrap, probe, or formal run is reachable from here.

Usage (the user-owned Python 3.11+ that the artifact config records as python_executable, e.g.
~/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/bin/python3.12; the system/shim python3
is root-owned or too old and exits 2 with a fixed message):
    <that python> -B docs/codex-direct/migration-benchmark/v20_source_selftest.py
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


class _FakePasswd:
    def __init__(self, home):
        self.pw_dir = str(home)


class _FakePwd:
    """Stand-in for the pwd module: only the temporary home differs from the real account."""
    def __init__(self, home):
        self._home = home

    def getpwuid(self, _uid):
        return _FakePasswd(self._home)


def _child(artifact, home):
    sys.dont_write_bytecode = True
    sys.path.insert(0, artifact)
    import v20_driver
    v20_driver.pwd = _FakePwd(home)
    base, _manifest = v20_driver.load_manifest(verify_cli=False)
    counts = v20_driver.run_tests(base)
    print("v20 source selftest: PASS " + json.dumps(counts, sort_keys=True) + f" total={sum(counts.values())}")


def _make_removable(root):
    """chmod only real files/directories inside the temporary home. Codex's `--version` leaves symlinks
    (arg0 aliases) to the real Codex executable there; chmod would follow them and alter that binary."""
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        try:
            path.chmod(0o700)
        except OSError:
            pass


REQUIREMENT_MESSAGE = "v20_source_selftest_requires_user_owned_python_with_tomllib"


def _interpreter_ok():
    try:
        if os.stat(os.path.realpath(sys.executable)).st_uid != os.getuid():
            return False
        import tomllib  # noqa: F401
    except (OSError, ImportError):
        return False
    return True


def main():
    if not _interpreter_ok():
        print(REQUIREMENT_MESSAGE, file=sys.stderr)
        return 2
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        _child(sys.argv[2], sys.argv[3])
        return 0
    if len(sys.argv) != 1:
        print("usage: v20_source_selftest.py", file=sys.stderr)
        return 2
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE))
    import harness_fingerprint
    codex = harness_fingerprint.CODEX_REAL_PATH
    before = (codex.stat().st_ctime_ns, codex.stat().st_mode)
    status = _run_in_temporary_home()
    after = (codex.stat().st_ctime_ns, codex.stat().st_mode)
    if after != before:
        print("v20_source_selftest_changed_codex_executable", file=sys.stderr)
        return 3
    return status


def _run_in_temporary_home():
    # /private/tmp is rejected by the artifact layout checks, so use the system-wide /var/tmp.
    parent = Path("/var/tmp").resolve(strict=True)
    home = Path(tempfile.mkdtemp(prefix="p5-v20-source-selftest-", dir=parent)).resolve(strict=True)
    try:
        sys.path.insert(0, str(HERE))
        import v20_artifacts
        cache = home / "Library/Caches/agent-crew-p5-benchmark"
        (home / "Workspace/agent-crew").mkdir(parents=True, mode=0o700)
        v20_artifacts.CACHE = cache
        v20_artifacts.pwd = _FakePwd(home)
        artifact, _fingerprint = v20_artifacts.build()
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--child",
                                 str(artifact), str(home)], cwd=str(home))
        return result.returncode
    finally:
        _make_removable(home)
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
