#!/usr/bin/env python3
"""C6の合成fixtureだけを読み、モデルが行った進捗更新を採点する。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message):
    print(json.dumps({"ok": False, "reason": message}, ensure_ascii=False))
    raise SystemExit(1)


def checked(root, relative):
    path = root / relative
    try:
        if os.path.islink(root) or not root.is_dir():
            fail("C6 fixture rootが不正です")
    except OSError:
        fail("C6 fixture rootが不正です")
    current = root
    for part in Path(relative).parts:
        current = current / part
        try:
            if os.path.islink(current):
                fail("C6入力にsymlinkまたは不正な構成要素があります")
        except OSError:
            fail("C6入力がありません")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        fail("C6入力がfixture外を参照します")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-before-sha256", required=True)
    parser.add_argument("--progress-sha256", required=True)
    parser.add_argument("--readme-sha256", required=True)
    args = parser.parse_args()
    root = Path.cwd()
    state = checked(root, "migration-progress/state.json")
    program = checked(root, "migration-progress/progress.py")
    readme = checked(root, "migration-progress/README.md")
    queue = root / ".claude/_queue.json"
    if queue.exists():
        fail("C6 fixtureでqueueを変更しました")
    if not state.is_file() or not program.is_file():
        fail("C6入力がありません")
    if digest(program) != args.progress_sha256 or digest(readme) != args.readme_sha256:
        fail("C6のread-only入力が変更されています")
    if digest(state) == args.state_before_sha256:
        fail("合成state.jsonが更新されていません")
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
        p0 = data["tasks"]["P0"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        fail("合成state.jsonが不正です")
    if p0.get("status") != "検証中":
        fail("P0が検証中ではありません")
    if data.get("schema") != 1 or set(data.get("tasks", {})) != {f"P{number}" for number in range(8)}:
        fail("合成state.jsonのschemaまたはタスク構造が変わりました")
    shown = subprocess.run([sys.executable, "-B", str(program), "--once"], cwd=root,
                           capture_output=True, text=True)
    if shown.returncode != 0 or "P0 [検証中]" not in shown.stdout:
        fail("合成state.jsonをCLIで再読込できません")
    print(json.dumps({"ok": True, "state_changed": True, "p0_status": p0["status"],
                      "reload_exit_code": shown.returncode, "state_sha256": digest(state)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
