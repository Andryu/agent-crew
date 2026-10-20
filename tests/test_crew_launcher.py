"""起動scopeの寿命と設定レイヤー選択を検証する。"""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
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

    def test_direct_launch_from_old_python_reexecs_or_stops_clearly(self):
        # macOS標準python3（3.9）からの直接起動でもtomllib不足で落ちず、3.11+へ切り替える。
        old = Path("/usr/bin/python3")
        if not old.exists() or subprocess.run([old, "-c", "import sys; sys.exit(sys.version_info >= (3, 11))"]).returncode:
            self.skipTest("3.11未満のpython3がない環境")
        # module読込時にcodex_hook_state（tomllib）をimportするため、claude分岐の成功で3.11+への切替を証明できる。
        # codex分岐はrepo固有のhook state（fresh cloneには含めない）に依存するため、launch_specのunit testで検査する。
        result = subprocess.run([old, ROOT / "scripts/crew", "--print-command", "claude"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"cwd": str(ROOT), "command": ["claude", "--setting-sources", "project"],
                                                     "scope": {}})
        refused = subprocess.run([old, ROOT / "scripts/crew", "--print-command", "claude"], capture_output=True,
                                 text=True, check=False, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(refused.returncode, 1)
        self.assertIn("Python 3.11以上", refused.stderr)


if __name__ == "__main__":
    unittest.main()
