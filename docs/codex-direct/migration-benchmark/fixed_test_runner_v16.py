#!/usr/bin/env python3
"""初期test bytesを開いたFDから実行する。変更対象codeは未信頼。"""

import hashlib
import os
from pathlib import Path
import stat
import sys
import types
import unittest

TESTS = {
    "C1": ("test_crew_launcher.py", "98295b6adaffea2f589dd4031a25c0a478c0d8f035fd819ce9a6545b613b09fd"),
    "C2": ("test_install_crew_hooks.py", "ebfbf375fe59da8324c7ac20bbd3420672e90febeb29eff220c7f8ab7bd56a80"),
    "C3": ("test_codex_hook_state.py", "104ffefccf7ac950b125eb680ee70a128f1f0868e341c3f3af528162c0924d9a"),
    "C5": ("test_operational_readiness.py", "c722b654fb284f9e36ec9523f69f7625af0e6455b4530cffa8c619a3c16a422c"),
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in TESTS or sys.flags.isolated != 1 or sys.dont_write_bytecode is not True:
        raise SystemExit("P5_RUNNER_ARGS_INVALID")
    name, expected = TESTS[sys.argv[1]]
    root = Path.cwd()
    directory = root / ".p5-fixed-tests"
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise SystemExit("P5_TEST_ASSET_INVALID")
            data = bytearray()
            while chunk := os.read(fd, 65536):
                data.extend(chunk)
            after = os.fstat(fd)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if signature(before) != signature(after) or signature(after) != signature(current):
                raise SystemExit("P5_TEST_ASSET_CHANGED")
            if hashlib.sha256(data).hexdigest() != expected:
                raise SystemExit("P5_TEST_ASSET_HASH")
            # compileに渡すbytesは上のFDから読んだ同一bytes。
            module = types.ModuleType("p5_fixed_test")
            module.__file__ = str(root / "tests" / name)
            module.__package__ = ""
            sys.modules[module.__name__] = module
            exec(compile(bytes(data), module.__file__, "exec"), module.__dict__)
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            raise SystemExit(0 if result.wasSuccessful() else 1)
        finally:
            os.close(fd)
    finally:
        os.close(parent)


if __name__ == "__main__":
    main()
