"""共通原本から生成するCodex hookのイベントと実行入口を検証する。"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "codex_hook_installer", REPO_DIR / "scripts/install_crew_hooks.py"
)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def load_commands() -> list[str]:
    hooks = installer.generated_hooks(REPO_DIR, "codex")
    return [handler["command"] for groups in hooks.values() for group in groups for handler in group["hooks"]]


class CodexHooksTests(unittest.TestCase):
    def test_hooks_use_supported_events_and_command_handlers(self):
        hooks = installer.generated_hooks(REPO_DIR, "codex")
        self.assertEqual(set(hooks), {"SessionStart", "Stop", "SubagentStop"})
        self.assertTrue(all(handler["type"] == "command" for groups in hooks.values()
                            for group in groups for handler in group["hooks"]))

    def test_commands_resolve_from_git_root_without_claude_project_dir(self):
        for command in load_commands():
            self.assertIn("git rev-parse --show-toplevel", command)
            self.assertNotIn("CLAUDE_PROJECT_DIR", command)

    def test_commands_run_from_subdirectory_without_claude_project_dir(self):
        with tempfile.TemporaryDirectory(prefix="codex-hook-entry-") as directory:
            root = Path(directory).resolve()
            script = root / "scripts/crew_hooks.py"
            script.parent.mkdir()
            # 実hookを起動せず、生成commandが渡すruntime/event/rootをfixtureで検査する。
            script.write_text(
                "import argparse\nfrom pathlib import Path\n"
                "parser = argparse.ArgumentParser()\n"
                "parser.add_argument('--runtime')\nparser.add_argument('--event')\n"
                "parser.add_argument('--root')\nargs = parser.parse_args()\n"
                "assert args.runtime == 'codex'\n"
                "assert Path(args.root) == Path(__file__).resolve().parents[1]\n"
                "print(args.event)\n"
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            nested = root / "docs/nested"
            nested.mkdir(parents=True)
            environment = {key: value for key, value in os.environ.items()
                           if key not in {"CLAUDE_PROJECT_DIR", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}}
            events = []
            for command in load_commands():
                result = subprocess.run(["bash", "-c", command], cwd=nested, env=environment,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                events.append(result.stdout.strip())
            self.assertEqual(events, ["SessionStart", "Stop", "SubagentStop"])


if __name__ == "__main__":
    unittest.main()
