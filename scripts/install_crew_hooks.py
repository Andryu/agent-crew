#!/usr/bin/env python3
"""共通manifestから設定差分を生成し、明示指定時だけ退避して適用する。"""

import argparse
import copy
from datetime import datetime, timezone
import difflib
import json
import hashlib
import os
from pathlib import Path
import shlex
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
# UserPromptSubmit は生成しないが、旧所有handlerを安全に除去するため認識する。
EVENTS = {"SessionStart", "UserPromptSubmit", "Stop", "SubagentStop", "TaskCompleted"}
MARKER = "crew-hooks:"
LEGACY_SHIMS = {
    "session_start": ("SessionStart", "0ab8e8aee1beabe5a353b624ce39797986e89a4c43b378744b2ba6f4e67a878e"),
    "subagent_stop": ("SubagentStop", "034f944f4ee6488f8753eca546452a7fb87d8ecab74944e687c78b86a14c28a7"),
    "task_completed": ("TaskCompleted", "0e3283c052b85b19e34841b01988b7fc6d68e857251509ebee02430f4a8a9f3b"),
}
# 移行前の実設定にあるcommandだけを所有対象とする。部分一致は禁止。
LEGACY_COMMANDS = frozenset({
    ".claude/hooks/task_completed.sh",
    ".claude/hooks/subagent_stop.sh",
    "scripts/enforce-queue-done-stop.sh || true",
    "bash -c 'cd \"$(git rev-parse --show-toplevel 2>/dev/null)\" && scripts/propose-lesson-rules.sh --dry-run 2>/dev/null || true'",
    "bash -c 'cd \"$(git rev-parse --show-toplevel 2>/dev/null)\" && bash scripts/privacy-check.sh 2>/dev/null || true'",
    "bash -c 'cd \"$(git rev-parse --show-toplevel 2>/dev/null)\" && scripts/enforce-retro-stop.sh || true'",
    "echo 'スプリント計画・レトロの前に必読: ~/Workspace/Obsidian/knowledge/agent-crew-failure-patterns.md（繰り返し失敗パターン）と ~/Workspace/Obsidian/decisions/agent-crew-adr-index.md（ADR索引）'",
    "bash -c 'cd \"$(git rev-parse --show-toplevel 2>/dev/null || pwd)\" && bash .claude/hooks/session_start.sh'",
    "bash -c 'cd \"$(git rev-parse --show-toplevel 2>/dev/null || pwd)\" && bash scripts/model-mode.sh'",
})


def hook_command(runtime: str, event: str) -> str:
    if runtime == "claude":
        return f'python3 "$CLAUDE_PROJECT_DIR/scripts/crew_hooks.py" --runtime claude --event {event} --root "$CLAUDE_PROJECT_DIR"'
    return f'root=$(git rev-parse --show-toplevel) && python3 "$root/scripts/crew_hooks.py" --runtime codex --event {event} --root "$root"'


def generated_hooks(root: Path, runtime: str) -> dict:
    """指定rootのmanifestを読み、runtimeのhooksマッピングを返す。"""
    manifest = json.loads((Path(root) / "config/crew-hooks.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("未対応のmanifest schema_versionです")
    if runtime not in {"claude", "codex"}:
        raise ValueError(f"未対応のruntimeです: {runtime}")
    events = manifest["runtimes"][runtime]["events"]
    if not isinstance(events, list) or any(not isinstance(e, str) or e not in EVENTS for e in events):
        raise ValueError("manifestのeventsが不正です")
    if (len(events) != len(set(events)) or "UserPromptSubmit" in events
            or (runtime == "codex" and "TaskCompleted" in events)):
        raise ValueError("manifestに重複またはruntime未対応イベントがあります")
    result = {}
    for event in events:
        result[event] = [{"hooks": [{
            "statusMessage": f"{MARKER}{runtime}:{event}",
            "type": "command", "command": hook_command(runtime, event), "timeout": 15,
        }]}]
    return result


def is_owned(handler: dict, runtime: str, event: str) -> bool:
    if handler.get("type") != "command":
        return False
    generated = (
        event in EVENTS
        and handler.get("statusMessage") == f"{MARKER}{runtime}:{event}"
        and handler.get("command") == hook_command(runtime, event)
    )
    return generated or (
        runtime == "claude" and handler.get("command") in LEGACY_COMMANDS
    )


def merge_settings(existing: dict, generated: dict, runtime: str) -> dict:
    """所有handlerだけを除去し、未知の設定・group・handlerを保持する。"""
    merged = copy.deepcopy(existing)
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("既存設定のhooksがobjectではありません")
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            raise ValueError(f"既存設定の{event}が配列ではありません")
        retained = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"既存設定の{event} groupが不正です")
            original = group["hooks"]
            if any(not isinstance(h, dict) for h in original):
                raise ValueError(f"既存設定の{event} handlerが不正です")
            group["hooks"] = [h for h in original if not is_owned(h, runtime, event)]
            # 元から空のgroup、未知のメタデータも保持する。
            if group["hooks"] or not original or set(group) - {"hooks", "matcher"}:
                retained.append(group)
        if retained or not groups:
            hooks[event] = retained
        else:
            hooks.pop(event)
    for event, groups in generated.items():
        hooks[event] = copy.deepcopy(groups) + hooks.get(event, [])
    return merged


def snapshot(path: Path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def generated_shim(runtime, event):
    return ('#!/bin/sh\n# 共通coreへの互換入口。生成元: scripts/install_crew_hooks.py\n'
            'root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 1\n'
            f'exec python3 "$root/scripts/crew_hooks.py" --runtime {runtime} --event {event} --root "$root"\n')


def verify_snapshot(path: Path, expected):
    if snapshot(path) != expected:
        raise ValueError(f"生成後に設定が変更されました（適用中止）: {path}")


def atomic_write(path: Path, content: str, expected):
    """同一directoryの一時ファイルを、再照合直後に置換する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".crew-hooks-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if expected is not None:
            temporary.chmod(path.stat().st_mode & 0o777)
        verify_snapshot(path, expected)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    pending = []
    backup = None
    try:
        for runtime, relative in (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json")):
            path = root / relative
            before = snapshot(path)
            old = before.decode("utf-8") if before is not None else ""
            existing = json.loads(old) if old else {}
            if not isinstance(existing, dict):
                raise ValueError(f"{relative}がobjectではありません")
            result = merge_settings(existing, generated_hooks(root, runtime), runtime)
            # 意味的に一致していれば整形だけの変更はしない。
            if result == existing:
                continue
            new = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            pending.append((path, relative, new, before))
            sys.stdout.writelines(difflib.unified_diff(
                old.splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile=relative, tofile=relative + " (generated)",
            ))
        for runtime in ("claude", "codex"):
            for name, (event, legacy_hash) in LEGACY_SHIMS.items():
                relative = f".{runtime}/hooks/{name}.sh"
                path = root / relative
                before = snapshot(path)
                new = generated_shim(runtime, event)
                if before == new.encode():
                    continue
                if before is not None and hashlib.sha256(before).hexdigest() != legacy_hash:
                    raise ValueError(f"独自変更のある互換入口を上書きしません: {relative}")
                pending.append((path, relative, new, before))
                print(f"互換入口を共通coreへ変更: {relative}")
        if args.apply and pending:
            for path, _, _, before in pending:
                verify_snapshot(path, before)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = root / "docs/codex-direct/backups" / f"shared-{stamp}"
            backup.mkdir(parents=True, exist_ok=False)
            # 両設定を検証し、全既存ファイルを退避してから適用する。
            for path, relative, _, before in pending:
                if before is not None:
                    dest = backup / relative
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(before)
            for path, _, new, before in pending:
                atomic_write(path, new, before)
                if path.suffix == ".sh":
                    path.chmod(0o755)
            print(f"バックアップ: {backup}", file=sys.stderr)
        return 1 if args.check and pending else 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"hook設定生成に失敗: {error}", file=sys.stderr)
        if backup is not None:
            print(f"退避先: {backup}。適用済み設定は自動で戻しません。現在の設定と退避内容を確認してください。", file=sys.stderr)
        if args.apply:
            command = f"python3 {shlex.quote(str(Path(__file__).resolve()))} --root {shlex.quote(str(root))}"
            print(f"再実行: {command} --check で差分を確認し、競合を解消後に {command} --apply", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
