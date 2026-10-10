#!/usr/bin/env python3
"""batch・再分類・集計が共用する、固定入力のharness fingerprint。"""

import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import pwd
import shutil
import stat
import struct
import sys

PYTHON_EXECUTABLE = str(Path(sys.executable).resolve(strict=True))
PYTHON_RUNTIME_ROOT = Path(sys.base_prefix).resolve(strict=True)
PYTHON_VERSION = (3, 12, 13)
CODEX_LAUNCH_PATH = Path(os.path.abspath(shutil.which("codex") or "/opt/homebrew/bin/codex"))
CODEX_REAL_PATH = CODEX_LAUNCH_PATH.resolve(strict=True)
_CLI_HASH_CACHE = {}
_C_UTF8_SHA256 = hashlib.sha256(b"C.UTF-8").hexdigest()
PLATFORM_TEMP_ROOTS = tuple(Path(value) for value in ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp"))
# character classでroot自身をglob denyにし、/**を別に追加して全子孫も遮断する。
# 0.155.1はsaw_glob=trueのpatternに子孫suffixを自動追加しない。
PLATFORM_TEMP_DENY_GLOBS = tuple(pattern for root in
    ("/t[m]p", "/private/t[m]p", "/var/t[m]p", "/private/var/t[m]p") for pattern in (root, root + "/**"))
# 実exec toolの決定論的正規化仕様。値そのものは保存せず、許可値・正規化後hash・由来をfingerprintに含める。
CODEX_TOOL_ENV_NORMALIZATION = {
    "schema": 1,
    "source": "v19_fixed_macos_codex_tool_environment_spec",
    "keys": {
        "LANG": {"kind": "exact_value_sha256", "sha256": _C_UTF8_SHA256,
                 "derivation": "model_free_normal_shell_preflight_locale_observation"},
        "LC_ALL": {"kind": "exact_value_sha256", "sha256": _C_UTF8_SHA256,
                   "derivation": "model_free_normal_shell_preflight_locale_observation"},
        "PATH": {"kind": "codex_macos_path_v1", "allowed_profile_sha256": {
                    "normal_shell_login": "104462fab1d53252cbc8ca3562d5e04ce4718369c9dfe647a01df810728f09d7",
                    "codex_host": "8283ba217254d7532bdd107b5dd947a6c6d1ec66f684b69a999975c4979b0acb"},
                 "derivation": "model_free_normal_shell_preflight_and_codex_host_path_projection"},
    },
    "path_normalizer": "allowlisted_components_ordered_with_ephemeral_codex_paths_tokenized_v1",
}


def account_home():
    """toolのsynthetic HOMEや呼出元環境には依存しない。"""
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def formal_base():
    return account_home() / "Library/Caches/agent-crew-p5-benchmark"


def _private_executable_binding(path, expected_mode):
    path = Path(path)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != expected_mode):
        raise ValueError("driver fileのowner/type/modeが不正です")
    content = _read_regular_file(path)
    after = path.lstat()
    if _stat_signature(before) != _stat_signature(after):
        raise ValueError("driver fileが検証中に変更されました")
    return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest(),
            "device": before.st_dev, "inode": before.st_ino, "size": before.st_size,
            "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns,
            "owner": before.st_uid, "mode": stat.S_IMODE(before.st_mode)}


def compute_driver_executable_binding():
    return _private_executable_binding(formal_base() / "drivers/p5_driver_v19.py", 0o700)


def compute_driver_config_binding():
    return _private_executable_binding(formal_base() / "drivers/p5-driver-v19-config.json", 0o600)


def compute_normal_shell_launcher_binding(path=None):
    """永続Cache配下の正本launcher identity。temporary wrapperには依存しない。"""
    return _private_executable_binding(path or formal_base() / "drivers/p5-v19-normal-shell.sh", 0o700)


def reject_platform_temp(path):
    """aliasのrealpathを含め、Darwinの固定scratch領域を正式rootに使わせない。"""
    path = Path(path)
    resolved = path.resolve(strict=False)
    if sys.platform == "darwin" and any(resolved == root.resolve() or resolved.is_relative_to(root.resolve())
                                       for root in PLATFORM_TEMP_ROOTS):
        raise ValueError("Darwin platform temp配下を正式実行rootには使えません")
    return resolved


def compute_codex_executable_binding(executable=None):
    """起動alias・固定実体・bytes/statを結合。同版の置換も別campaignにする。"""
    path = Path(executable) if executable is not None else CODEX_REAL_PATH
    launcher = CODEX_LAUNCH_PATH if path == CODEX_REAL_PATH else path
    before_launcher = launcher.lstat()
    resolved = launcher.resolve(strict=True)
    if resolved != path or not path.is_absolute():
        raise ValueError("Codex起動aliasの実体が固定pathから変わりました")
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_uid not in {0, os.getuid()} or before.st_mode & 0o022):
        raise ValueError("Codex実体は信頼ownerのregular single-link実行fileが必要です")
    signature = _stat_signature(before)
    key = (str(path), signature)
    if key not in _CLI_HASH_CACHE:
        _CLI_HASH_CACHE.clear()
        _CLI_HASH_CACHE[key] = hashlib.sha256(_read_regular_file(path)).hexdigest()
    # cache hitでも全componentをnofollowで検証する。
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
    finally:
        os.close(parent)
    if (_stat_signature(current) != signature or _stat_signature(launcher.lstat()) != _stat_signature(before_launcher)
            or launcher.resolve(strict=True) != path):
        raise ValueError("Codex実体/aliasが検証中に変わりました")
    return {"realpath": str(path), "sha256": _CLI_HASH_CACHE[key],
            "device": before.st_dev, "inode": before.st_ino, "size": before.st_size,
            "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns,
            "owner": before.st_uid, "mode": stat.S_IMODE(before.st_mode),
            "launcher": {"path": str(launcher), "device": before_launcher.st_dev,
                         "inode": before_launcher.st_ino, "mtime_ns": before_launcher.st_mtime_ns,
                         "ctime_ns": before_launcher.st_ctime_ns,
                         "target": os.readlink(launcher) if stat.S_ISLNK(before_launcher.st_mode) else None}}

# 従来batchの順序を維持し、このmodule自身を末尾へ追加する。
HARNESS_INPUTS = (
    "run.py", "batch.py", "sandbox_preflight.py", "analyze.py", "analysis_selftest.py", "driver.py", "callback_audit.py", "callback-api-inventory.json",
    "comparison-v2.json", "validate_c6.py", "../migration-baseline/comparison.json",
    "../migration-baseline/snapshot-index.json", "b-contract-index.json", "a-contract-index.json",
    "harness_fingerprint.py", "probe_v16.py", "fixed_test_runner_v16.py", "v16_selftest.py",
    "probe_v17.py", "fixed_test_runner_v17.py", "v17_selftest.py", "v18_selftest.py",
    "probe_v19.py", "v19_selftest.py",
)


def _read_regular_file(path):
    """構成要素のsymlink・fileのhardlink・読取中の変更を拒否する。"""
    path = Path(os.path.abspath(path))
    parent_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    file_fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("harness inputはregular single-link fileが必要です")
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        opened = os.fstat(file_fd)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("harness inputが読取開始時に変更されました")
        chunks = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(file_fd)
        current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                                   info.st_nlink, stat.S_IFMT(info.st_mode))
        if signature(opened) != signature(after) or signature(after) != signature(current) or after.st_nlink != 1:
            raise ValueError("harness inputが読取中に変更されました")
        return b"".join(chunks)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(parent_fd)


def _stat_signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _runtime_tree_manifest(root):
    """runtime全treeをnofollowで読み、内部symlinkのtargetも固定する。cacheは使わない。"""
    root = Path(os.path.abspath(root))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    ancestors = []
    try:
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            ancestors.append([part, info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)])
        root_info = os.fstat(fd)
        manifest = {}
        def walk(directory_fd, prefix):
            before = os.fstat(directory_fd)
            names = sorted(os.listdir(directory_fd))
            for name in names:
                relative = prefix + name
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                entry = {"mode": stat.S_IMODE(info.st_mode), "owner": info.st_uid}
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                    try:
                        if _stat_signature(info) != _stat_signature(os.fstat(child)):
                            raise ValueError("runtime directoryが読取開始時に変更されました")
                        manifest[relative] = {**entry, "type": "directory"}
                        walk(child, relative + "/")
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
                    try:
                        if _stat_signature(info) != _stat_signature(os.fstat(child)):
                            raise ValueError("runtime fileが読取開始時に変更されました")
                        digest = hashlib.sha256()
                        while True:
                            data = os.read(child, 1024 * 1024)
                            if not data:
                                break
                            digest.update(data)
                        if _stat_signature(info) != _stat_signature(os.fstat(child)):
                            raise ValueError("runtime fileが読取中に変更されました")
                        manifest[relative] = {**entry, "type": "file", "size": info.st_size, "sha256": digest.hexdigest()}
                    finally:
                        os.close(child)
                elif stat.S_ISLNK(info.st_mode):
                    target = os.readlink(name, dir_fd=directory_fd)
                    manifest[relative] = {**entry, "type": "symlink", "target": target}
                else:
                    raise ValueError("runtimeにhardlinkまたは非通常fileがあります")
                if _stat_signature(info) != _stat_signature(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)):
                    raise ValueError("runtime entryが読取中に変更されました")
            if names != sorted(os.listdir(directory_fd)) or _stat_signature(before) != _stat_signature(os.fstat(directory_fd)):
                raise ValueError("runtime directoryが読取中に変更されました")
        walk(fd, "")
        # symlinkはOSで辿らず、取得済みmanifest上で内部targetだけを解決する。
        for relative, entry in manifest.items():
            if entry["type"] != "symlink":
                continue
            pending, resolved, hops = relative.split("/"), [], 0
            while pending:
                part = pending.pop(0)
                if part in {"", "."}:
                    continue
                if part == "..":
                    if not resolved:
                        raise ValueError("runtime外へ出るsymlinkを拒否します")
                    resolved.pop()
                    continue
                candidate = "/".join([*resolved, part])
                target_entry = manifest.get(candidate)
                if target_entry is None:
                    raise ValueError("runtimeに壊れたsymlinkがあります")
                if target_entry["type"] == "symlink":
                    target = target_entry["target"]
                    hops += 1
                    if posixpath.isabs(target) or hops > 40:
                        raise ValueError("runtimeの絶対symlinkまたは循環symlinkを拒否します")
                    pending = target.split("/") + pending
                else:
                    if pending and target_entry["type"] != "directory":
                        raise ValueError("runtime symlinkの中間targetがdirectoryではありません")
                    resolved.append(part)
        # pathの付替えも拒否する。mtime等はtree変更検出に使い、ancestorの無関係更新は無視する。
        probe = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            observed = []
            for part in root.parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=probe)
                os.close(probe)
                probe = child
                info = os.fstat(probe)
                observed.append([part, info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)])
            if observed != ancestors or _stat_signature(root_info) != _stat_signature(os.fstat(probe)):
                raise ValueError("runtime rootまたは祖先が読取中に変更されました")
        finally:
            os.close(probe)
        return manifest, {"root_device": root_info.st_dev, "root_inode": root_info.st_ino,
                          "root_mode": stat.S_IMODE(root_info.st_mode), "ancestors": ancestors}
    finally:
        os.close(fd)


def compute_python_runtime_binding():
    """固定した実runtimeのidentity・全bytes・symlink・型を毎回再検証する。"""
    executable, root = Path(PYTHON_EXECUTABLE), PYTHON_RUNTIME_ROOT
    protected = [Path("/"), account_home(), account_home() / ".local", Path(__file__).absolute().parents[3],
                 formal_base(), Path(os.path.abspath(os.environ.get("CODEX_HOME") or str(account_home() / ".codex")))]
    if (sys.version_info[:3] != PYTHON_VERSION or sys.implementation.name != "cpython"
            or sys.implementation.cache_tag != "cpython-312" or platform.machine() != "arm64"
            or executable != root / "bin/python3.12"
            or any(path.is_relative_to(root) for path in protected)):
        raise ValueError("専用runtime directory内の固定CPython 3.12.13/arm64が必要です")
    manifest, identity = _runtime_tree_manifest(root)
    if (any(owner not in {0, os.getuid()} or mode & 0o022 for _, _, _, owner, mode in identity["ancestors"])
            or identity["ancestors"][-1][3] != os.getuid()
            or any(entry["owner"] != os.getuid() or (entry["type"] != "symlink" and entry["mode"] & 0o022)
                   for entry in manifest.values())):
        raise ValueError("runtimeと祖先には信頼したownerとgroup/world-writeなしを要求します")
    executable_entry = manifest.get("bin/python3.12", {})
    if executable_entry.get("type") != "file" or not executable_entry.get("mode", 0) & 0o111:
        raise ValueError("runtimeの実bin/python3.12が不正です")
    content = _read_regular_file(executable)
    if hashlib.sha256(content).hexdigest() != executable_entry["sha256"]:
        raise ValueError("runtime実行fileがmanifest取得後に変更されました")
    machine = platform.machine()
    cpu = {"arm64": 0x0100000C, "x86_64": 0x01000007}.get(machine)
    if (sys.platform != "darwin" or cpu is None or len(content) < 8
            or struct.unpack("<II", content[:8]) != (0xFEEDFACF, cpu)):
        raise ValueError("runtimeのMach-O architectureが実行中Pythonと一致しません")
    return {"schema": 1, "root_realpath": str(root), **identity,
            "executable_realpath": str(executable), "executable_sha256": executable_entry["sha256"],
            "python_version": list(sys.version_info[:3]), "architecture": machine,
            "implementation": sys.implementation.name, "cache_tag": sys.implementation.cache_tag,
            "manifest_entries": len(manifest),
            "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def compute_harness_fingerprint(here, *, python_runtime_binding=None, codex_executable_binding=None,
                                driver_executable_binding=None, normal_shell_launcher_binding=None):
    """benchmark directoryの現行固定入力から64桁SHA-256を返す。保存・実行はしない。"""
    here = Path(os.path.abspath(here))
    repository = here.parents[2]
    components = []
    for name in HARNESS_INPUTS:
        path = Path(os.path.abspath(here / name))
        label = str(path.relative_to(repository))
        components.append(label + ":" + hashlib.sha256(_read_regular_file(path)).hexdigest())
    runtime = compute_python_runtime_binding() if python_runtime_binding is None else python_runtime_binding
    components.append("python_runtime:" + json.dumps(runtime, sort_keys=True, separators=(",", ":")))
    codex = compute_codex_executable_binding() if codex_executable_binding is None else codex_executable_binding
    components.append("codex_executable:" + json.dumps(codex, sort_keys=True, separators=(",", ":")))
    driver = compute_driver_executable_binding() if driver_executable_binding is None else driver_executable_binding
    components.append("driver_executable:" + json.dumps(driver, sort_keys=True, separators=(",", ":")))
    launcher = (compute_normal_shell_launcher_binding() if normal_shell_launcher_binding is None
                else normal_shell_launcher_binding)
    components.append("normal_shell_launcher:" + json.dumps(launcher, sort_keys=True, separators=(",", ":")))
    components.append("actual_tool_environment_normalization:" + json.dumps(
        CODEX_TOOL_ENV_NORMALIZATION, sort_keys=True, separators=(",", ":")))
    # 実exec toolの/bin/zsh -lcが参照する固定OS層。説明に使う物をfingerprintから外さない。
    for shell_input in ("/bin/zsh", "/etc/zprofile", "/usr/libexec/path_helper", "/etc/paths"):
        components.append("login_shell:" + json.dumps(_shell_file_identity(shell_input), sort_keys=True,
                                                        separators=(",", ":")))
    for shell_input in ("/etc/zshenv", "/etc/zlogin"):
        target = Path(shell_input)
        components.append("login_shell_optional:" + json.dumps(_shell_file_identity(shell_input, optional=True),
                                                                 sort_keys=True, separators=(",", ":")))
    paths_d = Path("/etc/paths.d")
    paths_info = paths_d.lstat()
    components.append("login_shell_paths_d:" + json.dumps({"path": str(paths_d),
        "realpath": str(paths_d.resolve(strict=True)), "device": paths_info.st_dev, "inode": paths_info.st_ino,
        "owner": paths_info.st_uid, "mode": stat.S_IMODE(paths_info.st_mode), "size": paths_info.st_size,
        "mtime_ns": paths_info.st_mtime_ns, "ctime_ns": paths_info.st_ctime_ns,
        "entries": sorted(entry.name for entry in paths_d.iterdir())}, sort_keys=True, separators=(",", ":")))
    for target in sorted(paths_d.iterdir()) if paths_d.exists() else []:
        components.append("login_shell:" + json.dumps(_shell_file_identity(target), sort_keys=True,
                                                        separators=(",", ":")))
    components.append("fixed_sed:" + json.dumps(_shell_file_identity("/usr/bin/sed"), sort_keys=True,
                                                  separators=(",", ":")))
    return hashlib.sha256("".join(components).encode()).hexdigest()


def _shell_file_identity(value, optional=False):
    """login shellの実効性に関わるfile modeとinode metadataを固定する。"""
    target = Path(value)
    try:
        alias = target.lstat()
        resolved = target.resolve(strict=True)
        info = resolved.stat()
        return {"path": str(target), "realpath": str(resolved),
                "alias_identity": {"device": alias.st_dev, "inode": alias.st_ino, "owner": alias.st_uid,
                    "mode": stat.S_IMODE(alias.st_mode), "executable": bool(alias.st_mode & 0o111),
                    "size": alias.st_size, "mtime_ns": alias.st_mtime_ns, "ctime_ns": alias.st_ctime_ns,
                    "symlink_target": os.readlink(target) if stat.S_ISLNK(alias.st_mode) else None},
                "device": info.st_dev,
                "inode": info.st_ino, "owner": info.st_uid, "mode": stat.S_IMODE(info.st_mode),
                "executable": bool(info.st_mode & 0o111), "size": info.st_size,
                "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
                "sha256": hashlib.sha256(_read_regular_file(resolved)).hexdigest()}
    except FileNotFoundError:
        if optional:
            return {"path": str(target), "absent": True}
        raise
