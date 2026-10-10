"""共通判定と両ランタイムのwire契約を隔離fixtureで検証。"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("crew_hooks", ROOT / "scripts/crew_hooks.py")
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)


def task(slug="a", status="IN_PROGRESS", **kw):
    return dict(slug=slug, status=status, **kw)


class CoreTests(unittest.TestCase):
    def test_scope_blocks_only_parent_once(self):
        q = {"tasks": [task(), task("b", "DONE")]}
        self.assertIn("a", hooks.evaluate(q, "Stop", "a")["block"])
        self.assertIsNone(hooks.evaluate(q, "SubagentStop", "a")["block"])
        self.assertIsNone(hooks.evaluate(q, "Stop")["block"])
        again = hooks.evaluate(q, "Stop", "a", True)
        self.assertIsNone(again["block"])
        self.assertTrue(any("未解決" in n for n in again["notes"]))

    def test_qa_rejected_done_is_not_complete(self):
        q = {"tasks": [task(status="DONE", qa_mode="inline", qa_result="CHANGES_REQUESTED")]}
        self.assertIsNotNone(hooks.evaluate(q, "Stop", "a")["block"])
        self.assertFalse(any("全タスクDONE" in n for n in hooks.evaluate(q, "Stop")["notes"]))
        q["tasks"][0]["qa_result"] = "APPROVED"
        self.assertIsNone(hooks.evaluate(q, "Stop", "a")["block"])
        self.assertTrue(any("全タスクDONE" in n for n in hooks.evaluate(q, "Stop")["notes"]))

    def test_empty_unknown_and_blocked_do_not_claim_completion(self):
        self.assertIn("完了とは判定しない", hooks.evaluate({"tasks": []}, "Stop")["notes"][0])
        self.assertIsNone(hooks.evaluate({"tasks": [task(status="BLOCKED")]}, "Stop", "a")["block"])
        unknown = hooks.evaluate({"tasks": [task()]}, "Stop", "missing")
        self.assertIsNone(unknown["block"])
        self.assertTrue(any("存在しない" in n for n in unknown["notes"]))

    def test_ready_requires_dependencies_and_their_qa(self):
        q = {"tasks": [task(status="DONE", qa_mode="inline"), task("b", "READY_FOR_RIKU", depends_on=["a"])]}
        self.assertFalse(any("着手可能" in n for n in hooks.evaluate(q, "Stop")["notes"]))
        q["tasks"][0]["qa_result"] = "APPROVED"
        self.assertTrue(any("着手可能: b" in n for n in hooks.evaluate(q, "Stop")["notes"]))

    def test_retro_marker_and_warning(self):
        q = {"tasks": [task(status="DONE"), task("retro", "TODO")]}
        self.assertTrue(any("レトロ未完了" in n for n in hooks.evaluate(q, "Stop")["notes"]))
        self.assertFalse(any("レトロ未完了" in n for n in hooks.evaluate(q, "Stop", retro_marker=True)["notes"]))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="crew hooks ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / ".claude").mkdir()
        (self.root / "config").mkdir()
        (self.root / "config/crew-hooks.json").write_text('{"checks":{}}')
        self.queue = self.root / ".claude/_queue.json"
        self.queue.write_text(json.dumps({"tasks": [task()]}))

    def invoke(self, runtime, event, payload):
        return subprocess.run([sys.executable, str(ROOT / "scripts/crew_hooks.py"), "--runtime", runtime, "--event", event, "--root", str(self.root)], input=json.dumps(payload), text=True, capture_output=True, cwd=self.root, env={"PATH": "/usr/bin:/bin"}, timeout=10)

    def test_runtime_event_matrix_json_and_no_write(self):
        before = self.queue.read_bytes()
        for runtime in ("claude", "codex"):
            for event in ("SessionStart", "Stop", "SubagentStop"):
                with self.subTest(runtime=runtime, event=event):
                    r = self.invoke(runtime, event, {"cwd": str(self.root), "hook_event_name": event})
                    self.assertEqual(r.returncode, 0, r.stderr)
                    data = json.loads(r.stdout)
                    if event == "SessionStart":
                        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], event)
                    else:
                        self.assertIn("systemMessage", data)
        self.assertEqual(before, self.queue.read_bytes())
        self.assertFalse((self.root / ".claude/_signals.jsonl").exists())

    def test_bad_payload_does_not_leak(self):
        for payload in ([], {"cwd": "secret-sk-example"}, {"stop_hook_active": "secret-sk-example"}):
            r = self.invoke("codex", "Stop", payload)
            self.assertIn("判定不能", json.loads(r.stdout)["reason"])
            self.assertNotIn("secret-sk-example", r.stdout + r.stderr)

    def test_bad_queue_and_duplicate_slugs_fail_visibly(self):
        for content in ('secret-broken-json', json.dumps({"tasks": [task(), task()]})):
            self.queue.write_text(content)
            r = self.invoke("claude", "Stop", {})
            self.assertIn("判定不能", r.stdout)
            self.assertEqual(json.loads(r.stdout)["decision"], "block")
            self.assertNotIn("secret-broken", r.stdout)
            again = self.invoke("claude", "Stop", {"stop_hook_active": True})
            self.assertNotIn("decision", json.loads(again.stdout))
            self.assertIn("判定不能", json.loads(again.stdout)["systemMessage"])

    def test_retired_prompt_event_is_compatible_noop(self):
        r = self.invoke("codex", "UserPromptSubmit", {"cwd": str(self.root)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {})

    def test_task_id_is_not_guessed(self):
        before = self.queue.read_bytes()
        r = self.invoke("claude", "TaskCompleted", {"task_id": "other"})
        self.assertIn("対応未確認", r.stdout)
        self.assertEqual(before, self.queue.read_bytes())
        self.assertIn("判定不能", self.invoke("codex", "TaskCompleted", {}).stdout)

    def test_wrong_root_scope_warns_without_blocking(self):
        result = hooks.run("codex", "Stop", {}, self.root, {"CREW_TASK_SLUG": "a", "CREW_TASK_ROOT": "/other"})
        self.assertNotIn("decision", result)
        self.assertIn("repoが不一致", result["systemMessage"])

    def test_session_start_is_bounded_and_scoped(self):
        self.queue.write_text(json.dumps({"tasks": [task(f"task-{i}", "TODO") for i in range(100)]}))
        result = hooks.run("codex", "SessionStart", {}, self.root,
                           {"CREW_TASK_SLUG": "task-42", "CREW_TASK_ROOT": str(self.root)})
        message = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("担当タスク: task-42 [TODO]", message)
        self.assertIn("未完了100件", message)
        self.assertIn("起動時snapshot", message)
        self.assertIn("bash scripts/queue.sh show", message)
        self.assertLess(len(message), 500)
        self.assertNotIn("task-99", message)

    def test_stop_reads_queue_current_value_and_spawns_nothing(self):
        self.invoke("codex", "SessionStart", {})
        self.queue.write_text(json.dumps({"tasks": [task(status="DONE", qa_mode="inline", qa_result="CHANGES_REQUESTED")]}))
        with patch("subprocess.Popen", side_effect=AssertionError("spawn")):
            first = hooks.run("codex", "Stop", {}, self.root,
                              {"CREW_TASK_SLUG": "a", "CREW_TASK_ROOT": str(self.root)})
            again = hooks.run("codex", "Stop", {"stop_hook_active": True}, self.root,
                              {"CREW_TASK_SLUG": "a", "CREW_TASK_ROOT": str(self.root)})
        self.assertEqual(first["decision"], "block")
        self.assertIn("QA未承認", again["systemMessage"])
        self.assertIn("継続後も未解決", again["systemMessage"])
        self.assertNotIn("decision", again)

    def test_stop_ignores_legacy_check_flags(self):
        (self.root / "config/crew-hooks.json").write_text('{"checks":{"privacy":true,"lesson_candidates":true}}')
        with patch("subprocess.Popen", side_effect=AssertionError("spawn")):
            result = hooks.run("codex", "Stop", {}, self.root, {})
        self.assertIn("作業中", result["systemMessage"])

    def test_privacy_summary_redacts_values_and_file_names(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / "private-person-name.txt").write_text("secret-person@example.invalid\n")
        subprocess.run(["git", "-C", str(self.root), "add", "private-person-name.txt"], check=True, capture_output=True)
        result = subprocess.run(["/bin/bash", str(ROOT / "scripts/privacy-check.sh"), "--summary"], cwd=self.root, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater(json.loads(result.stdout)["findings"], 0)
        self.assertNotIn("secret-person", result.stdout + result.stderr)
        self.assertNotIn("private-person", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
