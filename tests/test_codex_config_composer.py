"""所有区画だけの合成、衝突拒否、世代復旧を合成fixtureで検証する。"""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import codex_config_composer as composer
import codex_hook_state as hook_state


class ComposerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.target = self.root / "home/.codex/config.toml"
        self.target.parent.mkdir(parents=True)
        self.state = self.root / "private"
        self.source = (ROOT / "config/codex/permissions.toml").read_text()
        self.legacy = (ROOT / "config/codex/legacy-developer.toml").read_text()

    def apply(self):
        return composer.apply_policy(self.target, self.source, self.legacy, self.state, True)

    def unmarked_options(self, original):
        return {"adopt_unmarked": True, "expected_target_path": str(self.target.resolve()),
                "expected_target_sha256": hashlib.sha256(original).hexdigest(),
                "expected_source_sha256": hashlib.sha256(self.source.encode()).hexdigest(),
                "expected_legacy_sha256": hashlib.sha256(self.legacy.encode()).hexdigest(),
                "expected_after_owned_sha256": hashlib.sha256(
                    composer.canonical(composer.desired_policy(self.source)[0])).hexdigest()}

    def test_unmarked_known_legacy_adoption_is_explicit_and_initial_rollback_refused(self):
        original = ('model = "fixture"\n' + self.legacy).encode()
        self.target.write_bytes(original)
        state = self.target.parent / "config-composer"
        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"):
            with self.assertRaisesRegex(ValueError, "台帳なし"):
                composer.apply_policy(self.target, self.source, self.legacy, state, False)
            preview = composer.apply_policy(self.target, self.source, self.legacy, state, False,
                                            **self.unmarked_options(original))
            self.assertTrue(preview["changed"])
            self.assertFalse(preview["applied"])
            self.assertEqual(self.target.read_bytes(), original)
            self.assertFalse(state.exists())
            result = composer.apply_policy(self.target, self.source, self.legacy, state, True,
                                           **self.unmarked_options(original))
            self.assertTrue(result["changed"])
            self.assertTrue(result["applied"])
            self.assertEqual({key: preview[key] for key in ("after_hash", "after_owned_sha256", "unowned_sha256")},
                             {key: result[key] for key in ("after_hash", "after_owned_sha256", "unowned_sha256")})
            self.assertEqual(composer.policy_unowned(composer.Document(self.target.read_text()).data),
                             composer.policy_unowned(composer.Document(original.decode()).data))
            self.assertEqual(result["unowned_sha256"], hashlib.sha256(composer.canonical(
                composer.policy_unowned(composer.Document(original.decode()).data))).hexdigest())
            ledger_path = composer._ledger_path(state, self.target)
            ledger = json.loads(ledger_path.read_text())
            self.assertEqual(ledger["migration_kind"], "legacy_unmarked")
            self.assertEqual(ledger["status"], "applied")
            self.assertEqual((Path(ledger["backup"]) / "config.toml").read_bytes(), original)
            with self.assertRaisesRegex(ValueError, "初回世代rollbackは禁止"):
                composer.rollback_policy(self.target, state)
            after = self.target.read_bytes()
            self.assertFalse(composer.apply_policy(self.target, self.source, self.legacy, state, True)["changed"])
            with self.assertRaisesRegex(ValueError, "既存ledger/pending"):
                composer.apply_policy(self.target, self.source, self.legacy, state, True,
                                      **self.unmarked_options(after))
            self.assertEqual(self.target.read_bytes(), after)

    def test_unmarked_known_legacy_rejects_unknown_key_changed_value_and_hash(self):
        state = self.target.parent / "config-composer"
        first, rest = self.legacy.split("[permissions.developer]", 1)
        fixtures = (("unknown key", self.legacy + "unknown_permission = true\n", "旧wealth所有区画"),
                    ("description", self.legacy.replace('description = ', 'description = "changed" # ', 1),
                     "旧wealth所有区画"),
                    ("extends", self.legacy.replace('extends = ":workspace"', 'extends = ":read-only"', 1),
                     "旧wealth所有区画"),
                    ("maintenance", self.legacy + '\n[permissions.maintenance]\ndescription = "fixture"\n',
                     "新profileが台帳なし"),
                    ("review", self.legacy + '\n[permissions.review]\nextends = ":read-only"\n',
                     "新profileが台帳なし"),
                    ("old marker", composer.LEGACY_START + first + composer.LEGACY_END + composer.LEGACY_START +
                     "[permissions.developer]" + rest + composer.LEGACY_END, "初回移管条件"))
        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"):
            for label, text, message in fixtures:
                for write in (False, True):
                    with self.subTest(fixture=label, write=write):
                        self.target.write_text(text)
                        original = self.target.read_bytes()
                        with self.assertRaisesRegex(ValueError, message):
                            composer.apply_policy(self.target, self.source, self.legacy, state, write,
                                                  **self.unmarked_options(original))
                        self.assertEqual(self.target.read_bytes(), original)
                        self.assertFalse(list(state.glob("*.json")))
                        self.assertFalse((state / "backups").exists())
            self.target.write_text(self.legacy)
            original = self.target.read_bytes()
            options = self.unmarked_options(original)
            options["expected_target_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "固定hash"):
                composer.apply_policy(self.target, self.source, self.legacy, state, True, **options)

    def test_unmarked_known_legacy_recover_before_and_after_target_write(self):
        state = self.target.parent / "config-composer"
        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"):
            for failure_call, recovery in ((2, "applied_from_legacy"), (3, "applied")):
                with self.subTest(failure_call=failure_call):
                    self.target.write_text(self.legacy)
                    original = self.target.read_bytes()
                    original_write = composer.atomic_write
                    calls = 0

                    def fail_once(*args, **kwargs):
                        nonlocal calls
                        calls += 1
                        if calls == failure_call:
                            raise OSError("injected write failure")
                        return original_write(*args, **kwargs)

                    with mock.patch.object(composer, "atomic_write", side_effect=fail_once):
                        with self.assertRaisesRegex(OSError, "injected write failure"):
                            composer.apply_policy(self.target, self.source, self.legacy, state, True,
                                                  **self.unmarked_options(original))
                    ledger_path = composer._ledger_path(state, self.target)
                    self.assertEqual(json.loads(ledger_path.read_text())["status"], "pending")
                    self.assertEqual(self.target.read_bytes() == original, failure_call == 2)
                    self.assertEqual(composer.recover_policy(self.target, state), recovery)
                    self.assertEqual(json.loads(ledger_path.read_text())["status"], "applied")
                    with self.assertRaisesRegex(ValueError, "初回世代rollbackは禁止"):
                        composer.rollback_policy(self.target, state)
                    ledger_path.unlink()

    def test_unmarked_known_legacy_rejects_existing_pending_and_bad_profiles(self):
        state = self.target.parent / "config-composer"
        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"):
            self.target.write_text(self.legacy)
            original = self.target.read_bytes()
            state.mkdir()
            ledger_path = composer._ledger_path(state, self.target)
            ledger_path.write_text('{"status":"pending"}\n')
            for write in (False, True):
                with self.subTest(existing_ledger_write=write):
                    with self.assertRaisesRegex(ValueError, "既存ledger/pending"):
                        composer.apply_policy(self.target, self.source, self.legacy, state, write,
                                              **self.unmarked_options(original))
                    self.assertEqual(self.target.read_bytes(), original)
                    self.assertEqual(ledger_path.read_text(), '{"status":"pending"}\n')
                    self.assertEqual((state / "composer.lock").exists(), write)
            ledger_path.unlink()
            unknown_write = (self.legacy + '\n[permissions.other.filesystem]\n' +
                             json.dumps(str(self.target)) + ' = "write"\n')
            flat_roots_write = (self.legacy + '\n[permissions.other]\nworkspace_roots = { ' +
                                json.dumps(str(self.root / "home/.codex")) + ' = true }\n\n'
                                '[permissions.other.filesystem]\n":workspace_roots" = "write"\n')
            for text, message in ((unknown_write,
                                   "未知profile"),
                                  (flat_roots_write, "未知profile"),
                                  ('sandbox_mode = "danger-full-access"\n' + self.legacy, "legacy sandbox")):
                self.target.write_text(text)
                original = self.target.read_bytes()
                with self.assertRaisesRegex(ValueError, message):
                    composer.apply_policy(self.target, self.source, self.legacy, state, True,
                                          **self.unmarked_options(original))
                self.assertEqual(self.target.read_bytes(), original)
                self.assertFalse(ledger_path.exists())

    def test_unmarked_known_legacy_requires_every_expected_hash_and_valid_record(self):
        state = self.target.parent / "config-composer"
        self.target.write_text(self.legacy)
        original = self.target.read_bytes()
        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"):
            for field in ("expected_target_sha256", "expected_source_sha256",
                          "expected_legacy_sha256", "expected_after_owned_sha256"):
                for write in (False, True):
                    with self.subTest(field=field, write=write):
                        options = self.unmarked_options(original)
                        options[field] = "0" * 64
                        with self.assertRaisesRegex(ValueError, "不一致"):
                            composer.apply_policy(self.target, self.source, self.legacy, state, write, **options)
                        self.assertEqual(self.target.read_bytes(), original)
                        self.assertFalse(list(state.glob("*.json")))
            repo_target = self.root / "repo/.codex/config.toml"
            repo_target.parent.mkdir(parents=True)
            repo_target.write_bytes(original)
            options = self.unmarked_options(original)
            options["expected_target_path"] = str(repo_target.resolve())
            with self.assertRaisesRegex(ValueError, "global設定だけ"):
                composer.apply_policy(repo_target, self.source, self.legacy, self.state, False, **options)
            self.assertFalse(self.state.exists())
            options = self.unmarked_options(original)
            options["expected_target_path"] = str(self.root / "wrong/config.toml")
            with self.assertRaisesRegex(ValueError, "対象path"):
                composer.apply_policy(self.target, self.source, self.legacy, state, True, **options)
            composer.apply_policy(self.target, self.source, self.legacy, state, True,
                                  **self.unmarked_options(original))
            ledger_path = composer._ledger_path(state, self.target)
            record = json.loads(ledger_path.read_text())
            record["status"] = "pending"
            record["expected_after_owned_sha256"] = "0" * 64
            ledger_path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "after区画"):
                composer.recover_policy(self.target, state)
            self.assertEqual(json.loads(ledger_path.read_text())["status"], "pending")
            record["expected_after_owned_sha256"] = self.unmarked_options(original)["expected_after_owned_sha256"]
            record["status"] = "rollback_pending"
            ledger_path.write_text(json.dumps(record))
            applied = self.target.read_bytes()
            with self.assertRaisesRegex(ValueError, "初回世代rollbackは禁止"):
                composer.recover_policy(self.target, state)
            self.assertEqual(self.target.read_bytes(), applied)

    def test_unmarked_known_legacy_cli_opt_in_uses_fixture_home(self):
        self.target.write_text(self.legacy)
        original = self.target.read_bytes()
        state = self.target.parent / "config-composer"
        options = self.unmarked_options(original)
        command = [sys.executable, str(ROOT / "scripts/codex_config_composer.py"),
                   "--target", str(self.target), "--state-dir", str(state),
                   "--source", str(ROOT / "config/codex/permissions.toml"),
                   "--legacy-source", str(ROOT / "config/codex/legacy-developer.toml"),
                   "--adopt-legacy-unmarked"]
        for name, value in options.items():
            if name != "adopt_unmarked":
                command.extend(["--" + name.replace("_", "-"), value])
        env = dict(os.environ, HOME=str(self.root / "home"))
        preview = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        self.assertEqual(json.loads(preview.stdout)["applied"], False)
        self.assertEqual(self.target.read_bytes(), original)
        self.assertFalse(state.exists())
        refused = subprocess.run(command + ["--recover"], env=env, capture_output=True, text=True, check=False)
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertFalse(state.exists())
        result = subprocess.run(command + ["--apply"], env=env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(composer._ledger_path(state, self.target).read_text())["status"], "applied")

    def test_first_apply_creates_missing_repo_config_parent(self):
        target = self.root / "new-repo/.codex/config.toml"
        self.assertFalse(target.parent.exists())
        preview = composer.apply_policy(target, self.source, self.legacy, self.state, False)
        self.assertTrue(preview["changed"])
        self.assertFalse(target.parent.exists())
        result = composer.apply_policy(target, self.source, self.legacy, self.state, True)
        self.assertTrue(result["changed"])
        self.assertTrue(target.is_file())
        self.assertEqual(composer.policy_owned(composer.Document(target.read_text()).data),
                         composer.desired_policy(self.source)[0])
        ledger = composer._ledger_path(self.state, target)
        self.assertEqual(json.loads(ledger.read_text())["status"], "applied")

    def test_unknown_siblings_arrays_and_quoted_key_preserved(self):
        original = ('model = "fixture"\n\n[features]\njs_repl = true\n\n'
                    '[custom."a.b"]\nitems = [1, 2]\n')
        self.target.write_text(original)
        self.assertTrue(composer.apply_policy(self.target, self.source, self.legacy, self.state, False)["changed"])
        self.assertFalse(self.state.exists())
        self.assertTrue(self.apply()["changed"])
        parsed = composer.Document(self.target.read_text()).data
        self.assertEqual(parsed["custom"]["a.b"]["items"], [1, 2])
        self.assertTrue(parsed["features"]["js_repl"])
        self.assertFalse(self.apply()["changed"])
        self.target.write_text(self.target.read_text().replace('model = "fixture"', 'model = "other"'))
        self.assertFalse(self.apply()["changed"])
        self.assertEqual(composer.rollback_policy(self.target, self.state)["target"], str(self.target))
        self.assertIn('model = "other"', self.target.read_text())
        self.assertNotIn("default_permissions", self.target.read_text())

    def test_owned_edit_and_legacy_sandbox_refused(self):
        self.target.write_text('model = "fixture"\n')
        self.apply()
        changed = self.target.read_text().replace('default_permissions = "developer"', 'default_permissions = "review"')
        self.target.write_text(changed)
        with self.assertRaisesRegex(ValueError, "独自変更"):
            self.apply()
        self.target.write_text('sandbox_mode = "danger-full-access"\n')
        with self.assertRaisesRegex(ValueError, "legacy sandbox"):
            self.apply()

    def test_legacy_marker_migration_and_pending_recovery(self):
        first, rest = self.legacy.split("[permissions.developer]", 1)
        self.target.write_text(composer.LEGACY_START + first + composer.LEGACY_END +
                               'model = "fixture"\n\n' + composer.LEGACY_START +
                               "[permissions.developer]" + rest + composer.LEGACY_END)
        self.apply()
        self.assertNotIn("wealth-advisor developer permissions", self.target.read_text())
        path = composer._ledger_path(self.state, self.target)
        record = json.loads(path.read_text())
        record["status"] = "pending"
        path.write_text(json.dumps(record))
        old = (Path(record["backup"]) / "config.toml").read_text()
        self.target.write_text(old.replace('model = "fixture"', 'model = "changed"'))
        self.assertEqual(composer.recover_policy(self.target, self.state), "applied_from_legacy")
        self.assertIn('model = "changed"', self.target.read_text())
        with self.assertRaisesRegex(ValueError, "初回世代rollbackは禁止"):
            composer.rollback_policy(self.target, self.state)
        self.assertNotIn(composer.LEGACY_START, self.target.read_text())

    def test_pending_recovery_rejects_edit_after_snapshot(self):
        first, rest = self.legacy.split("[permissions.developer]", 1)
        self.target.write_text(composer.LEGACY_START + first + composer.LEGACY_END +
                               'model = "fixture"\n\n' + composer.LEGACY_START +
                               "[permissions.developer]" + rest + composer.LEGACY_END)
        self.apply()
        path = composer._ledger_path(self.state, self.target)
        record = json.loads(path.read_text())
        record["status"] = "pending"
        path.write_text(json.dumps(record))
        self.target.write_bytes((Path(record["backup"]) / "config.toml").read_bytes())
        actual_owned = composer.policy_owned
        edited = False

        def edit_after_parse(*args, **kwargs):
            nonlocal edited
            result = actual_owned(*args, **kwargs)
            if not edited:
                edited = True
                self.target.write_text(self.target.read_text().replace('model = "fixture"', 'model = "external"'))
            return result

        with mock.patch.object(composer, "policy_owned", side_effect=edit_after_parse):
            with self.assertRaisesRegex(ValueError, "外部編集"):
                composer.recover_policy(self.target, self.state)
        self.assertIn('model = "external"', self.target.read_text())
        self.assertEqual(json.loads(path.read_text())["status"], "pending")

    def test_symlink_target_refused_before_ledger_or_replace(self):
        real = self.root / "real-config.toml"
        real.write_text('model = "fixture"\n')
        self.target.symlink_to(real)
        for operation in (lambda: self.apply(),
                          lambda: composer.recover_policy(self.target, self.state),
                          lambda: composer.rollback_policy(self.target, self.state)):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, "symlink"):
                    operation()
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(real.read_text(), 'model = "fixture"\n')
        self.assertFalse(self.state.exists())

    def test_global_uses_fixed_private_temp_for_apply_and_rollback(self):
        self.target.write_text('model = "fixture"\n')
        fixed = self.target.parent / "config-composer"
        created_in = []
        mkstemp = composer.tempfile.mkstemp

        def observe_temp(*args, **kwargs):
            created_in.append(Path(kwargs["dir"]))
            return mkstemp(*args, **kwargs)

        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"), \
             mock.patch.object(composer.tempfile, "mkstemp", side_effect=observe_temp):
            with self.assertRaisesRegex(ValueError, "private台帳"):
                self.apply()
            self.assertFalse(self.state.exists())
            composer.apply_policy(self.target, self.source, self.legacy, fixed, True)
            changed_source = self.source.replace("明示保守時のglobal設定編集", "fixture変更")
            composer.apply_policy(self.target, changed_source, self.legacy, fixed, True)
            composer.rollback_policy(self.target, fixed)
        self.assertIn(fixed, created_in)
        self.assertNotIn(self.target.parent, created_in)
        self.assertIn('model = "fixture"', self.target.read_text())

    def test_global_legacy_recover_uses_same_private_temp(self):
        first, rest = self.legacy.split("[permissions.developer]", 1)
        self.target.write_text(composer.LEGACY_START + first + composer.LEGACY_END +
                               'model = "fixture"\n\n' + composer.LEGACY_START +
                               "[permissions.developer]" + rest + composer.LEGACY_END)
        fixed = self.target.parent / "config-composer"
        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"):
            composer.apply_policy(self.target, self.source, self.legacy, fixed, True)
            path = composer._ledger_path(fixed, self.target)
            record = json.loads(path.read_text())
            record["status"] = "pending"
            path.write_text(json.dumps(record))
            self.target.write_bytes((Path(record["backup"]) / "config.toml").read_bytes())
            created_in = []
            mkstemp = composer.tempfile.mkstemp

            def observe_temp(*args, **kwargs):
                created_in.append(Path(kwargs["dir"]))
                return mkstemp(*args, **kwargs)

            with mock.patch.object(composer.tempfile, "mkstemp", side_effect=observe_temp):
                self.assertEqual(composer.recover_policy(self.target, fixed), "applied_from_legacy")
        self.assertIn(fixed, created_in)
        self.assertNotIn(self.target.parent, created_in)

    def test_global_state_validation_precedes_lock_for_all_operations(self):
        self.target.write_text('model = "fixture"\n')
        fixed = self.target.parent / "config-composer"
        wrong = self.root / "wrong-state"
        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"):
            operations = (lambda: composer.apply_policy(self.target, self.source, self.legacy, wrong, True),
                          lambda: composer.recover_policy(self.target, wrong),
                          lambda: composer.rollback_policy(self.target, wrong))
            for operation in operations:
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(ValueError, "private台帳"):
                        operation()
            self.assertFalse(wrong.exists())
            actual = self.root / "actual-state"
            actual.mkdir(mode=0o750)
            fixed.symlink_to(actual, target_is_directory=True)
            for operation in (lambda: composer.apply_policy(self.target, self.source, self.legacy, fixed, True),
                              lambda: composer.recover_policy(self.target, fixed),
                              lambda: composer.rollback_policy(self.target, fixed)):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        operation()
            self.assertEqual(actual.stat().st_mode & 0o777, 0o750)
            self.assertFalse((actual / "composer.lock").exists())

    def test_global_device_mismatch_stops_before_pending(self):
        self.target.write_text('model = "fixture"\n')
        fixed = self.target.parent / "config-composer"
        original = self.target.read_bytes()
        stat = Path.stat

        def different_device(path, *args, **kwargs):
            result = stat(path, *args, **kwargs)
            if path == fixed:
                return mock.Mock(st_dev=result.st_dev + 1, st_mode=result.st_mode)
            return result

        with mock.patch.object(composer.Path, "home", return_value=self.root / "home"), \
             mock.patch.object(Path, "stat", different_device):
            with self.assertRaisesRegex(ValueError, "filesystem"):
                composer.apply_policy(self.target, self.source, self.legacy, fixed, True)
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(list(fixed.glob("*.json")), [])
        self.assertFalse((fixed / "backups").exists())

    def test_cleanup_error_keeps_primary_error_and_target(self):
        self.target.write_text('model = "fixture"\n')
        original = self.target.read_bytes()
        with mock.patch.object(composer.os, "replace", side_effect=OSError("primary replace failed")), \
             mock.patch.object(composer.os, "unlink", side_effect=OSError("cleanup failed")):
            with self.assertRaisesRegex(OSError, "primary replace failed") as caught:
                composer.atomic_write(self.target, b'model = "updated"\n', original)
        self.assertTrue(any("cleanup failed" in note for note in caught.exception.__notes__))
        self.assertEqual(self.target.read_bytes(), original)

    def test_after_replace_ledger_failure_stays_pending_and_recovers(self):
        self.target.write_text('model = "fixture"\n')
        original_write = composer.atomic_write
        calls = 0

        def fail_final_ledger(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("ledger final write failed")
            return original_write(*args, **kwargs)

        with mock.patch.object(composer, "atomic_write", side_effect=fail_final_ledger):
            with self.assertRaisesRegex(OSError, "ledger final write failed"):
                self.apply()
        self.assertEqual(calls, 3)
        path = composer._ledger_path(self.state, self.target)
        self.assertEqual(json.loads(path.read_text())["status"], "pending")
        self.assertIn("default_permissions", self.target.read_text())
        self.assertEqual(composer.recover_policy(self.target, self.state), "applied")
        self.assertEqual(json.loads(path.read_text())["status"], "applied")

    def test_multiline_and_dotted_unknown_never_change(self):
        original = ('description = """first\napproval_policy = "hidden"\nlast"""\n'
                    '"odd.key" = { items = ["a", "b"] }\n')
        self.target.write_text(original)
        with self.assertRaisesRegex(ValueError, "所有外のTOML意味木"):
            self.apply()
        self.assertEqual(self.target.read_text(), original)
        hook_text = ('description = """start\nnotify = ["hidden"]\nend"""\n'
                     '[features]\njs_repl = true\n')
        with self.assertRaisesRegex(ValueError, "所有外のTOML意味木"):
            composer.compose_hooks(hook_text, [{"key": "fixture", "enabled": False}])
        for inline_or_dotted in ('features = { js_repl = true }\n',
                                 'features.js_repl = true\n'):
            with self.subTest(inline_or_dotted=inline_or_dotted):
                with self.assertRaises((ValueError, tomllib.TOMLDecodeError)):
                    composer.compose_hooks(inline_or_dotted, [{"key": "fixture", "enabled": False}])

    def test_unknown_global_write_profile_refused(self):
        home = Path.home()

        def read_only(filesystem):
            # 基底を:read-onlyに固定し、path判定そのものを検査する。
            return '[permissions.other]\nextends = ":read-only"\n\n[permissions.other.filesystem]\n' + filesystem

        def flat(path):
            return read_only(json.dumps(path) + ' = "write"\n')

        paths = ("~/.codex/config.toml", str(home / ".codex/config.toml"),
                 str(home / ".codex/../.codex/config.toml"), str(home), "/", ":root")
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "global write"):
                    composer.compose_policy(flat(path), self.source)
        nested = ('[permissions.other]\nextends = ":read-only"\n\n[permissions.other.filesystem."~"]\n'
                  '".codex/config.toml" = "write"\n')
        with self.assertRaisesRegex(ValueError, "global write"):
            composer.compose_policy(nested, self.source)
        alias = self.root / "codex-link"
        alias.symlink_to(home / ".codex", target_is_directory=True)
        loop = self.root / "loop"
        loop.symlink_to(loop)
        for path in (str(alias / "config.toml"), str(loop / "x")):
            with self.subTest(symlink=path):
                with self.assertRaisesRegex(ValueError, "global write"):
                    composer.compose_policy(flat(path), self.source)
        result, *_ = composer.compose_policy(flat("~/.codex-extra"), self.source)
        self.assertEqual(composer.Document(result).data["permissions"]["other"]["filesystem"]["~/.codex-extra"], "write")

        case_and_glob = ("~/.CODEX", "~/.Codex/config.toml", str(home / ".codex/config.toml").upper(),
                         "~/.cod*/config.toml", "~/.CO?EX/rules", "~/[.]codex/config.toml", "~/**/config.toml",
                         "~/*/config.toml", str(home.parent) + "/*/.codex/config.toml", "/**",
                         "~/*.md", "~/.{codex,x}/config.toml", "~/{.c,x}*", str(home.parent) + "/*")
        relative_or_unresolved = (".codex", "../../.codex", "relative/x", "./tmp", "$HOME/.codex",
                                  "/tmp/${P1_FIXTURE}", "~no_such_user_p1_fixture/x")
        for path in case_and_glob + relative_or_unresolved:
            with self.subTest(dangerous_path=path):
                with self.assertRaisesRegex(ValueError, "global write"):
                    composer.compose_policy(flat(path), self.source)
        for base, subpath in (("relative", "x"), (".", "tmp"), ("..", ".codex")):
            with self.subTest(relative_nested=base):
                text = read_only(json.dumps(base) + " = { " + json.dumps(subpath) + ' = "write" }\n')
                with self.assertRaisesRegex(ValueError, "global write"):
                    composer.compose_policy(text, self.source)
        for path in ("~/.CODEX-extra", "~/Workspace/*.md", "~/Workspace/{a,b}.md", "~/.cod", "~/.cod?/config.toml",
                     "~/.c[!o]dex/config.toml", "/tmp/p1-fixture"):
            with self.subTest(safe_path=path):
                result, *_ = composer.compose_policy(flat(path), self.source)
                self.assertEqual(composer.Document(result).data["permissions"]["other"]["filesystem"][path], "write")

        # 実行時workspace rootは未知（~/.codex自身もありうる）ため、明示rootの有無・内容によらず拒否する。
        def roots_profile(roots, filesystem):
            head = '[permissions.other]\nextends = ":read-only"\n'
            if roots is not None:
                head += 'workspace_roots = ' + roots + '\n'
            return head + '\n[permissions.other.filesystem]\n' + filesystem + '\n'

        root_writes = ('":workspace_roots" = "write"', '":workspace_roots" = { ".codex" = "write" }',
                       '":workspace_roots" = { "config.toml" = "write" }', '":workspace_roots" = { "src" = "write" }')
        for roots in (None, '{ "~/.codex" = true }', '{ "~/Workspace/project" = true }', '{ "~/.codex" = false }',
                      '{ "." = true }', '{ ".." = true }', '["~/.codex"]'):
            for filesystem in root_writes:
                with self.subTest(roots=roots, form=filesystem):
                    with self.assertRaisesRegex(ValueError, "global write"):
                        composer.compose_policy(roots_profile(roots, filesystem), self.source)
        for roots, filesystem in ((None, '":workspace_roots" = "read"'),
                                  ('{ "~/.codex" = true }', '":workspace_roots" = { "config.toml" = "read" }'),
                                  ('{ "~/Workspace/project" = true }', '"~/Workspace/project" = "write"')):
            with self.subTest(harmless=roots, form=filesystem):
                text = roots_profile(roots, filesystem)
                result, *_ = composer.compose_policy(text, self.source)
                self.assertEqual(composer.policy_unowned(composer.Document(result).data),
                                 composer.policy_unowned(composer.Document(text).data))

    def test_unknown_profile_inheritance_special_base_and_types_are_conservative(self):
        home = Path.home()
        under_root = json.dumps(str((home / ".codex/config.toml").relative_to("/")))
        read_only = '[permissions.other]\nextends = ":read-only"\n\n'
        dangerous = {
            "extends maintenance": '[permissions.other]\nextends = "maintenance"\n',
            "extends developer": '[permissions.other]\nextends = "developer"\n',
            "extends developer with project root": ('[permissions.other]\nextends = "developer"\n'
                                                     'workspace_roots = { "~/Workspace/project" = true }\n'),
            ":workspace only": '[permissions.other]\nextends = ":workspace"\n',
            ":workspace with project root": ('[permissions.other]\nextends = ":workspace"\n'
                                             'workspace_roots = { "~/Workspace/project" = true, "~/.codex" = false }\n'),
            ":workspace with codex root": ('[permissions.other]\nextends = ":workspace"\n'
                                           'workspace_roots = { "~/.codex" = true }\n'),
            ":workspace with relative root": ('[permissions.other]\nextends = ":workspace"\n'
                                              'workspace_roots = { ".." = true }\n'),
            ":workspace with non-dict roots": ('[permissions.other]\nextends = ":workspace"\n'
                                               'workspace_roots = "~"\n'),
            "indirect maintenance": ('[permissions.other]\nextends = "middle"\n\n'
                                     '[permissions.middle]\nextends = "maintenance"\n'),
            "indirect :workspace": ('[permissions.other]\nextends = "middle"\n\n'
                                    '[permissions.middle]\nextends = ":workspace"\n'),
            "parent explicit write": ('[permissions.other]\nextends = "middle"\n\n'
                                      '[permissions.middle]\nextends = ":read-only"\n\n'
                                      '[permissions.middle.filesystem]\n"~/.codex/rules" = "write"\n'),
            "parent root write": ('[permissions.other]\nextends = "middle"\n\n'
                                  '[permissions.middle]\nextends = ":read-only"\n\n'
                                  '[permissions.middle.filesystem.":workspace_roots"]\n"src" = "write"\n'),
            "no extends global write": '[permissions.other.filesystem]\n"~/.codex/rules" = "write"\n',
            "no extends root write": '[permissions.other.filesystem]\n":workspace_roots" = "write"\n',
            "no extends special base": '[permissions.other.filesystem]\n":tmpdir" = "write"\n',
            "no extends relative": '[permissions.other.filesystem]\n".codex" = "write"\n',
            # extendsなしはCLI 0.155.1のcanaryで制限基底と確認できず（選択時abort）、明示writeの内容によらず拒否する。
            "no extends": '[permissions.other]\ndescription = "fixture"\n',
            "no extends with explicit write": '[permissions.other.filesystem]\n"/tmp/p1-fixture" = "write"\n',
            "parent without extends": ('[permissions.other]\nextends = "middle"\n\n'
                                       '[permissions.middle.filesystem]\n"~/Workspace/project" = "write"\n'),
            "parent without extends global write": ('[permissions.other]\nextends = "middle"\n\n'
                                                    '[permissions.middle.filesystem]\n"~/.codex" = "write"\n'),
            "cycle": ('[permissions.other]\nextends = "middle"\n\n'
                      '[permissions.middle]\nextends = "other"\n'),
            "unknown parent": '[permissions.other]\nextends = "missing"\n',
            "unknown builtin": '[permissions.other]\nextends = ":danger-full-access"\n',
            "non-string extends": '[permissions.other]\nextends = 1\n',
            "non-dict profile": '[permissions]\nother = "write"\n',
            "non-dict permissions": 'permissions = "write"\n',
            "non-dict filesystem": '[permissions.other]\nextends = ":read-only"\nfilesystem = "write"\n',
            "unknown access": read_only + '[permissions.other.filesystem]\n"~/Workspace" = "rw"\n',
            "unknown nested access": read_only + '[permissions.other.filesystem."~/Workspace"]\n"x" = 1\n',
            "none is not official access": read_only + '[permissions.other.filesystem]\n"~/.codex" = "none"\n',
            "nested none": read_only + '[permissions.other.filesystem."~/Workspace"]\n"x" = "none"\n',
            "nested :root": read_only + '[permissions.other.filesystem.":root"]\n' + under_root + ' = "write"\n',
            "nested unknown special": read_only + '[permissions.other.filesystem.":tmpdir"]\n"x" = "write"\n',
            "flat unknown special": read_only + '[permissions.other.filesystem]\n":tmpdir" = "write"\n',
        }
        for label, text in dangerous.items():
            with self.subTest(dangerous=label):
                with self.assertRaisesRegex(ValueError, "global write|permissionsの型"):
                    composer.compose_policy(text, self.source)

        applied, *_ = composer.compose_policy("", self.source)
        desired = composer.desired_policy(self.source)[0]
        for parent in ("maintenance", "developer"):
            with self.subTest(applied_parent=parent):
                with self.assertRaisesRegex(ValueError, "global write"):
                    composer.compose_policy(applied + '\n[permissions.other]\nextends = "' + parent + '"\n',
                                            self.source, desired)
        safe = {
            "extends review": '[permissions.other]\nextends = "review"\n',
            ":read-only with explicit write": (read_only + '[permissions.other.filesystem]\n"~/Workspace" = "write"\n'
                                               '"~/.codex" = "read"\n'),
            "indirect :read-only with explicit write": ('[permissions.other]\nextends = "middle"\n\n'
                                                        '[permissions.middle]\nextends = ":read-only"\n\n'
                                                        '[permissions.middle.filesystem]\n"/tmp/p1-fixture" = "write"\n'),
            "nested :root elsewhere": read_only + '[permissions.other.filesystem.":root"]\n"tmp/p1-fixture" = "write"\n',
            "absolute nested base": read_only + '[permissions.other.filesystem."~/Workspace"]\n"project" = "write"\n',
            "deny is non-write": (read_only + '[permissions.other.filesystem]\n"~/.codex" = "deny"\n'
                                  '":workspace_roots" = "deny"\n"~/Workspace" = "write"\n'),
            "nested deny": read_only + '[permissions.other.filesystem."~"]\n".codex" = "deny"\n',
        }
        for label, extra in safe.items():
            with self.subTest(safe=label):
                text = applied + "\n" + extra
                result, *_ = composer.compose_policy(text, self.source, desired)
                self.assertEqual(result, text)

    def test_source_developer_is_agent_crew_only_without_global_write(self):
        data = tomllib.loads(self.source)
        developer, maintenance, review = (data["permissions"][name] for name in composer.OWNED_PROFILES)
        self.assertEqual(developer["extends"], ":read-only")
        self.assertEqual(developer["filesystem"], {
            "~/Workspace/agent-crew": "write", "~/Workspace/agent-crew/.git": "write",
            "~/Workspace/agent-crew/.codex": "read", "~/Workspace/agent-crew/.codex/config.toml": "read",
            "/**/.codex/**": "deny",
            "~/.cache": "write", "~/.npm": "write", "~/.local/share/uv": "write", "~/Library/Caches": "write",
            ":tmpdir": "write", ":slash_tmp": "write"})
        self.assertIs(developer["network"]["enabled"], True)
        self.assertEqual(maintenance["extends"], ":read-only")  # developerのdenyを継承しない兄弟profile
        self.assertEqual(set(maintenance["filesystem"].values()), {"write"})
        self.assertEqual(set(maintenance["filesystem"]), {
            "~/Workspace/agent-crew", "~/Workspace/agent-crew/.git", "~/Workspace/agent-crew/.codex",
            "~/.cache", "~/.npm", "~/.local/share/uv", "~/Library/Caches", ":tmpdir", ":slash_tmp",
            "~/.codex/config.toml", "~/.codex/config-composer", "~/.codex/AGENTS.md", "~/.codex/rules",
            "~/.codex/skills", "~/.codex/agents", "~/.agents/skills", "~/.claude/settings.json",
            "~/.claude/skills", "~/.claude/agents"})
        self.assertEqual(developer["filesystem"], composer.SOURCE_DEVELOPER_FILESYSTEM)
        self.assertEqual(maintenance["filesystem"], composer.SOURCE_MAINTENANCE_FILESYSTEM)
        self.assertIs(maintenance["network"]["enabled"], True)
        self.assertEqual(review, {"description": review["description"], "extends": ":read-only"})
        self.assertNotIn(":workspace_roots", self.source)
        self.assertNotIn(str(Path.home()), self.source)  # ユーザー名を含む絶対pathを公開原本へ書かない
        # 公開原本にprivate repoの物理配置を書かない。private repo rootはそのrepoのprofile layerで追加する。
        self.assertNotIn("wealth", self.source.casefold())
        for path, access in developer["filesystem"].items():
            if access == "write" and path not in composer.SOURCE_SPECIAL_WRITE:
                with self.subTest(developer_path=path):
                    self.assertFalse(composer._global_write_path(path))
        # 旧原本は移管照合専用で変更しない。
        self.assertEqual(hashlib.sha256(self.legacy.encode()).hexdigest(), composer.KNOWN_UNMARKED_LEGACY_SHA256)
        # 固定hashは移管のexpected値と文書の値。原本を変えたら文書と同時に更新する。
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(),
                         "7675f876d4097e7a04787d9d889ba7eab92a7888bfba923422e76b61981df76d")
        self.assertEqual(hashlib.sha256(composer.canonical(composer.desired_policy(self.source)[0])).hexdigest(),
                         "9db64c8657083c7527ffc452994f7e59cd210d9da7ec910cfbda5e70e647d054")

    def test_source_regression_to_workspace_or_global_write_refused(self):
        developer_fs = '[permissions.developer.filesystem]\n'
        maintenance_fs = '[permissions.maintenance.filesystem]\n'
        maintenance_head = '[permissions.maintenance]\ndescription = "明示保守時のglobal設定編集"\nextends = ":read-only"\n'
        review_head = '[permissions.review]\ndescription = "読み取り専用の独立レビュー"\nextends = ":read-only"\n'
        regressions = {
            "developer extends :workspace": ('extends = ":read-only"\n\n' + developer_fs,
                                             'extends = ":workspace"\n\n' + developer_fs),
            "developer global config": (developer_fs, developer_fs + '"~/.codex/config.toml" = "write"\n'),
            "developer global dir": (developer_fs, developer_fs + '"~/.codex" = "write"\n'),
            "developer home ancestor": (developer_fs, developer_fs + '"~" = "write"\n'),
            "developer glob into global": (developer_fs, developer_fs + '"~/.cod*" = "write"\n'),
            "developer relative": (developer_fs, developer_fs + '".codex" = "write"\n'),
            "developer flat workspace_roots": (developer_fs, developer_fs + '":workspace_roots" = "write"\n'),
            "developer nested workspace_roots": (developer_fs, developer_fs + '":workspace_roots" = { ".codex" = "write" }\n'),
            "developer unknown special": (developer_fs, developer_fs + '":root" = "write"\n'),
            "developer none access": (developer_fs, developer_fs + '"~/.codex" = "none"\n'),
            "developer non-cache home dir": (developer_fs, developer_fs + '"~/.config" = "write"\n'),
            "developer claude dir": (developer_fs, developer_fs + '"~/.claude" = "write"\n'),
            "developer whole Workspace": (developer_fs, developer_fs + '"~/Workspace" = "write"\n'),
            "developer other repo": (developer_fs, developer_fs + '"~/Workspace/other" = "write"\n'),
            "developer repo .codex write": ('"~/Workspace/agent-crew/.codex" = "read"',
                                            '"~/Workspace/agent-crew/.codex" = "write"'),
            "developer repo .codex protection removed": ('"~/Workspace/agent-crew/.codex" = "read"\n', ''),
            "developer nested .codex deny removed": ('"/**/.codex/**" = "deny"\n', ''),
            "developer nested .codex deny narrowed": ('"/**/.codex/**" = "deny"', '"~/Workspace/agent-crew/**/.codex/**" = "deny"'),
            "developer network disabled": ('[permissions.developer.network]\nenabled = true',
                                           '[permissions.developer.network]\nenabled = false'),
            "developer workspace_roots key": ('extends = ":read-only"\n\n' + developer_fs,
                                              'extends = ":read-only"\nworkspace_roots = { "~" = true }\n\n' + developer_fs),
            "maintenance extra target": (maintenance_fs, maintenance_fs + '"~/.ssh" = "write"\n'),
            "maintenance extends :workspace": (maintenance_head, maintenance_head.replace(":read-only", ":workspace")),
            "maintenance extends developer": (maintenance_head, maintenance_head.replace('":read-only"', '"developer"')),
            "maintenance workspace_roots": (maintenance_fs, maintenance_fs + '":workspace_roots" = "write"\n'),
            "review extends developer": (review_head, review_head.replace(":read-only", "developer")),
            "review write": (review_head, review_head + '\n[permissions.review.filesystem]\n"/tmp/x" = "write"\n'),
        }
        for label, (old, new) in regressions.items():
            with self.subTest(regression=label):
                self.assertEqual(self.source.count(old), 1)
                with self.assertRaisesRegex(ValueError, "権限原本"):
                    composer.desired_policy(self.source.replace(old, new))
        self.target.write_text('model = "fixture"\n')
        with self.assertRaisesRegex(ValueError, "権限原本"):
            composer.apply_policy(self.target, self.source.replace(developer_fs, developer_fs + '"~/.codex" = "write"\n'),
                                  self.legacy, self.state, True)
        self.assertEqual(self.target.read_text(), 'model = "fixture"\n')
        self.assertFalse(self.state.exists())

    def test_second_generation_rollback_preserves_unowned_edit(self):
        self.target.write_text('model = "before"\n')
        self.apply()
        first = composer.policy_owned(composer.Document(self.target.read_text()).data)
        changed_source = self.source.replace("明示保守時のglobal設定編集", "fixture変更")
        composer.apply_policy(self.target, changed_source, self.legacy, self.state, True)
        self.target.write_text(self.target.read_text().replace('model = "before"', 'model = "after"'))
        composer.rollback_policy(self.target, self.state)
        self.assertEqual(composer.policy_owned(composer.Document(self.target.read_text()).data), first)
        self.assertIn('model = "after"', self.target.read_text())

    def test_pending_rollback_recovers_ledger(self):
        self.target.write_text('model = "fixture"\n')
        self.apply()
        changed_source = self.source.replace("明示保守時のglobal設定編集", "fixture変更")
        composer.apply_policy(self.target, changed_source, self.legacy, self.state, True)
        path = composer._ledger_path(self.state, self.target)
        record = json.loads(path.read_text())
        before_text = composer.restore_policy(self.target.read_text(), record["after"], record["before_fragments"])
        self.target.write_text(before_text)
        record["status"] = "rollback_pending"
        path.write_text(json.dumps(record))
        self.assertEqual(composer.recover_policy(self.target, self.state), "rolled_back")
        self.assertEqual(json.loads(path.read_text())["generation"], 1)

    def test_hook_entries_preserve_unknown_and_detect_tamper(self):
        key = '/fixture/hooks.json:stop:0:0'
        original = ('notify = []\n\n[features]\nhooks = true\njs_repl = true\n\n'
                    '[hooks.state."unknown.entry"]\nenabled = false\n')
        states = [{"key": key, "enabled": True, "trusted_hash": "sha256:" + "a" * 64}]
        with self.assertRaisesRegex(ValueError, "台帳なし"):
            composer.compose_hooks(original, states)
        initial = '[features]\njs_repl = true\n\n[hooks.state."unknown.entry"]\nenabled = false\n'
        content, before, after, fragments = composer.compose_hooks(initial, states)
        self.assertIn('"unknown.entry"', content)
        self.assertEqual(composer.compose_hooks(content, states, after, [key])[0], content)
        tampered = content.replace('trusted_hash = "sha256:' + "a" * 64,
                                   'trusted_hash = "sha256:' + "b" * 64)
        with self.assertRaisesRegex(ValueError, "独自変更"):
            composer.verify_hook_section(tampered, after)
        restored = composer.restore_hooks(content, after, fragments)
        self.assertIn('"unknown.entry"', restored)
        self.assertNotIn(key, restored)

    def test_original_wealth_installer_refuses_migrated_global_before_write(self):
        original_installer = ROOT / "tests/fixtures/legacy_wealth_install_codex_permissions.py"
        self.assertEqual(hashlib.sha256(original_installer.read_bytes()).hexdigest(),
                         "9b89101a8f4feec6a9c74cedf3ebb8010ceaebf7040ea1c7863e96ccb42fa3c7")
        self.target.write_text('model = "fixture"\n')
        self.apply()
        before = self.target.read_bytes()
        fake_repo = self.root / "wealth"
        (fake_repo / "scripts").mkdir(parents=True)
        shutil.copyfile(original_installer, fake_repo / "scripts/install_codex_permissions.py")
        env = dict(os.environ, HOME=str(self.root / "home"))
        result = subprocess.run([sys.executable, str(fake_repo / "scripts/install_codex_permissions.py"), "--apply"],
                                env=env, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("既存の approval_policy と競合", result.stderr)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse((self.root / "home/.codex/rules/developer.rules").exists())
        self.assertFalse((fake_repo / ".codex/config.toml").exists())

    def test_policy_and_hook_writers_share_lock_without_lost_update(self):
        repo = (self.root / "fixture-repo").resolve()
        (repo / "config").mkdir(parents=True)
        (repo / ".codex").mkdir()
        shutil.copyfile(ROOT / "config/crew-hooks.json", repo / "config/crew-hooks.json")
        target = repo / ".codex/config.toml"
        target.write_text('model = "fixture"\n')
        project_path = str(repo / ".codex/hooks.json")
        observed = []
        for event, groups in hook_state.generated_hooks(repo, "codex").items():
            observed.append({"key": f"{project_path}:{hook_state.snake(event)}:0:0",
                             "eventName": hook_state.EVENTS[event], "source": "project",
                             "sourcePath": project_path, "handlerType": "command", "isManaged": False,
                             "command": groups[0]["hooks"][0]["command"],
                             "currentHash": "sha256:" + "a" * 64})
        snap = self.root / "hooks-list.json"
        snap.write_text(json.dumps({"result": {"data": [{"cwd": str(repo), "hooks": observed, "errors": []}]}}))
        state_dir = self.root / "shared-private"
        commands = ([sys.executable, str(ROOT / "scripts/codex_config_composer.py"),
                     "--target", str(target), "--state-dir", str(state_dir),
                     "--source", str(ROOT / "config/codex/permissions.toml"),
                     "--legacy-source", str(ROOT / "config/codex/legacy-developer.toml"), "--apply"],
                    [sys.executable, str(ROOT / "scripts/codex_hook_state.py"),
                     "--root", str(repo), "--state-dir", str(state_dir),
                     "--snapshot", str(snap), "--apply"])
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for command in commands]
        results = [process.communicate(timeout=15) for process in processes]
        self.assertEqual([process.returncode for process in processes], [0, 0], results)
        data = composer.Document(target.read_text()).data
        self.assertEqual(data["model"], "fixture")
        self.assertEqual(composer.policy_owned(data), composer.desired_policy(self.source)[0])
        self.assertEqual(data["notify"], [])
        self.assertIs(data["features"]["hooks"], True)
        self.assertEqual(len(data["hooks"]["state"]), 3)


if __name__ == "__main__":
    unittest.main()
