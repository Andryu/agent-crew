#!/usr/bin/env python3.12
"""通常shell専用P5 driver。正式campaignを再開・削除・自動killしない。"""

import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import signal
import stat
import subprocess
import sys
import time
import uuid

ACCOUNT_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
BASE = ACCOUNT_HOME / "Library/Caches/agent-crew-p5-benchmark"
DRIVERS = BASE / "drivers"
LOGS = DRIVERS / "logs/v19-final"
FORMAL = BASE / "formal"
CONFIG = DRIVERS / "p5-driver-v19-final-config.json"
LAUNCHER = DRIVERS / "p5-v19-final-normal-shell.sh"
SOURCE = None
HERE = None
STATUS = LOGS / "status.json"
LOCK = LOGS / "driver.lock"
PYTHON = ACCOUNT_HOME / ".local/share/uv/python/cpython-3.12.13-macos-aarch64-none/bin/python3.12"
GIT = "/usr/bin/git"
BASH = "/bin/bash"
EXPECTED_HEAD = None
EXPECTED_FINGERPRINT = None
LOADED_LAUNCHER_BINDING = None
FIXED_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
CAMPAIGN_SECONDS = 24 * 1200 + 315 + 300
DRIVER_GRACE_SECONDS = 600
KNOWN_PRIVACY_LINES = {
    ("docs/codex-direct/migration-benchmark/harness_fingerprint.py", 312):
        "e3a5c6c684f77b12d5726043ee75ac55a47f848ceb116e745bc7562dcc2d244f",
    ("docs/codex-direct/migration-benchmark/selftest.py", 328):
        "b74639bd80b379b2183ecdea29f134e27d728e328fff6364fd99229cb7efcc3c",
    ("docs/plans/2026-09-22-p5-rerun.md", 143):
        "d205ebe2ffb34164980881f749c36ee5007f76b2b310e5aa45c77e4261dbb7f3",
}


class Stop(Exception):
    pass


class Interrupted(BaseException):
    def __init__(self, number):
        self.number = number


def on_signal(number, _frame):
    raise Interrupted(number)


def open_dir(path, create=False):
    """絶対pathの全componentをnofollowで辿る。"""
    path = Path(path)
    if not path.is_absolute():
        raise Stop("absolute_directory_required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def directory_identity(path, create=False):
    fd = open_dir(path, create=create)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise Stop("private_directory_owner_or_mode: " + str(path))
        return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
    finally:
        os.close(fd)


def directory_record(path):
    device, inode, owner, mode = directory_identity(path)
    return {"realpath": str(Path(path).resolve(strict=True)), "device": device,
            "inode": inode, "owner": owner, "mode": mode}


def regular_identity(path, mode=0o600):
    path = Path(path)
    parent = open_dir(path.parent)
    try:
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != mode):
            raise Stop("private_file_owner_type_or_mode: " + str(path))
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise Stop("private_file_replaced: " + str(path))
            data = bytearray()
            while chunk := os.read(fd, 1024 * 1024):
                data.extend(chunk)
            after = os.fstat(fd)
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if signature(before) != signature(after) or signature(after) != signature(current):
                raise Stop("private_file_changed_during_read: " + str(path))
            return bytes(data)
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def external_binding():
    """repo原本、実行copy、configの同一bytesとstat identityを固定する。"""
    original = HERE / "driver.py"
    runtime = DRIVERS / "p5_driver_v19_final.py"
    launcher_bytes = regular_identity(LAUNCHER, mode=0o700)
    original_bytes = regular_identity(original, mode=0o644)
    runtime_bytes = regular_identity(runtime, mode=0o700)
    config_bytes = regular_identity(CONFIG)
    if original_bytes != runtime_bytes:
        raise Stop("external_driver_differs_from_harness_source")
    def metadata(path):
        info = path.lstat()
        return {"path": str(path), "sha256": hashlib.sha256(regular_identity(path, stat.S_IMODE(info.st_mode))).hexdigest(),
                "device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
                "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
                "owner": info.st_uid, "mode": stat.S_IMODE(info.st_mode)}
    launcher_info = LAUNCHER.lstat()
    launcher = {"path": str(LAUNCHER), "sha256": hashlib.sha256(launcher_bytes).hexdigest(),
        "device": launcher_info.st_dev, "inode": launcher_info.st_ino, "size": launcher_info.st_size,
        "mtime_ns": launcher_info.st_mtime_ns, "ctime_ns": launcher_info.st_ctime_ns,
        "owner": launcher_info.st_uid, "mode": stat.S_IMODE(launcher_info.st_mode)}
    return {"source": metadata(original), "copy": metadata(runtime), "config": metadata(CONFIG),
            "config_sha256": hashlib.sha256(config_bytes).hexdigest(), "launcher": launcher}


def load_config():
    global SOURCE, HERE, EXPECTED_HEAD, EXPECTED_FINGERPRINT, LOADED_LAUNCHER_BINDING
    config = json.loads(regular_identity(CONFIG))
    expected_fields = {"schema", "source", "head", "fingerprint", "launcher_binding"}
    if (set(config) != expected_fields or config["schema"] != 3
            or not isinstance(config["head"], str) or len(config["head"]) != 40
            or not isinstance(config["fingerprint"], str) or len(config["fingerprint"]) != 64):
        raise Stop("invalid_driver_config")
    launcher_info = LAUNCHER.lstat()
    launcher_binding = {"path": str(LAUNCHER), "sha256": hashlib.sha256(regular_identity(LAUNCHER, mode=0o700)).hexdigest(),
        "device": launcher_info.st_dev, "inode": launcher_info.st_ino, "size": launcher_info.st_size,
        "mtime_ns": launcher_info.st_mtime_ns, "ctime_ns": launcher_info.st_ctime_ns,
        "owner": launcher_info.st_uid, "mode": stat.S_IMODE(launcher_info.st_mode)}
    if config["launcher_binding"] != launcher_binding:
        raise Stop("normal_shell_launcher_binding_changed")
    source = Path(config["source"])
    if (not source.is_absolute() or source.parent != BASE / "source"
            or source.name != "agent-crew-p5-" + config["head"][:7] + "-sparse"):
        raise Stop("driver_config_source_path_invalid")
    SOURCE, HERE = source, source / "docs/codex-direct/migration-benchmark"
    EXPECTED_HEAD, EXPECTED_FINGERPRINT = config["head"], config["fingerprint"]
    LOADED_LAUNCHER_BINDING = launcher_binding


def new_file(path, data):
    path = Path(path)
    parent = open_dir(path.parent)
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=parent)
        try:
            os.fchmod(fd, 0o600)
            data = data.encode("utf-8") if isinstance(data, str) else data
            offset = 0
            while offset < len(data):
                offset += os.write(fd, data[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def remove_file(path):
    path = Path(path)
    regular_identity(path)
    parent = open_dir(path.parent)
    try:
        os.unlink(path.name, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def status_write(value):
    if os.path.lexists(STATUS):
        regular_identity(STATUS)
    temporary = STATUS.with_name(".status-" + uuid.uuid4().hex)
    new_file(temporary, json_bytes(value))
    parent = open_dir(LOGS)
    try:
        if os.path.lexists(STATUS):
            regular_identity(STATUS)
        os.rename(temporary.name, STATUS.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)
    regular_identity(STATUS)


def child_env():
    # 呼出し元HOME/PATHを継承せず、認証情報以外も最小化する。
    home = str(Path(pwd.getpwuid(os.getuid()).pw_dir))
    env = {"HOME": home, "PATH": FIXED_PATH, "LANG": "en_US.UTF-8", "TMPDIR": "/private/tmp"}
    if "CODEX_HOME" in os.environ:
        candidate = Path(os.environ["CODEX_HOME"])
        if not candidate.is_absolute() or candidate.is_symlink():
            raise Stop("invalid_CODEX_HOME")
        env["CODEX_HOME"] = str(candidate)
    return env


def command(argv, log, capture=False, timeout=None):
    log.write("$ " + " ".join(map(str, argv)) + "\n")
    log.flush()
    process = subprocess.Popen([str(part) for part in argv], cwd=SOURCE, env=child_env(),
                               stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE if capture else log,
                               stderr=log, start_new_session=True)
    try:
        if capture:
            output, _ = process.communicate(timeout=timeout)
        else:
            process.wait(timeout=timeout)
            output = b""
    except subprocess.TimeoutExpired:
        raise Stop("child_timeout_process_may_remain_no_kill") from None
    if process.returncode != 0:
        raise Stop("command_nonzero:" + Path(str(argv[0])).name + ":" + str(process.returncode))
    return output


def source_check(log, expected_directories=None):
    directories = {str(path): directory_identity(path, create=path in (LOGS, FORMAL))
                   for path in (BASE, SOURCE.parent, SOURCE, DRIVERS, LOGS, FORMAL)}
    if expected_directories is not None and directories != expected_directories:
        raise Stop("source_or_private_directory_identity_changed")
    head = command([GIT, "rev-parse", "HEAD"], log, capture=True).decode().strip()
    if head != EXPECTED_HEAD:
        raise Stop("unexpected_source_HEAD")
    if command([GIT, "status", "--porcelain=v1", "--untracked-files=all"], log, capture=True).strip():
        raise Stop("source_worktree_not_clean")
    return directories


def load_shared():
    spec = importlib.util.spec_from_file_location("p5_driver_fingerprint", HERE / "harness_fingerprint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bindings(shared):
    runtime = shared.compute_python_runtime_binding()
    cli = shared.compute_codex_executable_binding()
    driver = shared.compute_driver_executable_binding()
    config = shared.compute_driver_config_binding()
    launcher_binding = shared.compute_normal_shell_launcher_binding()
    external = external_binding()
    if external["copy"] != driver or external["config"] != config:
        raise Stop("external_driver_binding_changed")
    if external["launcher"] != LOADED_LAUNCHER_BINDING or external["launcher"] != launcher_binding:
        raise Stop("normal_shell_launcher_binding_changed")
    fingerprint = shared.compute_harness_fingerprint(HERE, python_runtime_binding=runtime,
                                                      codex_executable_binding=cli,
                                                      driver_executable_binding=driver,
                                                      normal_shell_launcher_binding=launcher_binding)
    if fingerprint != EXPECTED_FINGERPRINT:
        raise Stop("unexpected_harness_fingerprint")
    return {"fingerprint": fingerprint, "python_runtime": runtime, "codex_executable": cli,
            "driver_executable": driver, "driver_config": config}


def privacy_check(log):
    # clean sourceではprivacy-check.shの変更差分は0件。既知fixtureも固定行hashで検証する。
    summary = json.loads(command([BASH, "scripts/privacy-check.sh", "--summary"], log, capture=True))
    detail = command([BASH, "scripts/privacy-check.sh"], log, capture=True)
    if summary != {"findings": 0} or detail.strip():
        raise Stop("privacy_check_unexpected_findings")
    for (name, number), expected_hash in KNOWN_PRIVACY_LINES.items():
        lines = (SOURCE / name).read_text(encoding="utf-8").splitlines()
        if number > len(lines) or hashlib.sha256(lines[number - 1].encode()).hexdigest() != expected_hash:
            raise Stop("known_privacy_fixture_changed:" + name)
    return {"findings": 0, "known_false_positive_lines_verified": len(KNOWN_PRIVACY_LINES)}


def verification(log, shared):
    directories = source_check(log)
    expected = bindings(shared)
    for name in ("selftest.py", "analysis_selftest.py", "v16_selftest.py", "v17_selftest.py", "v18_selftest.py", "v19_selftest.py"):
        command([PYTHON, "-B", HERE / name], log)
    compile_files = ("run.py", "sandbox_preflight.py", "validate_c6.py", "selftest.py",
                     "batch.py", "analyze.py", "analysis_selftest.py", "harness_fingerprint.py",
                     "probe_v16.py", "fixed_test_runner_v16.py", "v16_selftest.py",
                     "probe_v17.py", "fixed_test_runner_v17.py", "v17_selftest.py", "v18_selftest.py",
                     "probe_v19.py", "v19_selftest.py")
    command([PYTHON, "-B", "-X", "pycache_prefix=" + str(LOGS / "pycache"), "-m", "py_compile",
             *[HERE / name for name in compile_files]], log)
    command([GIT, "diff", "--check"], log)
    privacy = privacy_check(log)
    source_check(log, directories)
    if bindings(shared) != expected:
        raise Stop("source_or_binding_changed_during_verification")
    return expected, privacy, directories


def fresh_campaign(binding):
    campaign = FORMAL / ("p5-" + binding["fingerprint"][:16])
    reservation = LOGS / ("p5-" + binding["fingerprint"] + ".started.json")
    active = LOGS / ("p5-" + binding["fingerprint"] + ".active.json")
    if os.path.lexists(campaign):
        raise Stop("existing_campaign_no_resume")
    if os.path.lexists(reservation):
        raise Stop("existing_reservation_no_resume")
    if os.path.lexists(active):
        raise Stop("existing_driver_active_marker")
    return campaign, reservation, active


def verify_summary(campaign, binding, log):
    if os.path.lexists(campaign / "active-run.json"):
        raise Stop("active_operation_marker_retained")
    result = json.loads(regular_identity(campaign / "batch-summary.json"))
    campaign_binding = json.loads(regular_identity(campaign / "campaign-binding.json"))
    fixed = {key: value for key, value in campaign_binding.items() if key != "binding_sha256"}
    binding_hash = hashlib.sha256(json.dumps(fixed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if (set(campaign_binding) != {"schema", "fingerprint", "codex_executable", "python_runtime",
                                  "driver_executable", "driver_config", "private_directories", "binding_sha256"}
            or campaign_binding["schema"] != 1 or campaign_binding["binding_sha256"] != binding_hash
            or campaign_binding["private_directories"] !=
                {"root": directory_record(campaign), "parent": directory_record(campaign.parent)}):
        raise Stop("campaign_binding_invalid_after_batch")
    entries = result.get("results")
    if (result.get("campaign") != campaign.name or result.get("fingerprint") != binding["fingerprint"]
            or type(result.get("completed_records")) is not int or result["completed_records"] != 24
            or type(result.get("planned_runs")) is not int or result["planned_runs"] != 24
            or "stopped_reason" not in result or result["stopped_reason"] is not None
            or not isinstance(entries, list) or len(entries) != 24
            or result.get("codex_executable") != binding["codex_executable"]
            or result.get("driver_executable") != binding["driver_executable"]
            or result.get("driver_config") != binding["driver_config"]
            or result.get("campaign_binding_file") != str(campaign / "campaign-binding.json")
            or result.get("campaign_binding_sha256") != campaign_binding.get("binding_sha256")
            or campaign_binding.get("fingerprint") != binding["fingerprint"]
            or campaign_binding.get("codex_executable") != binding["codex_executable"]
            or campaign_binding.get("python_runtime") != binding["python_runtime"]
            or campaign_binding.get("driver_executable") != binding["driver_executable"]
            or campaign_binding.get("driver_config") != binding["driver_config"]):
        raise Stop("incomplete_or_unbound_campaign_summary")
    for index, entry in enumerate(entries, 1):
        if (entry.get("run_id") != f"run-{index:02d}" or entry.get("fingerprint") != binding["fingerprint"]
                or entry.get("pass_preliminary") is not True):
            raise Stop("invalid_campaign_record:" + str(index))
    log.write("verified 24 preliminary records\n")


def main():
    if sys.argv[1:] not in ([], ["--verify-only"]):
        raise SystemExit("使用方法: p5_driver.py [--verify-only]")
    dry = sys.argv[1:] == ["--verify-only"]
    os.umask(0o077)
    if Path(sys.executable).resolve(strict=True) != PYTHON:
        raise Stop("wrong_fixed_python")
    if Path(pwd.getpwuid(os.getuid()).pw_dir) != BASE.parents[2]:
        raise Stop("wrong_OS_account_home")
    os.environ["HOME"] = str(BASE.parents[2])
    os.environ["PATH"] = FIXED_PATH
    load_config()
    for path in (BASE, SOURCE.parent, SOURCE, DRIVERS):
        directory_identity(path)
    directory_identity(LOGS, create=True)
    directory_identity(FORMAL, create=True)
    lock_parent = open_dir(LOGS)
    try:
        lock_fd = os.open(LOCK.name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=lock_parent)
    finally:
        os.close(lock_parent)
    lock_info = os.fstat(lock_fd)
    lock_parent = open_dir(LOGS)
    try:
        lock_current = os.stat(LOCK.name, dir_fd=lock_parent, follow_symlinks=False)
    finally:
        os.close(lock_parent)
    if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1 or
            lock_info.st_uid != os.getuid() or stat.S_IMODE(lock_info.st_mode) != 0o600 or
            (lock_info.st_dev, lock_info.st_ino) != (lock_current.st_dev, lock_current.st_ino)):
        raise Stop("invalid_driver_lock")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise Stop("another_driver_is_running") from None
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
    log_path = LOGS / (run_id + ".log")
    new_file(log_path, b"")
    log_parent = open_dir(LOGS)
    try:
        log_fd = os.open(log_path.name, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, dir_fd=log_parent)
        log_info = os.fstat(log_fd)
        log_current = os.stat(log_path.name, dir_fd=log_parent, follow_symlinks=False)
        if (not stat.S_ISREG(log_info.st_mode) or log_info.st_nlink != 1 or
                log_info.st_uid != os.getuid() or stat.S_IMODE(log_info.st_mode) != 0o600 or
                (log_info.st_dev, log_info.st_ino) != (log_current.st_dev, log_current.st_ino)):
            raise Stop("invalid_driver_log")
    finally:
        os.close(log_parent)
    status = {"run_id": run_id, "pid": os.getpid(), "stage": "starting", "verify_only": dry,
              "log": str(log_path), "source": str(SOURCE), "head": EXPECTED_HEAD,
              "fingerprint": EXPECTED_FINGERPRINT, "campaign": None, "exit_code": None}
    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(number, on_signal)
    with os.fdopen(log_fd, "w", encoding="utf-8", buffering=1) as log:
        def advance(stage, code=None, reason=None, **extra):
            status.update(stage=stage, exit_code=code, reason=reason,
                          updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), **extra)
            status_write(status)
            log.write(stage + ": " + str(reason) + "\n")
            print("P5 driver: " + stage + " (" + str(reason) + ")", flush=True)
        advance("verifying")
        try:
            shared = load_shared()
            expected, privacy, directories = verification(log, shared)
            campaign, reservation, active = fresh_campaign(expected)
            if dry:
                advance("verified", 0, "no_campaign_or_reservation_created", privacy=privacy,
                        driver_executable=expected["driver_executable"], driver_config=expected["driver_config"])
                return 0
            sys.path.insert(0, str(HERE))
            probe_spec = importlib.util.spec_from_file_location("p5_probe_v19", HERE / "probe_v19.py")
            probe_module = importlib.util.module_from_spec(probe_spec)
            probe_spec.loader.exec_module(probe_module)
            try:
                probe_module.require_final_probe(expected["fingerprint"],
                    driver_config_binding=expected["driver_config"])
            except (OSError, ValueError) as error:
                raise Stop("final_fixed_probe_not_passed:" + type(error).__name__) from None
            source_check(log, directories)
            if bindings(shared) != expected:
                raise Stop("binding_changed_before_batch")
            fresh_campaign(expected)
            campaign_deadline = time.monotonic() + CAMPAIGN_SECONDS
            campaign_started_epoch = time.time()
            reservation_bytes = json_bytes({"schema": 1, "run_id": run_id, "pid": os.getpid(),
                "head": EXPECTED_HEAD, "campaign": str(campaign), "binding": expected,
                "source_directories": directories, "log": str(log_path),
                "campaign_deadline_monotonic": campaign_deadline,
                "campaign_started_epoch": campaign_started_epoch})
            new_file(reservation, reservation_bytes)
            if regular_identity(reservation) != reservation_bytes:
                raise Stop("reservation_changed_after_creation")
            formal_fd = open_dir(FORMAL)
            try:
                os.mkdir(campaign.name, 0o700, dir_fd=formal_fd)
                os.fsync(formal_fd)
            finally:
                os.close(formal_fd)
            campaign_identity = directory_identity(campaign)
            active_bytes = json_bytes({"schema": 1, "run_id": run_id, "campaign": str(campaign),
                                         "campaign_identity": campaign_identity,
                                         "reservation": str(reservation), "pid": os.getpid(),
                                         "campaign_deadline_monotonic": campaign_deadline,
                                         "driver_executable": expected["driver_executable"],
                                         "driver_config": expected["driver_config"]})
            new_file(active, active_bytes)
            if regular_identity(active) != active_bytes:
                raise Stop("driver_active_marker_changed_after_creation")
            advance("campaign", None, "batch_started", campaign=str(campaign),
                    reservation=str(reservation), active_marker=str(active), privacy=privacy,
                    campaign_deadline_monotonic=campaign_deadline,
                    campaign_started_epoch=campaign_started_epoch,
                    driver_executable=expected["driver_executable"], driver_config=expected["driver_config"])
            process = subprocess.Popen([str(PYTHON), "-B", str(HERE / "batch.py"),
                                        "--campaign-deadline-monotonic", str(campaign_deadline)], cwd=SOURCE,
                                       env=child_env(), stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
            try:
                code = process.wait(timeout=max(0, campaign_deadline + DRIVER_GRACE_SECONDS - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise Stop("batch_timeout_process_may_remain_no_kill") from None
            status["batch_exit_code"] = code
            source_check(log, directories)
            if bindings(shared) != expected:
                raise Stop("binding_changed_after_batch")
            if directory_identity(campaign) != campaign_identity:
                raise Stop("campaign_directory_identity_changed")
            if regular_identity(reservation) != reservation_bytes or regular_identity(active) != active_bytes:
                raise Stop("driver_reservation_or_active_marker_changed")
            if code != 0:
                raise Stop("batch_nonzero:" + str(code))
            verify_summary(campaign, expected, log)
            remove_file(active)
            advance("completed", 0, "all_24_records_completed")
            return 0
        except Interrupted as error:
            advance("stopped", 128 + error.number, "signal_received_processes_may_remain_no_kill")
            return 128 + error.number
        except BaseException as error:
            reason = str(error) if isinstance(error, Stop) else "driver_exception_private_log"
            log.write(type(error).__name__ + ": " + str(error) + "\n")
            advance("stopped", 1, reason)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
