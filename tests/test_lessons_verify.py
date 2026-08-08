"""
tests/test_lessons_verify.py — lessons.sh 効果検証機能のテスト

learning-loop-verification-proposal.md L0（再発チェック基盤）の検証:
- --recurrence-condition 必須ゲート（type=failure かつ priority>=3）
- source_repo の SSH→HTTPS 正規化
- verify-check の streak 加算 / verified 自動遷移 / 再発リセット
- enforcement: code のプロンプト書き出しスキップ（propose-lesson-rules.sh）
実際の ~/.claude/_lessons.json には触れない（tmp_path フィクスチャを使用）。
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
LESSONS_SH = REPO_ROOT / "scripts" / "lessons.sh"
PROPOSE_SH = REPO_ROOT / "scripts" / "propose-lesson-rules.sh"


@pytest.fixture
def lessons_file(tmp_path: Path) -> Path:
    f = tmp_path / "_lessons.json"
    f.write_text(json.dumps({"schema_version": "1.1.0", "lessons": []}))
    return f


def run_lessons(args: list[str], lessons_file: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "LESSONS_FILE": str(lessons_file),
        "LOCK_FILE": str(lessons_file) + ".lock",
    }
    return subprocess.run(
        ["bash", str(LESSONS_SH)] + args, capture_output=True, text=True, env=env
    )


def add_failure(lessons_file: Path, *, severity="3", frequency="3", extra=None) -> subprocess.CompletedProcess:
    args = [
        "add",
        "--project", "agent-crew",
        "--sprint", "sprint-27",
        "--category", "process",
        "--severity", severity,
        "--frequency", frequency,
        "--description", "テスト用の失敗観察エントリです",
        "--action", "テスト用アクション",
    ] + (extra or [])
    return run_lessons(args, lessons_file)


def read_lessons(lessons_file: Path) -> list[dict]:
    return json.loads(lessons_file.read_text())["lessons"]


# ---------- 再発検知条件ゲート ----------

class TestRecurrenceConditionGate:
    def test_failure_high_priority_requires_condition(self, lessons_file):
        result = add_failure(lessons_file)
        assert result.returncode == 1
        assert "--recurrence-condition is required" in result.stderr

    def test_failure_high_priority_with_condition_succeeds(self, lessons_file):
        result = add_failure(lessons_file, extra=[
            "--recurrence-condition", "同型のタスク指示衝突が発生しない",
        ])
        assert result.returncode == 0, result.stderr
        entry = read_lessons(lessons_file)[0]
        assert entry["recurrence_condition"] == "同型のタスク指示衝突が発生しない"
        assert entry["verification_streak"] == 0
        assert entry["last_recurrence_sprint"] is None
        assert entry["enforcement"] == "prompt"

    def test_condition_too_short_rejected(self, lessons_file):
        result = add_failure(lessons_file, extra=["--recurrence-condition", "短い"])
        assert result.returncode == 1
        assert "at least 10 characters" in result.stderr

    def test_low_priority_failure_does_not_require_condition(self, lessons_file):
        # priority = 1×2 = 2 < 3 → ルール書き出し対象外なので条件不要
        result = add_failure(lessons_file, severity="1", frequency="2")
        assert result.returncode == 0, result.stderr

    def test_success_type_does_not_require_condition(self, lessons_file):
        result = add_failure(lessons_file, extra=["--type", "success"])
        assert result.returncode == 0, result.stderr

    def test_invalid_enforcement_rejected(self, lessons_file):
        result = add_failure(lessons_file, extra=[
            "--recurrence-condition", "同型の事象が発生しない",
            "--enforcement", "magic",
        ])
        assert result.returncode == 1
        assert "--enforcement must be" in result.stderr


# ---------- source_repo 正規化 ----------

class TestSourceRepoNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("git@github.com:Andryu/agent-crew.git", "https://github.com/Andryu/agent-crew"),
        ("ssh://git@github.com/Andryu/agent-crew.git", "https://github.com/Andryu/agent-crew"),
        ("https://github.com/Andryu/agent-crew.git", "https://github.com/Andryu/agent-crew"),
        ("https://github.com/Andryu/agent-crew", "https://github.com/Andryu/agent-crew"),
    ])
    def test_ssh_normalized_to_https(self, lessons_file, raw, expected):
        result = add_failure(lessons_file, extra=[
            "--recurrence-condition", "同型の事象が発生しない",
            "--source-repo", raw,
        ])
        assert result.returncode == 0, result.stderr
        assert read_lessons(lessons_file)[-1]["source_repo"] == expected


# ---------- verify-check ----------

class TestVerifyCheck:
    def _seed(self, lessons_file, status="implemented"):
        result = add_failure(lessons_file, extra=[
            "--recurrence-condition", "同型の事象が発生しない",
            "--status", status,
        ])
        assert result.returncode == 0, result.stderr
        return read_lessons(lessons_file)[-1]["id"]

    def test_streak_increments_then_verifies(self, lessons_file):
        lid = self._seed(lessons_file)
        r1 = run_lessons(["verify-check", "sprint-28"], lessons_file)
        assert r1.returncode == 0, r1.stderr
        assert read_lessons(lessons_file)[0]["verification_streak"] == 1
        assert read_lessons(lessons_file)[0]["status"] == "implemented"

        r2 = run_lessons(["verify-check", "sprint-29"], lessons_file)
        assert r2.returncode == 0, r2.stderr
        entry = read_lessons(lessons_file)[0]
        assert entry["verification_streak"] == 2
        assert entry["status"] == "verified"
        assert lid in r2.stdout  # verified 遷移としてサマリーに出る

    def test_recurred_resets_streak(self, lessons_file):
        lid = self._seed(lessons_file)
        run_lessons(["verify-check", "sprint-28"], lessons_file)
        r = run_lessons(["verify-check", "sprint-29", "--recurred", lid], lessons_file)
        assert r.returncode == 0, r.stderr
        entry = read_lessons(lessons_file)[0]
        assert entry["verification_streak"] == 0
        assert entry["last_recurrence_sprint"] == "sprint-29"
        assert "機械化候補" in r.stdout

    def test_recurred_after_verified_reverts_to_implemented(self, lessons_file):
        # verified 済みルールの破れ: verified → implemented へ差し戻し
        lid = self._seed(lessons_file)
        run_lessons(["verify-check", "sprint-28"], lessons_file)
        run_lessons(["verify-check", "sprint-29"], lessons_file)
        assert read_lessons(lessons_file)[0]["status"] == "verified"

        r = run_lessons(["verify-check", "sprint-30", "--recurred", lid], lessons_file)
        assert r.returncode == 0, r.stderr
        entry = read_lessons(lessons_file)[0]
        assert entry["status"] == "implemented"
        assert entry["verification_streak"] == 0
        assert entry["last_recurrence_sprint"] == "sprint-30"

    def test_same_sprint_lessons_excluded(self, lessons_file):
        # 現スプリントに記録されたばかりの lesson は streak 加算対象外
        self._seed(lessons_file)
        r = run_lessons(["verify-check", "sprint-27"], lessons_file)
        assert r.returncode == 0, r.stderr
        assert read_lessons(lessons_file)[0]["verification_streak"] == 0

    def test_low_priority_excluded(self, lessons_file):
        result = add_failure(lessons_file, severity="1", frequency="2", extra=["--status", "implemented"])
        assert result.returncode == 0
        run_lessons(["verify-check", "sprint-28"], lessons_file)
        assert read_lessons(lessons_file)[0]["verification_streak"] == 0

    def test_unknown_recurred_id_fails(self, lessons_file):
        self._seed(lessons_file)
        r = run_lessons(["verify-check", "sprint-28", "--recurred", "no-such-id"], lessons_file)
        assert r.returncode == 1
        assert "lesson not found" in r.stderr

    def test_invalid_sprint_format_fails(self, lessons_file):
        r = run_lessons(["verify-check", "sprint28"], lessons_file)
        assert r.returncode == 1

    def test_dismissed_not_incremented(self, lessons_file):
        self._seed(lessons_file, status="dismissed")
        run_lessons(["verify-check", "sprint-28"], lessons_file)
        entry = read_lessons(lessons_file)[0]
        assert entry["verification_streak"] == 0
        assert entry["status"] == "dismissed"


# ---------- enforcement: code のプロンプト書き出しスキップ ----------

class TestEnforcementSkip:
    def test_propose_lesson_rules_skips_code_enforcement(self, lessons_file, tmp_path):
        # code / prompt の2エントリを用意
        for enforcement in ("code", "prompt"):
            result = add_failure(lessons_file, extra=[
                "--recurrence-condition", "同型の事象が発生しない",
                "--enforcement", enforcement,
            ])
            assert result.returncode == 0, result.stderr
        lessons = read_lessons(lessons_file)
        code_id = next(l["id"] for l in lessons if l["enforcement"] == "code")
        prompt_id = next(l["id"] for l in lessons if l["enforcement"] == "prompt")

        # propose-lesson-rules.sh は cwd の .claude/agents を見るため tmp に用意
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "pm.md").write_text("# pm\n")

        env = {**os.environ, "LESSONS_FILE": str(lessons_file)}
        r = subprocess.run(
            ["bash", str(PROPOSE_SH), "--dry-run", "--min-priority", "3"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert r.returncode == 0, r.stderr
        combined = r.stdout + r.stderr
        assert prompt_id in combined
        assert code_id not in combined
