#!/usr/bin/env python3
"""batch・再分類・集計が共用する、固定入力のharness fingerprint。"""

import hashlib
import os
from pathlib import Path
import stat

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


def compute_harness_fingerprint(here):
    """benchmark directoryの現行固定入力から64桁SHA-256を返す。保存・実行はしない。"""
    here = Path(os.path.abspath(here))
    repository = here.parents[2]
    components = []
    for name in HARNESS_INPUTS:
        path = Path(os.path.abspath(here / name))
        label = str(path.relative_to(repository))
        components.append(label + ":" + hashlib.sha256(_read_regular_file(path)).hexdigest())
    return hashlib.sha256("".join(components).encode()).hexdigest()
