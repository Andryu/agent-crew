"""解答者向けの簡易確認（holdout とは別物・固定値）。

リポジトリ直下で実行:
    python3 -m pytest visible_test/test_visible.py -q
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

WORK = Path(os.environ.get("BENCH_WORK_DIR", "."))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(WORK / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_subagent_visible(tmp_path):
    discovery = _load("v_discovery", "dashboard/server/discovery.py")
    now = 1_800_000_000.0

    root = tmp_path / "projects"
    proj = root / "-Users-benchuser-Workspace-agent-crew"
    proj.mkdir(parents=True)
    main = proj / "sess-1.jsonl"
    main.write_text(json.dumps({"cwd": "/Users/benchuser/Workspace/agent-crew"}) + "\n")
    os.utime(main, (now - 5, now - 5))

    sub_dir = proj / "sess-1" / "subagents"
    sub_dir.mkdir(parents=True)
    sub = sub_dir / "agent-abc.jsonl"
    sub.write_text("{}\n")
    (sub_dir / "agent-abc.meta.json").write_text(json.dumps({"agentType": "qa"}))
    os.utime(sub, (now - 5, now - 5))

    sessions = discovery.find_active_sessions(root, 600.0, now=now)
    personas = sorted(
        (s.persona if s.persona is not None else "-") for s in sessions)
    assert personas == ["-", "sora"]  # メインは None、qa サブは sora
