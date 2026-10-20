"""生成・マージ・適用を隔離rootで検証する。"""

import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/install_crew_hooks.py"
SPEC = importlib.util.spec_from_file_location("install_crew_hooks", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="crew installer ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "config").mkdir()
        shutil.copyfile(REPO / "config/crew-hooks.json", self.root / "config/crew-hooks.json")

    def write_json(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False))
        return path

    def run_cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), *args],
            cwd=cwd or self.root, capture_output=True, text=True,
        )

    def test_manifest_and_runtime_commands(self):
        for runtime in ("claude", "codex"):
            generated = installer.generated_hooks(self.root, runtime)
            self.assertEqual("TaskCompleted" in generated, runtime == "claude")
            self.assertEqual(len(generated), 4 if runtime == "claude" else 3)
            self.assertNotIn("UserPromptSubmit", generated)
            for event, groups in generated.items():
                handler = groups[0]["hooks"][0]
                self.assertEqual(next(iter(handler)), "statusMessage")
                self.assertEqual(handler["timeout"], 15)
                self.assertIn(f"--runtime {runtime} --event {event}", handler["command"])
                self.assertNotIn(str(self.root), handler["command"])

    def test_merge_preserves_permissions_unknown_groups_and_similar_commands(self):
        known = ".claude/hooks/subagent_stop.sh"
        unknown = {"type": "command", "command": known + " --custom"}
        group = {"matcher": "custom", "other": 7, "hooks": [
            {"type": "command", "command": known}, unknown,
        ]}
        existing = {"permissions": {"allow": ["Bash(custom)"]}, "custom": True,
                    "hooks": {"Stop": [group], "UnknownEvent": [{"hooks": []}]}}
        frozen = json.loads(json.dumps(existing))
        result = installer.merge_settings(existing, installer.generated_hooks(self.root, "claude"), "claude")
        self.assertEqual(existing, frozen)
        self.assertEqual(result["permissions"], existing["permissions"])
        self.assertTrue(result["custom"])
        self.assertEqual(result["hooks"]["Stop"][1], {"matcher": "custom", "other": 7, "hooks": [unknown]})
        self.assertEqual(result["hooks"]["UnknownEvent"], [{"hooks": []}])
        self.assertEqual(installer.merge_settings(result, installer.generated_hooks(self.root, "claude"), "claude"), result)

    def test_removes_previous_owned_user_prompt_handler(self):
        for runtime in ("claude", "codex"):
            stale = {"type": "command", "statusMessage": f"crew-hooks:{runtime}:UserPromptSubmit",
                     "command": installer.hook_command(runtime, "UserPromptSubmit")}
            custom = {"type": "command", "command": "echo custom"}
            existing = {"hooks": {"UserPromptSubmit": [{"hooks": [stale, custom]}]}}
            merged = installer.merge_settings(existing, installer.generated_hooks(self.root, runtime), runtime)
            self.assertEqual(merged["hooks"]["UserPromptSubmit"], [{"hooks": [custom]}])
            owned_only = {"hooks": {"UserPromptSubmit": [{"hooks": [stale]}]}}
            merged = installer.merge_settings(owned_only, installer.generated_hooks(self.root, runtime), runtime)
            self.assertNotIn("UserPromptSubmit", merged["hooks"])

    def test_all_exact_legacy_commands_are_removed(self):
        old = {"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": command}
            for command in installer.LEGACY_COMMANDS
        ]}]}}
        generated = installer.generated_hooks(self.root, "claude")
        result = installer.merge_settings(old, generated, "claude")
        self.assertEqual(result["hooks"], generated)

    def test_dry_run_and_check_write_nothing(self):
        path = self.write_json(".codex/hooks.json", {"description": "維持", "hooks": {}})
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for args, expected in (((), 0), (("--check",), 1)):
            proc = self.run_cli(*args)
            self.assertEqual(proc.returncode, expected, proc.stderr)
            self.assertIn("(generated)", proc.stdout)
            after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
            self.assertEqual(after, before)
        self.assertFalse((self.root / "docs").exists())
        self.assertEqual(json.loads(path.read_text())["hooks"], {})

    def test_apply_backup_idempotence_and_unknown_codex_hooks(self):
        original = {"description": "保持", "hooks": {"Stop": [{"matcher": "x", "hooks": [
            {"type": "command", "command": "echo custom"}
        ]}]}}
        codex = self.write_json(".codex/hooks.json", original)
        claude = self.write_json(".claude/settings.json", {"permissions": {"allow": ["Read(*)"]}})
        old = {".codex/hooks.json": codex.read_bytes(), ".claude/settings.json": claude.read_bytes()}
        applied = self.run_cli("--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        backups = list((self.root / "docs/codex-direct/backups").glob("shared-*"))
        self.assertEqual(len(backups), 1)
        for relative, content in old.items():
            self.assertEqual((backups[0] / relative).read_bytes(), content)
        result = json.loads(codex.read_text())
        self.assertEqual(result["description"], "保持")
        self.assertEqual(result["hooks"]["Stop"][1], original["hooks"]["Stop"][0])
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (claude, codex)}
        self.assertEqual(self.run_cli("--check").returncode, 0)
        self.assertEqual(self.run_cli("--apply").returncode, 0)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (claude, codex)})
        self.assertEqual(list((self.root / "docs/codex-direct/backups").glob("shared-*")), backups)

    def test_other_cwd_and_commands_support_spaces(self):
        subdir = self.root / "nested space"
        subdir.mkdir()
        self.assertEqual(self.run_cli("--apply", cwd=subdir).returncode, 0)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / "scripts").mkdir()
        (self.root / "scripts/crew_hooks.py").write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n")
        for runtime in ("claude", "codex"):
            command = installer.generated_hooks(self.root, runtime)["Stop"][0]["hooks"][0]["command"]
            proc = subprocess.run(command, shell=True, cwd=subdir, text=True, capture_output=True,
                                  env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            args = json.loads(proc.stdout)
            self.assertEqual(args[:4], ["--runtime", runtime, "--event", "Stop"])
            self.assertEqual(Path(args[-1]).resolve(), self.root.resolve())

    def test_invalid_second_settings_does_not_partially_write(self):
        claude = self.write_json(".claude/settings.json", {"permissions": {}})
        self.write_json(".codex/hooks.json", {"hooks": []})
        before = claude.read_bytes()
        result = self.run_cli("--apply")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(claude.read_bytes(), before)
        self.assertFalse((self.root / "docs").exists())

    def test_manifest_rejects_unsupported_codex_event(self):
        path = self.root / "config/crew-hooks.json"
        manifest = json.loads(path.read_text())
        manifest["runtimes"]["codex"]["events"].append("TaskCompleted")
        path.write_text(json.dumps(manifest))
        self.assertEqual(self.run_cli("--check").returncode, 2)

    def test_manifest_rejects_retired_user_prompt_event(self):
        path = self.root / "config/crew-hooks.json"
        manifest = json.loads(path.read_text())
        manifest["runtimes"]["codex"]["events"].append("UserPromptSubmit")
        path.write_text(json.dumps(manifest))
        self.assertEqual(self.run_cli("--check").returncode, 2)

    def test_marker_with_custom_command_or_wrong_event_is_preserved(self):
        generated = installer.generated_hooks(self.root, "codex")
        custom = dict(generated["Stop"][0]["hooks"][0], command="echo custom")
        wrong_event = generated["SessionStart"][0]["hooks"][0]
        existing = {"hooks": {"Stop": [{"hooks": [custom, wrong_event]}]}}
        result = installer.merge_settings(existing, generated, "codex")
        self.assertEqual(result["hooks"]["Stop"][1]["hooks"], [custom, wrong_event])

    def test_snapshot_conflict_before_apply_leaves_all_files_intact(self):
        claude = self.write_json(".claude/settings.json", {"permissions": {}})
        codex = self.write_json(".codex/hooks.json", {"hooks": {}})
        original_claude = claude.read_bytes()
        original_snapshot = installer.snapshot
        reads = 0

        def concurrent_snapshot(path):
            nonlocal reads
            reads += 1
            if reads == 3:
                codex.write_text('{"concurrent": true}')
            return original_snapshot(path)

        stderr = io.StringIO()
        with mock.patch.object(installer, "snapshot", side_effect=concurrent_snapshot), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            result = installer.main(["--root", str(self.root), "--apply"])
        self.assertEqual(result, 2)
        self.assertEqual(claude.read_bytes(), original_claude)
        self.assertEqual(codex.read_text(), '{"concurrent": true}')
        self.assertFalse((self.root / "docs").exists())
        self.assertIn("--check", stderr.getvalue())

    def test_partial_apply_keeps_concurrent_edit_and_backups(self):
        claude = self.write_json(".claude/settings.json", {"permissions": {}})
        codex = self.write_json(".codex/hooks.json", {"hooks": {}})
        before = {".claude/settings.json": claude.read_bytes(), ".codex/hooks.json": codex.read_bytes()}
        original_replace = os.replace
        calls = []

        def concurrent_replace(source, target):
            self.assertEqual(source.parent, target.parent)
            self.assertEqual(target.read_bytes(), before[".claude/settings.json"])
            json.loads(source.read_text())
            calls.append(target)
            original_replace(source, target)
            codex.write_text('{"concurrent": true}')

        stderr = io.StringIO()
        with mock.patch.object(installer.os, "replace", side_effect=concurrent_replace), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            result = installer.main(["--root", str(self.root), "--apply"])
        self.assertEqual(result, 2)
        self.assertEqual(calls, [claude])
        self.assertIn("Stop", json.loads(claude.read_text())["hooks"])
        self.assertEqual(codex.read_text(), '{"concurrent": true}')
        backup = next((self.root / "docs/codex-direct/backups").glob("shared-*"))
        for relative, content in before.items():
            self.assertEqual((backup / relative).read_bytes(), content)
        self.assertIn(str(backup), stderr.getvalue())
        self.assertIn("--check", stderr.getvalue())
        self.assertIn("--apply", stderr.getvalue())
        self.assertEqual(list(self.root.rglob(".crew-hooks-*")), [])

    def test_atomic_replace_failure_preserves_original_and_cleans_temp(self):
        path = self.write_json(".codex/hooks.json", {"hooks": {}})
        before = path.read_bytes()
        with mock.patch.object(installer.os, "replace", side_effect=OSError("replace失敗")):
            with self.assertRaises(OSError):
                installer.atomic_write(path, '{"new": true}', before)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob(".crew-hooks-*")), [])


if __name__ == "__main__":
    unittest.main()
