"""Codex用hook設定の回帰テスト。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent
HOOKS_PATH = REPO_DIR / ".codex" / "hooks.json"


def load_commands() -> list[str]:
    hooks = json.loads(HOOKS_PATH.read_text())
    return [handler["command"] for groups in hooks["hooks"].values() for group in groups for handler in group["hooks"]]


def test_hooks_use_supported_events_and_command_handlers():
    hooks = json.loads(HOOKS_PATH.read_text())
    assert set(hooks["hooks"]) == {"SessionStart", "UserPromptSubmit", "Stop"}
    assert all(handler["type"] == "command" for groups in hooks["hooks"].values() for group in groups for handler in group["hooks"])


def test_commands_resolve_from_git_root_without_claude_project_dir():
    for command in load_commands():
        assert "git rev-parse --show-toplevel" in command
        assert "CLAUDE_PROJECT_DIR" not in command


def test_commands_run_from_subdirectory_without_claude_project_dir(tmp_path: Path):
    for relative_path in [".claude/hooks/session_start.sh", "scripts/model-mode.sh", "scripts/propose-lesson-rules.sh", "scripts/privacy-check.sh", "scripts/enforce-retro-stop.sh"]:
        script = tmp_path / relative_path
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/usr/bin/env bash\nexit 0\n")
        script.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    nested_dir = tmp_path / "docs" / "nested"
    nested_dir.mkdir(parents=True)
    environment = {key: value for key, value in os.environ.items() if key != "CLAUDE_PROJECT_DIR"}
    for command in load_commands():
        result = subprocess.run(["bash", "-c", command], cwd=nested_dir, env=environment, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
