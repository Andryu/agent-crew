"""解答者向けの簡易確認（holdout とは別物・固定値）。

リポジトリ直下で実行:
    python3 -m pytest visible_test/test_visible.py -q
"""
import importlib.util
import os
import sys
from pathlib import Path

WORK = Path(os.environ.get("BENCH_WORK_DIR", "."))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(WORK / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses 等がモジュールを参照できるよう登録する
    spec.loader.exec_module(mod)
    return mod


def test_game_department_visible():
    enrich = _load("v_enrich", "dashboard/server/enrich.py")
    assert (
        enrich.department_for("/Users/benchuser/orca/workspaces/agent-crew/game-department")
        == "game"
    )
    assert enrich.department_for("/Users/benchuser/Workspace/agent-crew") == "product"
