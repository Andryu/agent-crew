#!/usr/bin/env python3
"""batch・再分類・集計が共用する、固定入力のharness fingerprint。"""

import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import stat
import struct
import sys

PYTHON_EXECUTABLE = str(Path(sys.executable).resolve(strict=True))
PYTHON_RUNTIME_ROOT = Path(sys.base_prefix).resolve(strict=True)
PYTHON_VERSION = (3, 12, 13)

# 従来batchの順序を維持し、このmodule自身を末尾へ追加する。
HARNESS_INPUTS = (
    "run.py", "batch.py", "sandbox_preflight.py", "analyze.py", "analysis_selftest.py",
    "comparison-v2.json", "validate_c6.py", "../migration-baseline/comparison.json",
    "../migration-baseline/snapshot-index.json", "b-contract-index.json", "a-contract-index.json",
    "harness_fingerprint.py",
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
    protected = [Path("/"), Path.home(), Path.home() / ".local", Path(__file__).absolute().parents[3],
                 Path("/private/tmp/agent-crew-p5-benchmark/formal"),
                 Path(os.path.abspath(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")))]
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


def compute_harness_fingerprint(here, *, python_runtime_binding=None):
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
    return hashlib.sha256("".join(components).encode()).hexdigest()
