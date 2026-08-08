"""
tests/test_queue_done_git_guard.py — queue.py done の未コミット警告テスト

agent-crew-sprint-27-reliability-003（未コミット作業の保護漏れ）の恒久対応
（learning-loop-verification-proposal.md L1-2）の検証:
- 作業ツリーに未コミット差分がある状態で done → stderr に WARNING
- クリーンな作業ツリーで done → WARNING なし
- git リポジトリ外の queue でも done 自体は成功する（警告は best-effort）
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

QUEUE_TEMPLATE = {
    "sprint": "test-sprint",
    "tasks": [
        {
            "slug": "task-a",
            "title": "Task A",
            "status": "IN_PROGRESS",
            "assigned_to": "Riku",
            "complexity": "S",
            "risk_level": "low",
            "parallel_group": None,
            "depends_on": [],
            "qa_mode": None,
            "created_at": "2026-08-08",
            "updated_at": "2026-08-08",
            "notes": "",
            "retry_count": 0,
            "qa_result": None,
            "summary": None,
            "events": [],
        }
    ],
}


def run_done(queue_file: Path) -> subprocess.CompletedProcess:
    uv = str(Path.home() / ".local/bin/uv")
    env = {**os.environ, "QUEUE_FILE": str(queue_file)}
    return subprocess.run(
        [uv, "run", str(REPO_ROOT / "scripts" / "queue.py"), "done", "task-a", "Riku", "完了"],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """queue ファイルを含む一時 git リポジトリ（初期状態はクリーン）"""
    repo = tmp_path / "repo"
    claude_dir = repo / ".claude"
    claude_dir.mkdir(parents=True)
    queue_file = claude_dir / "_queue.json"
    queue_file.write_text(json.dumps(QUEUE_TEMPLATE, ensure_ascii=False))
    # done 自身が書き込む .claude/（_queue.json / _signals.jsonl）は追跡対象外にして
    # 「done 実行以外の未コミット差分」だけを検出対象にする
    (repo / ".gitignore").write_text(".claude/\n")
    (repo / "README.md").write_text("# test repo\n")

    def git(*args):
        subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True,
            env={**os.environ,
                 "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"},
        )

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    return repo


class TestDoneGitGuard:
    def test_warns_on_uncommitted_changes(self, git_repo):
        queue_file = git_repo / ".claude" / "_queue.json"
        (git_repo / "orphan.py").write_text("# 未コミット成果物\n")
        result = run_done(queue_file)
        assert result.returncode == 0, result.stderr
        assert "OK: task-a → DONE" in result.stdout
        assert "未コミットの変更" in result.stderr

    def test_no_warning_when_clean(self, git_repo):
        queue_file = git_repo / ".claude" / "_queue.json"
        result = run_done(queue_file)
        assert result.returncode == 0, result.stderr
        assert "OK: task-a → DONE" in result.stdout
        assert "未コミットの変更" not in result.stderr

    def test_done_succeeds_outside_git_repo(self, tmp_path):
        # git 管理外でも done は成功し、警告も出ない（best-effort）
        claude_dir = tmp_path / "no-git" / ".claude"
        claude_dir.mkdir(parents=True)
        queue_file = claude_dir / "_queue.json"
        queue_file.write_text(json.dumps(QUEUE_TEMPLATE, ensure_ascii=False))
        result = run_done(queue_file)
        assert result.returncode == 0, result.stderr
        assert "OK: task-a → DONE" in result.stdout
        assert "未コミットの変更" not in result.stderr
