"""機械ローカル信頼設定の限定と競合拒否を検証する。"""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import codex_hook_state as state


class HookStateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="state test ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.home = self.root / "home"
        (self.root / "config").mkdir()
        shutil.copyfile(REPO / "config/crew-hooks.json", self.root / "config/crew-hooks.json")
        self.hooks = []
        for event, groups in state.generated_hooks(self.root, "codex").items():
            path = str(self.root / ".codex/hooks.json")
            self.hooks.append({"key": f"{path}:{state.snake(event)}:0:0", "eventName": state.EVENTS[event],
                               "source": "project", "sourcePath": path, "handlerType": "command", "isManaged": False,
                               "command": groups[0]["hooks"][0]["command"], "currentHash": "sha256:" + "a" * 64})
        self.snapshot = self.root / "snapshot.json"

    def document(self):
        return {"result": {"data": [{"cwd": str(self.root), "hooks": self.hooks, "errors": []}]}}

    def user_hook(self, command, index=0):
        path = str(self.home / ".codex/hooks.json")
        return {"key": f"{path}:stop:{index}:0", "eventName": "stop", "source": "user", "sourcePath": path,
                "command": command, "handlerType": "command", "isManaged": False}

    def run_main(self, *args):
        self.snapshot.write_text(json.dumps(self.document()))
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(state.Path, "home", return_value=self.home), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = state.main(["--root", str(self.root), "--snapshot", str(self.snapshot), *args])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_apply_and_repeat_preserves_observed_hash(self):
        self.assertEqual(self.run_main("--check")[0], 1)
        self.assertFalse((self.root / ".codex/config.toml").exists())
        self.assertEqual(self.run_main("--apply")[0], 0)
        config = (self.root / ".codex/config.toml").read_text()
        self.assertTrue(config.startswith(state.HEADER))
        self.assertIn("notify = []", config)
        self.assertIn("[features]\nhooks = true", config)
        self.assertEqual(config.count("trusted_hash ="), 4)
        self.assertIn("sha256:" + "a" * 64, config)
        self.assertEqual(self.run_main("--check")[0], 0)
        self.assertEqual(self.run_main("--apply")[1], "")

    def test_launch_uses_inline_table_and_checks_user_order(self):
        command = f"'{self.home}/.codex/hooks/cmux-notify.sh'"
        self.hooks.append(self.user_hook(command))
        self.assertEqual(self.run_main("--apply")[0], 0)
        user_file = self.home / ".codex/hooks.json"
        user_file.parent.mkdir(parents=True)
        user_file.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command": command}]}]}}))
        with mock.patch.object(state.Path, "home", return_value=self.home):
            args = state.launch_overrides(self.root)
            self.assertEqual(args[:4], ["-c", "notify=[]", "-c", "features.hooks=true"])
            self.assertTrue(args[-1].startswith("hooks.state={"))
            self.assertIn(json.dumps(self.hooks[-1]["key"]) + "={enabled=false}", args[-1])
            self.assertEqual(args[-1].count("trusted_hash="), 4)
            user_file.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command": "different"}]}]}}))
            with self.assertRaisesRegex(ValueError, "構成変更"):
                state.launch_overrides(self.root)

    def test_nondefault_codex_home_refuses(self):
        with self.assertRaisesRegex(ValueError, "既定CODEX_HOME専用"):
            state.launch_overrides(self.root, {"CODEX_HOME": str(self.root / "other")})

    def test_launch_without_local_state_refuses(self):
        with self.assertRaisesRegex(ValueError, "未設定"):
            state.launch_overrides(self.root)

    def test_false_trust_claims_are_rejected(self):
        original = copy.deepcopy(self.hooks)
        changes = ({"source": "user"}, {"sourcePath": "/tmp/other.json"}, {"key": "fake"},
                   {"command": "echo injected"}, {"eventName": "stop"}, {"currentHash": "guess"},
                   {"isManaged": True}, {"handlerType": "prompt"})
        for change in changes:
            with self.subTest(change=change):
                self.hooks = copy.deepcopy(original)
                self.hooks[0].update(change)
                self.assertEqual(self.run_main("--apply")[0], 2)
                self.assertFalse((self.root / ".codex/config.toml").exists())
        for extra in ({**original[0]}, {**original[0], "key": "unknown-project-key"}):
            self.hooks = copy.deepcopy(original) + [extra]
            self.assertEqual(self.run_main("--check")[0], 2)

    def test_user_allowlist_only_and_index_change(self):
        disabled = f"'{self.home}/.codex/hooks/cmux-notify.sh'"
        self.hooks.extend([self.user_hook(disabled), self.user_hook(disabled + " --custom", 1),
                           self.user_hook(f"'{self.home}/.codex/hooks/cmux-progress.sh'", 2)])
        result, _, stderr = self.run_main("--apply")
        self.assertEqual(result, 0)
        self.assertIn("警告", stderr)
        self.assertNotIn("cmux", stderr)
        config = self.root / ".codex/config.toml"
        self.assertEqual(config.read_text().count("enabled = false"), 1)
        self.assertNotIn(":stop:1:0", config.read_text())
        old = config.read_bytes()
        self.hooks[4]["key"] = f"{self.home}/.codex/hooks.json:stop:8:0"
        self.assertEqual(self.run_main("--apply")[0], 0)
        self.assertIn(":stop:8:0", config.read_text())
        backups = list((self.root / "docs/codex-direct/backups").glob("shared-state-*/.codex/config.toml"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), old)

    def test_unknown_existing_config_and_manual_changes_are_rejected(self):
        config = self.root / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text('model = "custom"\n')
        self.assertEqual(self.run_main("--apply")[0], 2)
        self.assertEqual(config.read_text(), 'model = "custom"\n')
        config.unlink()
        self.assertEqual(self.run_main("--apply")[0], 0)
        changed = config.read_text() + "# 手編集\n"
        config.write_text(changed)
        self.assertEqual(self.run_main("--apply")[0], 2)
        self.assertEqual(config.read_text(), changed)

    def test_unknown_source_and_managed_user_are_not_trusted(self):
        self.hooks.extend([{**self.user_hook("private", 0), "source": "plugin"},
                           {**self.user_hook(next(iter(state.disabled_commands(self.home))), 1), "isManaged": True}])
        states, _ = state.selected_states(self.document(), self.root, self.home)
        self.assertEqual(len(states), 4)


if __name__ == "__main__":
    unittest.main()
