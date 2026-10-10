#!/usr/bin/env python3
"""P0対象だけの非機密スナップショットを保存・検証する。"""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib


HERE = Path(__file__).resolve().parent
CREW = HERE.parents[2]
WEALTH = Path.home() / "Workspace/claude-agent-teams/finace/wealth-advisor"
CODEX = Path.home() / ".codex"
OUTPUT = HERE / "manifest.json"

CREW_FILES = {
    "AGENTS.md": "repo契約",
    "config/crew-hooks.json": "共通hook原本",
    "scripts/crew_hooks.py": "共通hook core",
    "scripts/install_crew_hooks.py": "共通hook installer",
    "scripts/codex_hook_state.py": "機械固有hook設定生成器",
    "scripts/crew": "agent-crew専用launcher",
    ".codex/hooks.json": "生成hook adapter",
    ".codex/config.toml": "機械固有hook信頼設定",
    "docs/codex-direct/local-hook-state.json": "機械固有hook設定台帳",
    ".claude/settings.json": "共通hook適用先",
    ".codex/agents/direct-reviewer.toml": "repo reviewer定義",
    ".agents/skills/fable-class/SKILL.md": "repo skill",
    ".agents/skills/fable-class/references/planning.md": "比較Aの指示開始版",
    ".agents/skills/fable-class/references/delegation.md": "比較Aの指示開始版",
    ".agents/skills/fable-class/references/verification.md": "比較Aの指示開始版",
    "tests/test_crew_launcher.py": "比較課題fixture",
    "tests/test_install_crew_hooks.py": "比較課題fixture",
    "tests/test_codex_hook_state.py": "比較課題fixture",
    "docs/plans/2026-09-21-codex-operating-model-replan.md": "比較課題文書入力",
    "docs/plans/2026-09-21-codex-operating-model-reviews.md": "比較課題文書fixture",
    "migration-progress/progress.py": "比較課題fixture",
    "migration-progress/README.md": "比較課題契約",
}
WEALTH_FILES = {
    "AGENTS.md": "wealth固有契約",
    "README.md": "wealth固有案内",
    "config/codex/developer.toml": "global権限テンプレート原本（現状wealth）",
    "config/codex/developer.rules": "global権限rule原本（現状wealth）",
    "config/codex/project.toml": "wealth repo権限テンプレート",
    "scripts/install_codex_permissions.py": "wealth権限installer",
    "scripts/check_codex_permissions.py": "wealth権限fixture",
    "scripts/check_codex_permission_context.py": "wealth実効権限確認",
    "scripts/check_operational_readiness.py": "wealth静的準備確認",
    "tests/test_operational_readiness.py": "wealth静的fixture",
    ".codex/config.toml": "wealth repo権限適用先",
    "docs/codex-operations.md": "wealth運用準備記録",
    "docs/codex-permissions.md": "wealth権限導入記録",
    "docs/operations-baseline.json": "wealth非個人hash基準",
}
GLOBAL_FILES = {
    "config.toml": "個人global実設定",
    "AGENTS.md": "個人global契約",
    "rules/default.rules": "個人global既存rule",
    "rules/developer.rules": "wealth installerの適用先",
    "hooks.json": "個人global hook定義",
    "hooks/aggregate-learnings.sh": "個人global hook",
    "hooks/capture-learning.sh": "個人global hook",
    "hooks/cmux-notify.sh": "個人global hook",
    "hooks/cmux-progress.sh": "個人global hook",
    "hooks/herdr-agent-state.sh": "個人global hook",
}
ALLOWED_CONFIG_KEYS = (
    "model", "model_reasoning_effort", "approval_policy", "approvals_reviewer",
    "default_permissions", "model_provider",
)


def display_path(path):
    return str(path).replace(str(Path.home()), "~", 1)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.rstrip("\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_entry(root, name, owner, tracked=None):
    path = root / name
    entry = {"path": display_path(path), "owner": owner}
    if path.is_symlink():
        entry["state"] = "symlink（内容未読）"
    elif path.is_file():
        entry.update(state="present", sha256=sha(path))
    else:
        entry["state"] = "missing"
    if tracked is not None:
        lines = git(root, "status", "--porcelain=v1", "-uall", "--", name).splitlines()
        entry["git_status"] = lines[0][:2] if lines else "clean"
        entry["git_tracked"] = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", name],
            capture_output=True, check=False,
        ).returncode == 0
    return entry


def repo_snapshot(root, selected):
    # repo全体ではtracked差分の件数だけを取り、未追跡は対象パスに限る。
    statuses = git(root, "status", "--porcelain=v1", "-uno").splitlines()
    files = [file_entry(root, name, owner, tracked=True) for name, owner in selected.items()]
    return {
        "root": display_path(root),
        "branch": git(root, "branch", "--show-current"),
        "head": git(root, "rev-parse", "HEAD"),
        "status_counts": {
            "tracked_changed": len(statuses),
            "selected_untracked": sum(file["git_status"] == "??" for file in files),
        },
        "files": files,
    }


def capture():
    crew = repo_snapshot(CREW, CREW_FILES)
    wealth = repo_snapshot(WEALTH, WEALTH_FILES)
    global_files = [file_entry(CODEX, name, owner) for name, owner in GLOBAL_FILES.items()]
    config = tomllib.loads((CODEX / "config.toml").read_text(encoding="utf-8"))
    allowed = {key: config[key] for key in ALLOWED_CONFIG_KEYS if key in config}
    if any(not isinstance(value, str) for value in allowed.values()):
        raise ValueError("許可キーに文字列以外があります。保存せず確認してください")
    skills = CODEX / "skills"
    skill_entries = sorted(path.name for path in skills.iterdir()) if skills.is_dir() else []
    pairs = (
        (WEALTH / "config/codex/developer.rules", CODEX / "rules/developer.rules"),
        (WEALTH / "config/codex/project.toml", WEALTH / ".codex/config.toml"),
    )
    return {
        "schema": 1,
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "P0開発設定のみ。認証・資産・会話ログ・対象外repoを含まない",
        "agent_crew": crew,
        "wealth_advisor": wealth,
        "global_codex": {
            "root": display_path(CODEX),
            "files": global_files,
            "allowed_config_values": allowed,
            "skills_directory": {"path": display_path(skills), "entries": skill_entries,
                                 "content": "未読。配布元と意味差はP2で確認"},
        },
        "observed_matches": [
            {"source": display_path(source), "target": display_path(target),
             "same_sha256": source.is_file() and target.is_file() and sha(source) == sha(target)}
            for source, target in pairs
        ],
        "cli_version": subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True).stdout.strip(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="このディレクトリのmanifest.jsonだけを作成")
    mode.add_argument("--check", action="store_true", help="保存済みmanifestと現在の対象を比較")
    args = parser.parse_args()
    observed = capture()
    if args.write:
        if OUTPUT.exists():
            parser.error("既存manifest.jsonを上書きしません")
        OUTPUT.write_text(json.dumps(observed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("P0 manifest固定: 対象パス・hash・非機密キーのみ")
        return
    saved = json.loads(OUTPUT.read_text(encoding="utf-8"))
    observed["captured_at"] = saved.get("captured_at")
    if observed != saved:
        parser.exit(1, "P0 manifest差異あり。対象を確認してください\n")
    print("P0 manifest一致: 対象パス・hash・非機密キーのみ")


if __name__ == "__main__":
    main()
