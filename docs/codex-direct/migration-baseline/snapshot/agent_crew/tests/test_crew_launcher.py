"""起動scopeの寿命と設定レイヤー選択を検証する。"""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
loader = importlib.machinery.SourceFileLoader("crew_launcher", str(ROOT / "scripts/crew"))
spec = importlib.util.spec_from_loader(loader.name, loader)
launcher = importlib.util.module_from_spec(spec)
loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    @mock.patch.object(launcher, "launch_overrides", return_value=["-c", "features.hooks=true"])
    def test_unscoped_launch_discards_old_task(self, overrides):
        command, env = launcher.launch_spec(ROOT, "codex", [], None, {"CREW_TASK_SLUG": "old", "CREW_TASK_ROOT": "/old", "QUEUE_FILE": "/other/_queue.json", "PATH": "preserve"})
        self.assertNotIn("CREW_TASK_SLUG", env)
        self.assertNotIn("CREW_TASK_ROOT", env)
        self.assertEqual(env["PATH"], "preserve")
        self.assertEqual(env["QUEUE_FILE"], str(ROOT / ".claude/_queue.json"))
        self.assertNotIn("--disable", command)
        overrides.assert_called_once_with(ROOT, env)
        self.assertIn("features.hooks=true", command)

    def test_claude_uses_project_only(self):
        cmd, _ = launcher.launch_spec(ROOT, "claude", ["-p", "space in prompt"], None, {})
        self.assertEqual(cmd, ["claude", "--setting-sources", "project", "-p", "space in prompt"])

    @mock.patch.object(launcher, "launch_overrides", return_value=[])
    def test_scope_validated_against_launch_repo(self, overrides):
        with tempfile.TemporaryDirectory(prefix="crew launch ") as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir()
            (root / ".claude/_queue.json").write_text(json.dumps({"tasks": [{"slug": "valid", "status": "IN_PROGRESS"}]}))
            _, env = launcher.launch_spec(root, "codex", [], "valid", {})
            self.assertEqual(env["CREW_TASK_ROOT"], str(root))
            self.assertEqual(env["CREW_TASK_SLUG"], "valid")
            with self.assertRaises(ValueError):
                launcher.launch_spec(root, "codex", [], "missing", {})


if __name__ == "__main__":
    unittest.main()
