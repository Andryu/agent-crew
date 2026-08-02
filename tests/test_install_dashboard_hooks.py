"""
tests/test_install_dashboard_hooks.py — install.sh --only=dashboard-hooks ユニットテスト

STONEFISH ダッシュボード hooks（M3: 導入の仕組み）を対象プロジェクトへ配布する
コンポーネントを検証する。settings.json の既存 hooks を壊さない jq マージと、
2回実行しても重複しない冪等性が最重要の検証観点。
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).parent.parent
INSTALL_SH = REPO_DIR / "install.sh"

EXPECTED_EVENTS = [
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "Notification",
]


def run_install(target_dir: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = ["bash", str(INSTALL_SH), "--only=dashboard-hooks"] + (extra_args or []) + ["go", str(target_dir)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def read_settings(target_dir: Path) -> dict:
    return json.loads((target_dir / ".claude" / "settings.json").read_text())


# ---------- 1. settings.json が無い状態 ----------

def test_creates_settings_json_when_absent(tmp_path: Path):
    """settings.json が存在しない場合、hooks のみの新規ファイルが生成される"""
    result = run_install(tmp_path)
    assert result.returncode == 0, result.stderr

    settings = read_settings(tmp_path)
    assert set(settings["hooks"].keys()) == set(EXPECTED_EVENTS)

    for event in EXPECTED_EVENTS:
        groups = settings["hooks"][event]
        assert len(groups) == 1
        command = groups[0]["hooks"][0]["command"]
        assert event in command
        assert "emit_event.py" in command


# ---------- 2. 既存 hooks がある状態 ----------

def test_preserves_existing_hooks_and_adds_seven_events(tmp_path: Path):
    """既存 hooks（例: SubagentStop に別 command）は残り、7イベントが追加される"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    existing = {
        "hooks": {
            "SubagentStop": [
                {"matcher": "", "hooks": [{"type": "command", "command": ".claude/hooks/subagent_stop.sh"}]}
            ]
        },
        "permissions": {"allow": ["Bash(ls:*)"]},
    }
    (claude_dir / "settings.json").write_text(json.dumps(existing, ensure_ascii=False))

    result = run_install(tmp_path)
    assert result.returncode == 0, result.stderr

    settings = read_settings(tmp_path)

    # 既存の SubagentStop エントリが残っている
    subagent_stop_commands = [
        h["command"] for group in settings["hooks"]["SubagentStop"] for h in group["hooks"]
    ]
    assert ".claude/hooks/subagent_stop.sh" in subagent_stop_commands

    # 7イベント全てが登録されている
    assert set(EXPECTED_EVENTS).issubset(set(settings["hooks"].keys()))

    # 既存の permissions も保持されている
    assert settings["permissions"]["allow"] == ["Bash(ls:*)"]

    # バックアップファイルが作成されている
    backups = list(claude_dir.glob("settings.json.bak.*"))
    assert len(backups) == 1


# ---------- 3. 冪等性（2回実行しても重複しない） ----------

def test_idempotent_on_repeated_run(tmp_path: Path):
    """2回実行しても hooks が重複しない"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    existing = {
        "hooks": {
            "SubagentStop": [
                {"matcher": "", "hooks": [{"type": "command", "command": ".claude/hooks/subagent_stop.sh"}]}
            ]
        }
    }
    (claude_dir / "settings.json").write_text(json.dumps(existing, ensure_ascii=False))

    result1 = run_install(tmp_path)
    assert result1.returncode == 0, result1.stderr
    settings_after_1 = read_settings(tmp_path)

    result2 = run_install(tmp_path)
    assert result2.returncode == 0, result2.stderr
    settings_after_2 = read_settings(tmp_path)

    assert settings_after_1 == settings_after_2

    # SubagentStop は既存1件 + dashboard-hooks 1件 = 2件のまま増えない
    assert len(settings_after_2["hooks"]["SubagentStop"]) == 2

    # それ以外のイベントは dashboard-hooks の1件のみで増えない
    for event in EXPECTED_EVENTS:
        if event == "SubagentStop":
            continue
        assert len(settings_after_2["hooks"][event]) == 1


# ---------- 4. emit_event.py のコピーと実行権限 ----------

def test_copies_emit_event_with_exec_permission(tmp_path: Path):
    """emit_event.py が .claude/hooks/ にコピーされ、実行権限が付与される"""
    result = run_install(tmp_path)
    assert result.returncode == 0, result.stderr

    dst = tmp_path / ".claude" / "hooks" / "emit_event.py"
    assert dst.is_file()
    assert os.access(dst, os.X_OK)

    # コマンドパスがコピー先の実体を指している（配布元 dashboard/hooks/ ではない）
    settings = read_settings(tmp_path)
    command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert ".claude/hooks/emit_event.py" in command
    assert "dashboard/hooks/emit_event.py" not in command


# ---------- 5. usage テキストに dashboard-hooks が記載されている ----------

def test_usage_mentions_dashboard_hooks():
    """--help の component 一覧に dashboard-hooks が記載されている"""
    result = subprocess.run(
        ["bash", str(INSTALL_SH), "--help"], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "dashboard-hooks" in result.stdout


# ---------- 6. マージ後の settings.json が壊れていない ----------

def test_merged_settings_is_valid_json(tmp_path: Path):
    """マージ後の settings.json が jq empty (構文検証) を通過する"""
    result = run_install(tmp_path)
    assert result.returncode == 0, result.stderr

    settings_path = tmp_path / ".claude" / "settings.json"
    verify = subprocess.run(["jq", "empty", str(settings_path)], capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
