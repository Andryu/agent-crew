#!/usr/bin/env python3
"""score.py — holdout テストを実行し rubric.yaml で部分点を集計する採点器。

使い方:
    python3 bench/score.py --task bench/tasks/00-queue-done-issue-close \
        --work /tmp/bench-work/00 [--seed 42] [--json result.json]

採点の考え方:
- 各チェックは rubric.yaml の checks に1項目ずつ定義される（bash または pytest）。
- チェックの成否は「振る舞い」だけで決まる（exit code・生成物・JSON のキー/値）。
- regression: true のチェックが1つでも落ちたら、そのタスクは 0 点
  （既存機能を壊した解答に部分点を与えないため）。
- スコア = 獲得点 / 満点（regression ゲート適用後）。

rubric.yaml の書式（PyYAML 非依存の限定サブセット。行頭コメントのみ可、
インラインコメント・ネスト構造は不可）:
    checks:
      - id: some_check
        type: bash            # bash | pytest
        file: holdout_test/test_00.sh
        node: test_name       # pytest のみ（ファイル内の関数名）
        points: 1             # 省略時 1
        regression: true      # 省略時 false
        optional: true        # 省略時 false。pytest が skip した場合に
                              # 分母（満点）からも除外する加点項目
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_TIMEOUT = 120  # 秒/チェック


def load_rubric(path: Path) -> list:
    """rubric.yaml（限定サブセット）を checks のリストに読み込む。"""
    checks = []
    current = None
    in_checks = False
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "checks:":
            in_checks = True
            continue
        if not in_checks:
            raise ValueError(f"{path}:{lineno}: 'checks:' より前に項目があります: {raw!r}")
        if stripped.startswith("- "):
            current = {}
            checks.append(current)
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if current is None or ":" not in stripped:
            raise ValueError(f"{path}:{lineno}: 解釈できない行: {raw!r}")
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip().strip("\"'")
        if value.lower() in ("true", "false"):
            parsed = value.lower() == "true"
        elif value.isdigit():
            parsed = int(value)
        else:
            parsed = value
        current[key] = parsed

    for c in checks:
        for required in ("id", "type", "file"):
            if required not in c:
                raise ValueError(f"{path}: check に {required} がありません: {c}")
        c.setdefault("points", 1)
        c.setdefault("regression", False)
        c.setdefault("optional", False)
    if not checks:
        raise ValueError(f"{path}: checks が空です")
    return checks


def resolve_pytest(bench_root: Path) -> list:
    """pytest 実行コマンドを決める。優先順: $BENCH_PYTEST → リポジトリの .venv → python3。"""
    env_pytest = os.environ.get("BENCH_PYTEST")
    if env_pytest:
        return env_pytest.split()
    venv_python = bench_root.parent / ".venv" / "bin" / "python"
    if venv_python.exists():
        return [str(venv_python), "-m", "pytest"]
    return [sys.executable or "python3", "-m", "pytest"]


def run_check(check: dict, task_dir: Path, work_dir: Path, seed: int,
              pytest_cmd: list, timeout: int) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"bench-{check['id']}-"))
    env = dict(os.environ)
    env.update({
        "BENCH_WORK_DIR": str(work_dir),
        "BENCH_TASK_DIR": str(task_dir),
        "BENCH_SEED": str(seed),
        "BENCH_TMP": str(tmp),
    })
    target = task_dir / str(check["file"])
    if check["type"] == "bash":
        cmd = ["bash", str(target)]
    elif check["type"] == "pytest":
        node = check.get("node")
        spec = f"{target}::{node}" if node else str(target)
        cmd = pytest_cmd + ["-q", "-p", "no:cacheprovider", spec]
    else:
        raise ValueError(f"未知の type: {check['type']}")

    try:
        proc = subprocess.run(
            cmd, cwd=str(work_dir), env=env, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        passed = proc.returncode == 0
        output = proc.stdout
        # pytest が全テストを skip した場合（例: 依存ライブラリ不在）は
        # 「合格」ではなく「skip」として区別する。optional チェックなら
        # 分母からも除外し、非 optional なら安全側で不合格として扱う。
        skipped = (
            check["type"] == "pytest"
            and proc.returncode == 0
            and " passed" not in output
            and "skipped" in output
        )
    except subprocess.TimeoutExpired:
        passed = False
        skipped = False
        output = f"TIMEOUT ({timeout}s)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if skipped:
        passed = False

    return {
        "id": check["id"],
        "type": check["type"],
        "points": check["points"],
        "regression": check["regression"],
        "optional": check["optional"],
        "passed": passed,
        "skipped": skipped,
        "output": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", required=True, help="タスクディレクトリ（rubric.yaml を含む）")
    parser.add_argument("--work", required=True, help="解答済み作業ディレクトリ")
    parser.add_argument("--seed", type=int, default=None,
                        help="乱数シード。省略時は実行ごとにランダム生成")
    parser.add_argument("--json", dest="json_out", default=None, help="結果JSONの出力先")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="チェックごとのタイムアウト秒")
    parser.add_argument("--verbose", action="store_true", help="失敗チェックの出力を表示")
    args = parser.parse_args()

    task_dir = Path(args.task).resolve()
    work_dir = Path(args.work).resolve()
    bench_root = Path(__file__).resolve().parent
    seed = args.seed if args.seed is not None else random.SystemRandom().randint(1, 10**6)

    if not (task_dir / "rubric.yaml").exists():
        print(f"ERROR: rubric.yaml がありません: {task_dir}", file=sys.stderr)
        return 2
    if not work_dir.is_dir():
        print(f"ERROR: 作業ディレクトリがありません: {work_dir}", file=sys.stderr)
        return 2

    checks = load_rubric(task_dir / "rubric.yaml")
    pytest_cmd = resolve_pytest(bench_root)

    results = []
    for check in checks:
        results.append(run_check(check, task_dir, work_dir, seed, pytest_cmd, args.timeout))

    # optional チェックが skip された場合は分母（満点）からも除外する
    counted = [r for r in results if not (r["optional"] and r["skipped"])]
    total = sum(r["points"] for r in counted)
    earned = sum(r["points"] for r in counted if r["passed"])
    regression_failed = [r["id"] for r in counted if r["regression"] and not r["passed"]]
    final = 0 if regression_failed else earned

    print(f"# 採点結果: {task_dir.name} (seed={seed})")
    for r in results:
        if r["optional"] and r["skipped"]:
            mark = "SKIP"
        elif r["passed"]:
            mark = "PASS"
        else:
            mark = "FAIL"
        gate = " [regression]" if r["regression"] else ""
        opt = " [optional/対象外]" if (r["optional"] and r["skipped"]) else ""
        print(f"  [{mark}] {r['id']} ({r['points']}pt){gate}{opt}")
        if args.verbose and not r["passed"]:
            for line in r["output"].splitlines()[-15:]:
                print(f"         | {line}")
    if regression_failed:
        print(f"  !! regression チェック失敗のため 0 点: {', '.join(regression_failed)}")
    pct = (100.0 * final / total) if total else 0.0
    print(f"  スコア: {final}/{total} ({pct:.0f}%)")

    if args.json_out:
        payload = {
            "task": task_dir.name,
            "seed": seed,
            "score": final,
            "total": total,
            "percent": pct,
            "regression_failed": regression_failed,
            "checks": [
                {k: r[k] for k in ("id", "type", "points", "regression",
                                   "optional", "passed", "skipped")}
                for r in results
            ],
        }
        Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0 if final == total else 1


if __name__ == "__main__":
    sys.exit(main())
