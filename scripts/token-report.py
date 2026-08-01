#!/usr/bin/env python3
"""
token-report.py — 部門（リポジトリ）別トークン週次集計

~/.claude/projects/ 配下の各プロジェクトディレクトリ（Claude Code のセッション記録）を
DEPARTMENTS の設定に従って部門にマッピングし、直近N日間のトークン消費を部門別・
プロジェクト別に集計して Markdown レポートを出力する。

用途: 参謀長（Rin）が週次経営会議のトークン会計セクション（.claude/agents/coo.md 責務3）に使う。

## 集計上の注意（実データ調査で判明した点）
トランスクリプト JSONL の1つの assistant API 呼び出しは、thinking/tool_use などの
content ブロックごとに複数行へ分割されて記録される。これらは同一の message.id を持ち、
usage はストリーミング途中経過のため行ごとに値が異なる場合がある（後の行ほど値が大きい）。
そのため message.id ごとに「最も新しいタイムスタンプの行」だけを採用し、重複カウントを防ぐ。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

PROJECTS_ROOT = Path.home() / ".claude" / "projects"

# プロジェクトディレクトリ名（部分一致） → 部門名。上から順に最初に一致したものを採用する。
# どれにも一致しない場合は DEFAULT_DEPARTMENT に分類する。
DEPARTMENTS: list[tuple[str, str]] = [
    ("agent-crew", "product"),
    ("alpha-predict", "invest"),
    # NOTE: 汎用語の部分一致は誤マッチしやすいため、部門追加時はプロジェクト名に
    # 固有の文字列（リポジトリ名など）をパターンに使うこと（QA Sprint-24 指摘）
]
DEFAULT_DEPARTMENT = "other"

ANOMALY_THRESHOLD_PCT = 50.0  # 前期間比 +50% 超で⚠を付ける
TOP_PROJECTS_PER_DEPT = 5  # 部門別内訳で表示するプロジェクト数の上限


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def cache_tokens(self) -> int:
        return self.cache_creation_tokens + self.cache_read_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_tokens

    def add(self, other: "UsageTotals") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_tokens += other.cache_creation_tokens
        self.cache_read_tokens += other.cache_read_tokens


def parse_timestamp(raw: str) -> Optional[datetime]:
    """ISO8601（末尾Z、ミリ秒あり/なし）を aware datetime (UTC) に変換する。失敗時は None。"""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def department_for(project_dir_name: str) -> str:
    for pattern, dept in DEPARTMENTS:
        if pattern in project_dir_name:
            return dept
    return DEFAULT_DEPARTMENT


def project_display_name(project_dir_name: str) -> str:
    """エンコード済みディレクトリ名からホームディレクトリ由来の冗長な接頭辞を除去して読みやすくする。

    Claude Code はプロジェクトパスの "/" だけでなく "_" も "-" に置換してディレクトリ名を
    作るため（例: /Users/ando_shunsuke → -Users-ando-shunsuke-...）、比較用の接頭辞も
    同様に置換してから比較する。
    """
    home_encoded = str(Path.home()).replace("/", "-").replace("_", "-")
    prefix = home_encoded + "-"
    if project_dir_name.startswith(prefix):
        return project_dir_name[len(prefix):]
    return project_dir_name


def iter_dedup_usage_events(project_dir: Path, errors: list[str]):
    """
    プロジェクトディレクトリ配下の全 *.jsonl（サブエージェント含め再帰的に）を走査し、
    (timestamp, UsageTotals) を yield する。

    同一 message.id は複数行に分かれて出現する（content ブロック分割・ストリーミング途中経過）ため、
    message.id ごとに最新タイムスタンプの行だけを採用してから yield する。
    """
    latest: dict[str, tuple[datetime, UsageTotals]] = {}
    for jsonl_path in sorted(project_dir.rglob("*.jsonl")):
        try:
            with jsonl_path.open(encoding="utf-8") as fh:
                for line_no, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        errors.append(f"{jsonl_path}:{line_no}: JSON decode error: {e}")
                        continue

                    message = record.get("message")
                    if not isinstance(message, dict) or message.get("role") != "assistant":
                        continue
                    usage = message.get("usage")
                    if not isinstance(usage, dict):
                        continue

                    message_id = message.get("id")
                    ts_raw = record.get("timestamp")
                    ts = parse_timestamp(ts_raw) if isinstance(ts_raw, str) else None
                    if message_id is None or ts is None:
                        errors.append(f"{jsonl_path}:{line_no}: message.id または timestamp が欠落、スキップ")
                        continue

                    totals = UsageTotals(
                        input_tokens=int(usage.get("input_tokens") or 0),
                        output_tokens=int(usage.get("output_tokens") or 0),
                        cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
                        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
                    )
                    existing = latest.get(message_id)
                    if existing is None or ts > existing[0]:
                        latest[message_id] = (ts, totals)
        except OSError as e:
            errors.append(f"{jsonl_path}: read error: {e}")
            continue
    return latest.values()


@dataclass
class PeriodTotals:
    dept_current: dict = None
    dept_previous: dict = None
    proj_current: dict = None
    proj_previous: dict = None

    def __post_init__(self):
        self.dept_current = defaultdict(UsageTotals)
        self.dept_previous = defaultdict(UsageTotals)
        self.proj_current = defaultdict(UsageTotals)
        self.proj_previous = defaultdict(UsageTotals)


def collect_totals(days: int, errors: list[str]) -> tuple[PeriodTotals, datetime, datetime, datetime]:
    """
    直近 days 日（当期間）とその直前 days 日（前期間）のトークン使用量を、
    ~/.claude/projects/ 配下を1回走査して部門別・プロジェクト別に集計する。
    """
    now = datetime.now(timezone.utc)
    cur_start = now - timedelta(days=days)
    prev_start = cur_start - timedelta(days=days)

    result = PeriodTotals()

    if not PROJECTS_ROOT.exists():
        errors.append(f"projects root not found: {PROJECTS_ROOT}")
        return result, prev_start, cur_start, now

    for project_dir in sorted(PROJECTS_ROOT.iterdir()):
        if not project_dir.is_dir():
            continue
        dept = department_for(project_dir.name)
        display_name = project_display_name(project_dir.name)

        for ts, totals in iter_dedup_usage_events(project_dir, errors):
            if cur_start <= ts < now:
                result.dept_current[dept].add(totals)
                result.proj_current[(dept, display_name)].add(totals)
            elif prev_start <= ts < cur_start:
                result.dept_previous[dept].add(totals)
                result.proj_previous[(dept, display_name)].add(totals)
            # 前期間より古いイベントはレポート対象外

    return result, prev_start, cur_start, now


def format_int(n: int) -> str:
    return f"{n:,}"


def pct_change(current: int, previous: int) -> Optional[float]:
    """前期間比（%）。前期間が0で当期間も0なら None（変化なし扱い）、前期間が0で当期間>0なら inf（新規）。"""
    if previous == 0:
        return None if current == 0 else float("inf")
    return (current - previous) / previous * 100


def format_pct(pct: Optional[float]) -> str:
    if pct is None:
        return "—"
    if pct == float("inf"):
        return "新規"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def anomaly_marker(pct: Optional[float]) -> str:
    if pct is not None and pct != float("inf") and pct > ANOMALY_THRESHOLD_PCT:
        return " ⚠"
    return ""


def build_report(result: PeriodTotals, prev_start: datetime, cur_start: datetime, now: datetime, days: int) -> str:
    lines: list[str] = []
    lines.append(f"# トークン週次集計レポート")
    lines.append("")
    lines.append(f"- 生成日時: {now.strftime('%Y-%m-%d %H:%M')} UTC")
    lines.append(f"- 当期間: {cur_start.strftime('%Y-%m-%d')} 〜 {now.strftime('%Y-%m-%d')}（直近{days}日）")
    lines.append(f"- 前期間: {prev_start.strftime('%Y-%m-%d')} 〜 {cur_start.strftime('%Y-%m-%d')}（比較対象・直前{days}日）")
    lines.append("")

    # ---------- 部門別テーブル ----------
    lines.append("## 部門別トークン消費")
    lines.append("")
    lines.append("| 部門 | Input | Output | Cache | 合計 | 前期間比 |")
    lines.append("|------|------:|-------:|------:|-----:|----------|")

    all_depts = set(result.dept_current.keys()) | set(result.dept_previous.keys())
    dept_rows = sorted(all_depts, key=lambda d: result.dept_current[d].total_tokens, reverse=True)

    if not dept_rows:
        lines.append("| （データなし） | — | — | — | — | — |")
    for dept in dept_rows:
        cur = result.dept_current[dept]
        prev = result.dept_previous[dept]
        pct = pct_change(cur.total_tokens, prev.total_tokens)
        lines.append(
            f"| {dept} | {format_int(cur.input_tokens)} | {format_int(cur.output_tokens)} | "
            f"{format_int(cur.cache_tokens)} | {format_int(cur.total_tokens)} | "
            f"{format_pct(pct)}{anomaly_marker(pct)} |"
        )
    lines.append("")

    # ---------- プロジェクト別内訳（部門ごと上位N件） ----------
    lines.append("## プロジェクト別内訳（部門ごと上位{}件）".format(TOP_PROJECTS_PER_DEPT))
    lines.append("")

    for dept in dept_rows:
        projects_in_dept = [
            (name, result.proj_current[(d, name)])
            for (d, name) in result.proj_current.keys()
            if d == dept
        ]
        projects_in_dept.sort(key=lambda item: item[1].total_tokens, reverse=True)
        top = projects_in_dept[:TOP_PROJECTS_PER_DEPT]
        if not top:
            continue

        lines.append(f"### {dept}")
        lines.append("")
        lines.append("| プロジェクト | Input | Output | Cache | 合計 | 前期間比 |")
        lines.append("|--------------|------:|-------:|------:|-----:|----------|")
        for name, cur in top:
            prev = result.proj_previous.get((dept, name), UsageTotals())
            pct = pct_change(cur.total_tokens, prev.total_tokens)
            lines.append(
                f"| {name} | {format_int(cur.input_tokens)} | {format_int(cur.output_tokens)} | "
                f"{format_int(cur.cache_tokens)} | {format_int(cur.total_tokens)} | "
                f"{format_pct(pct)}{anomaly_marker(pct)} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="部門（リポジトリ）別トークン週次集計レポートを生成する")
    parser.add_argument("--days", type=int, default=7, help="集計対象期間（日数）。デフォルト7日")
    parser.add_argument("--out", type=str, default=None, help="出力先Markdownファイルパス。省略時は標準出力")
    args = parser.parse_args()

    if args.days <= 0:
        print("ERROR: --days は正の整数を指定してください", file=sys.stderr)
        return 1

    errors: list[str] = []
    result, prev_start, cur_start, now = collect_totals(args.days, errors)
    report = build_report(result, prev_start, cur_start, now, args.days)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report + "\n", encoding="utf-8")
        print(f"OK: レポートを書き出しました: {out_path}", file=sys.stderr)
    else:
        print(report)

    if errors:
        print(f"WARN: 集計中に {len(errors)} 件の問題が発生しました:", file=sys.stderr)
        for e in errors[:50]:
            print(f"  - {e}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... 他 {len(errors) - 50} 件", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
