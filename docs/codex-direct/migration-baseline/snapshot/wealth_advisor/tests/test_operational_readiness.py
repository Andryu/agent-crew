"""資産入力を作らず、静的チェックの検出・秘匿動作を確認する。"""

import hashlib
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "readiness", Path(__file__).resolve().parents[1] / "scripts/check_operational_readiness.py"
)
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        baseline = {}
        for name in readiness.FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            content = "開発用の文書\n"
            if name.endswith("allocation.py"):
                content = "\n".join(f"def {func}(): pass" for func in sorted(readiness.FUNCTIONS))
            path.write_text(content, encoding="utf-8")
            baseline[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        path = self.root / readiness.BASELINE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(baseline), encoding="utf-8")

    def test_unchanged(self):
        self.assertEqual(readiness.check(self.root), [])

    def test_main_exit_and_private_output(self):
        for changed, expected_exit in ((False, 0), (True, 1)):
            with self.subTest(changed=changed):
                if changed:
                    (self.root / readiness.FILES[1]).write_text("PRIVATE_MARKER", encoding="utf-8")
                output = io.StringIO()
                with patch.object(readiness, "ROOT", self.root), redirect_stdout(output):
                    self.assertEqual(readiness.main(), expected_exit)
                expected_lines = []
                if changed:
                    expected_lines.append("FILE_1_CHANGED_REVIEW_REQUIRED")
                expected_lines.append("静的確認: 要確認" if changed else "静的確認: 基準ファイルと一致")
                expected_lines.append("運用判定: 未許可・実データ未検証（接続・取得・計算は実行していません）")
                self.assertEqual(output.getvalue().splitlines(), expected_lines)
                self.assertNotIn("PRIVATE_MARKER", output.getvalue())

    def test_change_does_not_echo_content(self):
        (self.root / readiness.FILES[1]).write_text("PRIVATE_MARKER", encoding="utf-8")
        self.assertEqual(readiness.check(self.root), ["FILE_1_CHANGED_REVIEW_REQUIRED"])

    def test_missing_file_fails_closed(self):
        (self.root / readiness.FILES[0]).unlink()
        self.assertEqual(readiness.check(self.root), ["FILE_0_UNREADABLE"])

    def test_invalid_baseline(self):
        for content in ("{", "[]", '{"unexpected": "value"}'):
            with self.subTest(content=content):
                (self.root / readiness.BASELINE).write_text(content, encoding="utf-8")
                self.assertTrue(readiness.check(self.root))

    def test_missing_function_and_invalid_syntax(self):
        path = self.root / readiness.FILES[3]
        path.write_text("pass", encoding="utf-8")
        self.assertIn("CALC_FUNCTION_MISSING", readiness.check(self.root))
        path.write_text("def (", encoding="utf-8")
        self.assertIn("CALC_SYNTAX_INVALID", readiness.check(self.root))


if __name__ == "__main__":
    unittest.main()
