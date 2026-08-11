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


# ---------- V3-1: supersedes 存在チェック ----------

class TestSupersedesExistence:
    def test_unknown_supersedes_rejected(self, lessons_file):
        result = add_failure(lessons_file, extra=[
            "--recurrence-condition", "同型の事象が発生しない",
            "--supersedes", "no-such-id",
        ])
        assert result.returncode == 1
        assert "--supersedes: lesson not found" in result.stderr

    def test_existing_supersedes_accepted(self, lessons_file):
        first = add_failure(lessons_file, extra=["--recurrence-condition", "同型の事象が発生しない"])
        assert first.returncode == 0, first.stderr
        old_id = read_lessons(lessons_file)[0]["id"]

        result = add_failure(lessons_file, extra=[
            "--recurrence-condition", "改訂後の再発条件を満たす",
            "--supersedes", old_id,
        ])
        assert result.returncode == 0, result.stderr
        assert read_lessons(lessons_file)[-1]["supersedes"] == old_id


# ---------- V3-2: 信頼境界（owner_approved / source_repo フィルタ） ----------

class TestTrustBoundary:
    OWN = "https://github.com/Andryu/agent-crew"
    EXT = "https://github.com/Andryu/other-app"

    def _add(self, lessons_file, *, repo, approved=False, category="process"):
        args = [
            "add", "--project", "p", "--sprint", "sprint-27", "--category", category,
            "--severity", "3", "--frequency", "2",
            "--description", "信頼境界テスト用の観察エントリ", "--action", "テスト用の対策アクション",
            "--recurrence-condition", "同型の事象が発生しない",
            "--source-repo", repo,
        ]
        if approved:
            args.append("--owner-approved")
        r = run_lessons(args, lessons_file)
        assert r.returncode == 0, r.stderr
        return read_lessons(lessons_file)[-1]["id"]

    def test_owner_approved_defaults_false(self, lessons_file):
        self._add(lessons_file, repo=self.OWN)
        assert read_lessons(lessons_file)[0]["owner_approved"] is False

    def test_owner_approved_flag_sets_true(self, lessons_file):
        self._add(lessons_file, repo=self.EXT, approved=True)
        assert read_lessons(lessons_file)[0]["owner_approved"] is True

    def _run_propose(self, lessons_file, tmp_path):
        """自リポジトリを agent-crew とする一時 git リポジトリで dry-run 実行"""
        work = tmp_path / "work"
        agents = work / ".claude" / "agents"
        agents.mkdir(parents=True)
        for name in ("pm.md", "qa.md"):
            (agents / name).write_text(f"# {name}\n")
        subprocess.run(["git", "init", "-q"], cwd=work, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/Andryu/agent-crew.git"],
            cwd=work, check=True, capture_output=True,
        )
        env = {**os.environ, "LESSONS_FILE": str(lessons_file)}
        return subprocess.run(
            ["bash", str(PROPOSE_SH), "--dry-run", "--min-priority", "3"],
            capture_output=True, text=True, env=env, cwd=work,
        )

    def test_external_unapproved_excluded(self, lessons_file, tmp_path):
        own_id = self._add(lessons_file, repo=self.OWN)
        ext_id = self._add(lessons_file, repo=self.EXT)
        r = self._run_propose(lessons_file, tmp_path)
        assert r.returncode == 0, r.stderr
        combined = r.stdout + r.stderr
        # ルール本体として書き出されるのは「### <id>」の見出し行
        assert f"### {own_id}" in combined, "自リポジトリ由来は書き出し対象であるべき"
        assert f"### {ext_id}" not in combined, "外部由来・未承認はルール書き出しされないべき"
        # 除外はサイレントでなく明示的に報告される
        assert "信頼境界により除外" in combined and ext_id in combined, \
            "除外された lesson は報告に出るべき（サイレント除外の防止）"

    def test_external_approved_included(self, lessons_file, tmp_path):
        ext_id = self._add(lessons_file, repo=self.EXT, approved=True, category="qa")
        r = self._run_propose(lessons_file, tmp_path)
        assert r.returncode == 0, r.stderr
        assert ext_id in (r.stdout + r.stderr), "外部由来でも承認済みなら対象"

    def test_ssh_form_own_repo_normalized(self, lessons_file, tmp_path):
        """SSH 形式で記録された自リポジトリ由来 lesson も正規化して通過する"""
        own_id = self._add(lessons_file, repo="git@github.com:Andryu/agent-crew.git")
        r = self._run_propose(lessons_file, tmp_path)
        assert r.returncode == 0, r.stderr
        assert own_id in (r.stdout + r.stderr)


# ---------- list-rule-candidates: 抽出条件の単一実装（ドリフト防止） ----------

class TestListRuleCandidates:
    """retro.md と propose-lesson-rules.sh が共有する抽出ロジックの検証。

    このサブコマンドが唯一の実装であることが前提（jq クエリを複製すると
    正規化ロジックがドリフトし、環境によってサイレントに全件除外される）。
    """

    def _repo(self, tmp_path: Path, origin: str | None) -> Path:
        work = tmp_path / f"repo_{abs(hash(origin)) % 10000}"
        work.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=work, check=True, capture_output=True)
        if origin:
            subprocess.run(["git", "remote", "add", "origin", origin],
                           cwd=work, check=True, capture_output=True)
        return work

    def _list(self, lessons_file: Path, cwd: Path, excluded=False) -> list[str]:
        args = ["bash", str(LESSONS_SH), "list-rule-candidates"]
        if excluded:
            args.append("--excluded")
        env = {**os.environ, "LESSONS_FILE": str(lessons_file)}
        r = subprocess.run(args, capture_output=True, text=True, env=env, cwd=cwd)
        assert r.returncode == 0, r.stderr
        return [json.loads(line)["id"] for line in r.stdout.splitlines() if line.strip()]

    def _seed(self, lessons_file: Path, *, category, repo=None, approved=False,
              enforcement=None, status=None, severity="3", frequency="2"):
        args = [
            "add", "--project", "p", "--sprint", "sprint-27", "--category", category,
            "--severity", severity, "--frequency", frequency,
            "--description", "抽出条件テスト用の観察エントリ", "--action", "テスト用の対策アクション",
            "--recurrence-condition", "同型の事象が発生しない",
        ]
        if repo:
            args += ["--source-repo", repo]
        if approved:
            args.append("--owner-approved")
        if enforcement:
            args += ["--enforcement", enforcement]
        if status:
            args += ["--status", status]
        r = run_lessons(args, lessons_file)
        assert r.returncode == 0, r.stderr
        return read_lessons(lessons_file)[-1]["id"]

    @pytest.mark.parametrize("origin", [
        "https://github.com/Andryu/agent-crew.git",
        "git@github.com:Andryu/agent-crew.git",
        "ssh://git@github.com/Andryu/agent-crew.git",   # Sora MAJOR 指摘の再現条件
    ])
    def test_own_repo_passes_for_all_origin_forms(self, lessons_file, tmp_path, origin):
        """origin の表記形式（HTTPS/SSH/ssh://）に関わらず自リポジトリ由来は通過する"""
        own = self._seed(lessons_file, category="process",
                         repo="https://github.com/Andryu/agent-crew")
        assert own in self._list(lessons_file, self._repo(tmp_path, origin))

    def test_origin_missing_falls_back_to_local(self, lessons_file, tmp_path):
        """origin 未設定環境では source_repo='local' の lesson が通る（全件除外にならない）"""
        work = self._repo(tmp_path, None)
        env = {**os.environ, "LESSONS_FILE": str(lessons_file)}
        r = subprocess.run(
            ["bash", str(LESSONS_SH), "add", "--project", "p", "--sprint", "sprint-27",
             "--category", "process", "--severity", "3", "--frequency", "2",
             "--description", "origin未設定環境で記録した観察", "--action", "テスト用の対策アクション",
             "--recurrence-condition", "同型の事象が発生しない"],
            capture_output=True, text=True, env=env, cwd=work,
        )
        assert r.returncode == 0, r.stderr
        entry = read_lessons(lessons_file)[-1]
        assert entry["source_repo"] == "local"
        assert entry["id"] in self._list(lessons_file, work)

    def test_legacy_entry_without_source_repo_passes(self, lessons_file, tmp_path):
        """source_repo フィールドを持たない旧エントリを誤ってブロックしない"""
        data = json.loads(lessons_file.read_text())
        data["lessons"].append({
            "id": "legacy-001", "priority_score": 6, "type": "failure",
            "category": "process", "description": "レガシーエントリ", "action": "対策",
        })
        lessons_file.write_text(json.dumps(data, ensure_ascii=False))
        work = self._repo(tmp_path, "https://github.com/Andryu/agent-crew.git")
        assert "legacy-001" in self._list(lessons_file, work)

    def test_proposed_status_is_included(self, lessons_file, tmp_path):
        """lessons.sh add の既定 status='proposed' が抽出対象に含まれる

        （retro.md 側の旧クエリは open/null のみを見ており、既定で記録された
        lesson を全て取りこぼしていた。一元化でこの潜在バグが解消される）
        """
        lid = self._seed(lessons_file, category="process",
                         repo="https://github.com/Andryu/agent-crew")
        assert read_lessons(lessons_file)[-1]["status"] == "proposed"
        work = self._repo(tmp_path, "https://github.com/Andryu/agent-crew.git")
        assert lid in self._list(lessons_file, work)

    def test_code_enforcement_and_external_excluded(self, lessons_file, tmp_path):
        own = self._seed(lessons_file, category="process",
                         repo="https://github.com/Andryu/agent-crew")
        coded = self._seed(lessons_file, category="qa",
                           repo="https://github.com/Andryu/agent-crew", enforcement="code")
        ext = self._seed(lessons_file, category="tooling",
                         repo="https://github.com/Andryu/other-app")
        work = self._repo(tmp_path, "https://github.com/Andryu/agent-crew.git")
        passed = self._list(lessons_file, work)
        assert own in passed
        assert coded not in passed, "enforcement=code は二重管理防止のため除外"
        assert ext not in passed, "外部由来・未承認は信頼境界で除外"
        # --excluded は信頼境界で落ちたものだけを返す（enforcement=code は含まない）
        excluded = self._list(lessons_file, work, excluded=True)
        assert excluded == [ext]

    def test_min_priority_threshold(self, lessons_file, tmp_path):
        low = self._seed(lessons_file, category="process",
                         repo="https://github.com/Andryu/agent-crew",
                         severity="1", frequency="2")  # priority=2
        work = self._repo(tmp_path, "https://github.com/Andryu/agent-crew.git")
        assert low not in self._list(lessons_file, work), "既定閾値3未満は対象外"

    def test_invalid_min_priority_rejected(self, lessons_file, tmp_path):
        env = {**os.environ, "LESSONS_FILE": str(lessons_file)}
        r = subprocess.run(
            ["bash", str(LESSONS_SH), "list-rule-candidates", "--min-priority", "abc"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert r.returncode == 1
        assert "--min-priority must be a number" in r.stderr


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

        # propose-lesson-rules.sh は cwd の .claude/agents と git origin を見るため
        # 一時ディレクトリを本リポジトリと同じ origin を持つ git リポジトリとして用意する
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "pm.md").write_text("# pm\n")
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/Andryu/agent-crew.git"],
            cwd=tmp_path, check=True, capture_output=True,
        )

        env = {**os.environ, "LESSONS_FILE": str(lessons_file)}
        r = subprocess.run(
            ["bash", str(PROPOSE_SH), "--dry-run", "--min-priority", "3"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert r.returncode == 0, r.stderr
        combined = r.stdout + r.stderr
        assert prompt_id in combined
        assert code_id not in combined
