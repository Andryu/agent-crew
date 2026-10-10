"""接続せず、既知の開発ファイルだけを検査する。運用許可は判定しない。"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "docs/operations-baseline.json"
FILES = (
    "AGENTS.md",
    ".agents/skills/wealth-advisor/SKILL.md",
    "skills/wealth-advisor/SKILL.md",
    "src/wealth_advisor/analysis/allocation.py",
)
FUNCTIONS = {
    "summarize_by", "investable_total", "look_through_regions",
    "look_through_tech", "concentration", "unrealized_pl",
    "deviation", "rebalance_plan",
}


def check(root: Path) -> list[str]:
    """内容・差分・例外の詳細を出さず、固定の診断コードだけを返す。"""
    try:
        baseline = json.loads((root / BASELINE).read_text(encoding="utf-8"))
        if not isinstance(baseline, dict) or set(baseline) != set(FILES):
            return ["BASELINE_INVALID"]
        if any(
            not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            for value in baseline.values()
        ):
            return ["BASELINE_INVALID"]
    except (OSError, ValueError):
        return ["BASELINE_UNREADABLE"]

    problems = []
    for index, name in enumerate(FILES):
        try:
            content = (root / name).read_bytes()
        except OSError:
            problems.append(f"FILE_{index}_UNREADABLE")
            continue
        if hashlib.sha256(content).hexdigest() != baseline[name]:
            problems.append(f"FILE_{index}_CHANGED_REVIEW_REQUIRED")
        if name.endswith("allocation.py"):
            try:
                tree = ast.parse(content)
                names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
                if not FUNCTIONS <= names:
                    problems.append("CALC_FUNCTION_MISSING")
            except (SyntaxError, ValueError):
                problems.append("CALC_SYNTAX_INVALID")
    return problems


def main() -> int:
    problems = check(ROOT)
    for problem in problems:
        print(problem)
    print("静的確認: 要確認" if problems else "静的確認: 基準ファイルと一致")
    print("運用判定: 未許可・実データ未検証（接続・取得・計算は実行していません）")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
