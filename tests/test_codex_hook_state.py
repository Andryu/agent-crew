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
        self.assertNotIn("notify", state.Document(config).data)
        self.assertIn("hooks = true", config)
        self.assertEqual(config.count("trusted_hash ="), 3)
        self.assertIn("sha256:" + "a" * 64, config)
        self.assertEqual(json.loads((self.root / "docs/codex-direct/local-hook-state.json").read_text())["schema_version"], 2)
        self.assertEqual(self.run_main("--check")[0], 0)
        self.assertEqual(self.run_main("--apply")[1], "")

    def test_launch_uses_inline_table_and_checks_user_order(self):
        command = f"'{self.home}/.codex/hooks/cmux-notify.sh'"
        self.hooks.append(self.user_hook(command))
        self.assertEqual(self.run_main("--apply")[0], 0)
        user_file = self.home / ".codex/hooks.json"
        user_file.parent.mkdir(parents=True, exist_ok=True)
        user_file.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command": command}]}]}}))
        with mock.patch.object(state.Path, "home", return_value=self.home):
            args = state.launch_overrides(self.root)
            self.assertEqual(args[:4], ["-c", "notify=[]", "-c", "features.hooks=true"])
            self.assertTrue(args[-1].startswith("hooks.state={"))
            self.assertIn(json.dumps(self.hooks[-1]["key"]) + "={enabled=false}", args[-1])
            self.assertEqual(args[-1].count("trusted_hash="), 3)
            user_file.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command": "different"}]}]}}))
            with self.assertRaisesRegex(ValueError, "構成変更"):
                state.launch_overrides(self.root)

    def test_project_only_snapshot_launch_without_user_hooks_file(self):
        self.assertEqual(self.run_main("--apply")[0], 0)
        self.assertFalse((self.home / ".codex/hooks.json").exists())
        with mock.patch.object(state.Path, "home", return_value=self.home):
            args = state.launch_overrides(self.root)
        self.assertEqual(args[:4], ["-c", "notify=[]", "-c", "features.hooks=true"])
        self.assertEqual(args[-1].count("trusted_hash="), 3)

    def test_managed_symlinks_refused_before_backup_in_all_modes(self):
        for relative in (".codex/config.toml", "docs/codex-direct/local-hook-state.json"):
            with self.subTest(relative=relative):
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                real = self.root / ("real-" + path.name)
                real.write_text('model = "fixture"\n' if path.name == "config.toml" else "{}")
                original = real.read_bytes()
                path.symlink_to(real)
                try:
                    for mode in ("--check", "--apply", "--recover", "--rollback"):
                        with self.subTest(mode=mode):
                            self.assertEqual(self.run_main(mode)[0], 2)
                            self.assertTrue(path.is_symlink())
                            self.assertEqual(real.read_bytes(), original)
                            self.assertFalse((self.home / ".codex/config-composer").exists())
                    with mock.patch.object(state.Path, "home", return_value=self.home):
                        with self.assertRaisesRegex(ValueError, "symlink"):
                            state.launch_overrides(self.root)
                finally:
                    path.unlink()

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

    def test_old_project_prompt_registration_is_rejected_until_installer_update(self):
        path = str(self.root / ".codex/hooks.json")
        old = {"key": path + ":user_prompt_submit:0:0", "eventName": "userPromptSubmit",
               "source": "project", "sourcePath": path, "handlerType": "command", "isManaged": False,
               "command": 'root=$(git rev-parse --show-toplevel) && python3 "$root/scripts/crew_hooks.py" '
                          '--runtime codex --event UserPromptSubmit --root "$root"',
               "currentHash": "sha256:" + "a" * 64}
        self.hooks.append(old)
        self.assertEqual(self.run_main("--apply")[0], 2)
        self.assertFalse((self.root / ".codex/config.toml").exists())

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
        self.hooks[3]["key"] = f"{self.home}/.codex/hooks.json:stop:8:0"
        self.assertEqual(self.run_main("--apply")[0], 0)
        self.assertIn(":stop:8:0", config.read_text())
        backups = list((self.home / ".codex/config-composer/backups").glob("hook-*/config.toml"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), old)

    def test_unknown_existing_config_preserved_and_hook_changes_rejected(self):
        config = self.root / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text('model = "custom"\n')
        self.assertEqual(self.run_main("--apply")[0], 0)
        self.assertIn('model = "custom"', config.read_text())
        changed = 'notify = ["custom"]\n' + config.read_text()
        config.write_text(changed)
        self.assertEqual(self.run_main("--apply")[0], 2)
        self.assertEqual(config.read_text(), changed)

    def test_unknown_source_and_managed_user_are_not_trusted(self):
        self.hooks.extend([{**self.user_hook("private", 0), "source": "plugin"},
                           {**self.user_hook(next(iter(state.disabled_commands(self.home))), 1), "isManaged": True}])
        states, _ = state.selected_states(self.document(), self.root, self.home)
        self.assertEqual(len(states), 3)

    def test_schema1_valid_migrates_but_tamper_refused(self):
        key = str(self.root / ".codex/hooks.json") + ":user_prompt_submit:0:0"
        old_states = [{"source": "project", "sourcePath": str(self.root / ".codex/hooks.json"),
                       "key": key, "command": "legacy", "enabled": True,
                       "trusted_hash": "sha256:" + "b" * 64}]
        old_states += state.selected_states(self.document(), self.root, self.home)[0]
        config = self.root / ".codex/config.toml"
        sidecar = self.root / "docs/codex-direct/local-hook-state.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        content = state.render_config(old_states, legacy_notify=True)
        config.write_text(content)
        sidecar.write_text(json.dumps({"schema_version": 1, "root": str(self.root),
                                       "generated_config_hash": state.digest(content.encode()), "states": old_states}))
        self.assertEqual(self.run_main("--apply")[0], 0)
        self.assertNotIn(key, config.read_text())
        self.assertEqual(json.loads(sidecar.read_text())["schema_version"], 2)
        config.write_text("notify = [1]\n" + config.read_text())
        self.assertEqual(self.run_main("--apply")[0], 2)
        config.write_text(config.read_text().removeprefix("notify = [1]\n"))
        self.assertEqual(self.run_main("--rollback")[0], 0)
        rolled = json.loads(sidecar.read_text())
        self.assertEqual(rolled["schema_version"], 2)
        self.assertTrue(rolled["requires_fresh_snapshot"])
        with mock.patch.object(state.Path, "home", return_value=self.home):
            with self.assertRaisesRegex(ValueError, "新しい実機snapshot"):
                state.launch_overrides(self.root)
        self.assertEqual(self.run_main("--apply")[0], 0)
        self.assertFalse(json.loads(sidecar.read_text()).get("requires_fresh_snapshot", False))

    def test_schema1_new_user_key_recovers_at_both_write_boundaries(self):
        old_states = state.selected_states(self.document(), self.root, self.home)[0]
        config = self.root / ".codex/config.toml"
        sidecar = self.root / "docs/codex-direct/local-hook-state.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        old_config = state.render_config(old_states, legacy_notify=True)
        old_sidecar = json.dumps({"schema_version": 1, "root": str(self.root),
                                  "generated_config_hash": state.digest(old_config.encode()),
                                  "states": old_states})
        command = f"'{self.home}/.codex/hooks/cmux-notify.sh'"
        self.hooks.append(self.user_hook(command, index=9))
        new_key = self.hooks[-1]["key"]
        for failure_call, expected in ((2, "not_applied"), (3, "applied")):
            with self.subTest(failure_call=failure_call):
                config.write_text(old_config)
                sidecar.write_text(old_sidecar)
                actual_write = state.compose_write
                calls = 0

                def interrupted(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == failure_call:
                        raise OSError("fixture中断")
                    return actual_write(*args, **kwargs)

                with mock.patch.object(state, "compose_write", side_effect=interrupted):
                    self.assertEqual(self.run_main("--apply")[0], 2)
                pending = json.loads(sidecar.read_text())
                self.assertEqual(pending["status"], "pending")
                self.assertIn(new_key, pending["owned_before"]["entries"])
                self.assertIsNone(pending["owned_before"]["entries"][new_key])
                result, stdout, _ = self.run_main("--recover")
                self.assertEqual(result, 0)
                self.assertIn(expected, stdout)
                if failure_call == 2:
                    self.assertEqual(config.read_text(), old_config)
                    self.assertEqual(json.loads(sidecar.read_text())["schema_version"], 1)
                else:
                    self.assertIn(new_key, config.read_text())
                    self.assertEqual(json.loads(sidecar.read_text())["status"], "applied")

    def seed_legacy_schema2(self):
        self.assertEqual(self.run_main("--apply")[0], 0)
        config = self.root / ".codex/config.toml"
        sidecar = self.root / "docs/codex-direct/local-hook-state.json"
        config.write_text('notify = [] # 管理済み\n' + config.read_text())
        record = json.loads(sidecar.read_text())
        record["owned_after"]["notify"] = []
        record["owned_before"]["notify"] = None
        record["before_fragments"]["notify"] = None
        sidecar.write_text(json.dumps(record))
        return config, sidecar

    def test_schema2_notify_migration_is_idempotent_and_reversible(self):
        config, sidecar = self.seed_legacy_schema2()
        old_config, old_sidecar = config.read_bytes(), sidecar.read_bytes()
        self.assertEqual(self.run_main("--check")[0], 1)
        self.assertEqual(config.read_bytes(), old_config)
        self.assertEqual(self.run_main("--apply")[0], 0)
        self.assertNotIn("notify", state.Document(config.read_text()).data)
        record = json.loads(sidecar.read_text())
        self.assertNotIn("notify", record["owned_after"])
        self.assertEqual(record["owned_before"]["notify"], [])
        after = config.read_bytes(), sidecar.read_bytes()
        self.assertEqual(self.run_main("--check")[0], 0)
        self.assertEqual(self.run_main("--apply")[0], 0)
        self.assertEqual((config.read_bytes(), sidecar.read_bytes()), after)
        self.assertEqual(self.run_main("--rollback")[0], 0)
        self.assertEqual(state.Document(config.read_text()).data, state.Document(old_config.decode()).data)
        self.assertEqual(sidecar.read_bytes(), old_sidecar)
        self.assertEqual(self.run_main("--apply")[0], 0)

    def test_schema2_notify_migration_recovers_apply_and_rollback_boundaries(self):
        config, sidecar = self.seed_legacy_schema2()
        old_config, old_sidecar = config.read_bytes(), sidecar.read_bytes()
        for mode in ("--apply", "--rollback"):
            for failure_call in (2, 3):
                with self.subTest(mode=mode, failure_call=failure_call):
                    config.write_bytes(old_config)
                    sidecar.write_bytes(old_sidecar)
                    if mode == "--rollback":
                        self.assertEqual(self.run_main("--apply")[0], 0)
                    actual_write = state.compose_write
                    calls = 0

                    def interrupted(*args, **kwargs):
                        nonlocal calls
                        calls += 1
                        if calls == failure_call:
                            raise OSError("fixture中断")
                        return actual_write(*args, **kwargs)

                    with mock.patch.object(state, "compose_write", side_effect=interrupted):
                        self.assertEqual(self.run_main(mode)[0], 2)
                    expected = {("--apply", 2): "not_applied", ("--apply", 3): "applied",
                                ("--rollback", 2): "rollback_not_applied", ("--rollback", 3): "rolled_back"}
                    result, stdout, stderr = self.run_main("--recover")
                    self.assertEqual(result, 0, stderr)
                    self.assertEqual(stdout.strip(), expected[(mode, failure_call)])
                    legacy = (mode == "--apply" and failure_call == 2) or (mode == "--rollback" and failure_call == 3)
                    self.assertEqual("notify" in state.Document(config.read_text()).data, legacy)
                    self.assertEqual("notify" in json.loads(sidecar.read_text())["owned_after"], legacy)

    def test_schema2_notify_tamper_and_ledger_mismatch_preserve_bytes(self):
        config, sidecar = self.seed_legacy_schema2()
        baseline_config, baseline_record = config.read_text(), json.loads(sidecar.read_text())
        for config_notify, ledger_notify in ((None, []), ('["custom"]', []),
                                             ('["custom"]', ["custom"]), ('[]', None)):
            with self.subTest(config_notify=config_notify, ledger_notify=ledger_notify):
                text = baseline_config.split('\n', 1)[1]
                if config_notify is not None:
                    text = 'notify = ' + config_notify + '\n' + text
                record = copy.deepcopy(baseline_record)
                if ledger_notify is None:
                    record["owned_after"].pop("notify")
                else:
                    record["owned_after"]["notify"] = ledger_notify
                config.write_text(text)
                sidecar.write_text(json.dumps(record))
                before = config.read_bytes(), sidecar.read_bytes()
                self.assertEqual(self.run_main("--apply")[0], 2)
                self.assertEqual((config.read_bytes(), sidecar.read_bytes()), before)

    def test_schema2_pending_recovery_and_section_rollback(self):
        config = self.root / ".codex/config.toml"
        config.parent.mkdir(parents=True)
        config.write_text('model = "fixture"\n')
        self.assertEqual(self.run_main("--apply")[0], 0)
        sidecar = self.root / "docs/codex-direct/local-hook-state.json"
        record = json.loads(sidecar.read_text())
        record["status"] = "pending"
        sidecar.write_text(json.dumps(record))
        self.assertEqual(self.run_main("--recover")[0], 0)
        self.assertEqual(json.loads(sidecar.read_text())["status"], "applied")
        record = json.loads(sidecar.read_text())
        record["status"] = "rollback_pending"
        sidecar.write_text(json.dumps(record))
        self.assertEqual(self.run_main("--recover")[0], 0)
        self.assertEqual(json.loads(sidecar.read_text())["status"], "applied")
        config.write_text(config.read_text().replace('model = "fixture"', 'model = "new"'))
        self.assertEqual(self.run_main("--rollback")[0], 0)
        self.assertIn('model = "new"', config.read_text())
        self.assertNotIn("notify = []", config.read_text())
        self.assertFalse(sidecar.exists())


if __name__ == "__main__":
    unittest.main()
