"""01-token-dept-order holdout: パス断片 → 部門判定の振る舞いテスト。

- BENCH_WORK_DIR の解答済みリポジトリから enrich.py / token-report.py を import する。
- パスの接頭辞（ユーザー名部分）は BENCH_SEED から乱数生成する。
  分類はパス断片だけで決まるはずなので、接頭辞が変わっても結果は同じでなければ
  ならない（ランダム値注入）。
"""
import importlib.util
import os
import random
import sys
from pathlib import Path

WORK = Path(os.environ["BENCH_WORK_DIR"])
SEED = int(os.environ.get("BENCH_SEED", "12345"))
_rng = random.Random(SEED)
USER = "benchuser{}".format(_rng.randint(0, 9999))
MID = "ws{}".format(_rng.randint(0, 9999))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(WORK / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses 等がモジュールを参照できるよう登録する
    spec.loader.exec_module(mod)
    return mod


enrich = _load("bench_enrich", "dashboard/server/enrich.py")
token_report = _load("bench_token_report", "scripts/token-report.py")


def enc(path):
    """Claude Code のプロジェクトディレクトリ名エンコード（/ と _ を - に置換）。"""
    return path.replace("/", "-").replace("_", "-")


def both(path):
    """enrich（生パス）と token-report（エンコード済み名）の判定を返す。"""
    return (enrich.department_for(path), token_report.department_for(enc(path)))


def test_regression_existing_classification():
    """既存の product / invest / other 判定が変わっていないこと。"""
    assert both("/Users/{}/Workspace/agent-crew".format(USER)) == ("product", "product")
    assert both("/Users/{}/{}/alpha-predict-jp".format(USER, MID)) == ("invest", "invest")
    assert both("/Users/{}/Workspace/some-unrelated-repo".format(USER)) == ("other", "other")
    assert enrich.department_for("") == "other"


def test_game_worktree_is_game_not_product():
    """agent-crew 配下の game-department ワークツリーは game と判定されること。"""
    path = "/Users/{}/orca/workspaces/agent-crew/game-department".format(USER)
    assert both(path) == ("game", "game")


def test_stonefish_video_is_video():
    assert both("/Users/{}/Workspace/stonefish-video".format(USER)) == ("video", "video")
    assert both(
        "/Users/{}/orca/workspaces/stonefish-video/video-sprint-01".format(USER)
    ) == ("video", "video")


def test_agent_crew_sub_with_alpha_predict_stays_product():
    """agent-crew 配下に alpha-predict を含む名前があっても product のままであること
    （既存パターン同士の優先順位を崩していないか）。"""
    # 前提: 新部門が実装済みであること（未実装でも通る空虚な合格を防ぐ）
    assert both("/Users/{}/x/game-department".format(USER)) == ("game", "game")
    path = "/Users/{}/Workspace/agent-crew/alpha-predict-sub".format(USER)
    assert both(path) == ("product", "product")


def test_departments_tables_identical():
    """enrich.py と token-report.py の部門テーブルが完全一致していること。"""
    # 前提: 新部門が実装済みであること（未実装でも通る空虚な合格を防ぐ）
    assert both("/Users/{}/x/stonefish-video".format(USER)) == ("video", "video")
    assert list(enrich.DEPARTMENTS) == list(token_report.DEPARTMENTS)
