#!/usr/bin/env python3
"""P5 campaignの24runと独立レビューを4ゲート・速度指標へ集計する。"""

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import statistics
import tempfile

import batch

TASKS = [f"C{i}" for i in range(1, 7)]
CONDITIONS = ("A", "B")
REPEATS = (1, 2)
REVIEW_FIELDS = (
    "acceptance_pass", "handoff_pass", "scope_pass", "review_findings",
    "reviewed_by", "reviewed_at",
)
UNKNOWN = "unknown"
UNKNOWN_TEXT = {"unknown", "pending", "tbd", "n/a", "none", "null", "not_reviewed"}
CAMPAIGN_RE = re.compile(r"p5-[0-9a-f]{16}\Z")
FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}\Z")
REVIEWER_RE = re.compile(r"[A-Za-z0-9_.:/@-]{3,128}\Z")


class AnalysisError(ValueError):
    pass


def load_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise AnalysisError(f"regular JSONではありません: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnalysisError(f"JSONを読めません: {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise AnalysisError(f"JSON rootがobjectではありません: {path.name}")
    return value


def run_key(value):
    try:
        task = value["task_id"]
        condition = value["condition"]
        repeat = value["repeat"]
    except (KeyError, TypeError) as error:
        raise AnalysisError("run/review keyが不足") from error
    if (type(task) is not str or type(condition) is not str or type(repeat) is not int or
            task not in TASKS or condition not in CONDITIONS or repeat not in REPEATS):
        raise AnalysisError(f"run/review keyが範囲外: {task}-{condition}-{repeat}")
    return task, condition, repeat


def expected_keys():
    return {(task, condition, repeat)
            for task in TASKS for condition in CONDITIONS for repeat in REPEATS}


def index_unique(values, label):
    result = {}
    for value in values:
        if not isinstance(value, dict):
            raise AnalysisError(f"{label}にobject以外があります")
        key = run_key(value)
        if key in result:
            raise AnalysisError(f"{label} key重複: {key}")
        result[key] = value
    return result


def exact_true(value):
    return value is True


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def review_complete(review):
    if not all(field in review for field in REVIEW_FIELDS):
        return False
    if not all(type(review[field]) is bool for field in ("acceptance_pass", "handoff_pass", "scope_pass")):
        return False
    findings = review["review_findings"]
    reviewer = review["reviewed_by"]
    reviewed_at = review["reviewed_at"]
    if not isinstance(findings, list) or not all(isinstance(finding, str) for finding in findings):
        return False
    if (not isinstance(reviewer, str) or reviewer.strip().casefold() in UNKNOWN_TEXT or
            not REVIEWER_RE.fullmatch(reviewer.strip())):
        return False
    if not isinstance(reviewed_at, str) or reviewed_at.strip().casefold() in UNKNOWN_TEXT:
        return False
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def gate_record(record, review, preflight_passed):
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    event_audit = record.get("event_audit") if isinstance(record.get("event_audit"), dict) else {}
    safety_gate = record.get("safety_gate") if isinstance(record.get("safety_gate"), dict) else {}
    scope = record.get("scope_violations")
    validator = type(record.get("cli_exit")) is int and record["cli_exit"] == 0 and \
        type(validation.get("exit_code")) is int and validation["exit_code"] == 0
    acceptance = exact_true(review.get("acceptance_pass"))
    safety = (preflight_passed and scope == [] and exact_true(review.get("scope_pass")) and
              exact_true(event_audit.get("passed")) and event_audit.get("status") == "pass" and
              exact_true(safety_gate.get("passed")) and safety_gate.get("status") == "pass")
    if record.get("task_id") == "C6":
        guard = record.get("host_guard") if isinstance(record.get("host_guard"), dict) else {}
        safety = safety and exact_true(guard.get("unchanged")) and exact_true(record.get("c6_validator_consistent"))
    handoff = exact_true(review.get("handoff_pass"))
    gates = {"validator": validator, "acceptance": acceptance, "safety": safety, "handoff": handoff}
    return {"gates": gates, "final_pass": all(gates.values())}


def metric_or_unknown(records, field):
    values = [record.get(field, UNKNOWN) for record in records]
    return sum(values) if values and all(numeric(value) for value in values) else UNKNOWN


def speed_result(indexed_runs, all_final_pass):
    if not all_final_pass:
        return {"status": "not_evaluable", "reason": "all_24_runs_must_pass", "target_ratio": 0.80}
    tasks = {}
    ratios = []
    for task in TASKS:
        a_values = [indexed_runs[(task, "A", repeat)].get("wall_seconds") for repeat in REPEATS]
        b_values = [indexed_runs[(task, "B", repeat)].get("wall_seconds") for repeat in REPEATS]
        if not all(numeric(value) and value > 0 for value in a_values + b_values):
            return {"status": "not_evaluable", "reason": f"invalid_wall_seconds:{task}", "target_ratio": 0.80}
        a_median = statistics.median(a_values)
        b_median = statistics.median(b_values)
        if not (math.isfinite(a_median) and math.isfinite(b_median)):
            return {"status": "not_evaluable", "reason": f"non_finite_median:{task}", "target_ratio": 0.80}
        if a_median <= 0 or b_median <= 0:
            return {"status": "not_evaluable", "reason": f"zero_a_median:{task}", "target_ratio": 0.80}
        ratio = b_median / a_median
        if not math.isfinite(ratio):
            return {"status": "not_evaluable", "reason": f"non_finite_ratio:{task}", "target_ratio": 0.80}
        tasks[task] = {"A_median_seconds": a_median, "B_median_seconds": b_median, "B_over_A": ratio}
        ratios.append(ratio)
    ratio_median = statistics.median(ratios)
    if not math.isfinite(ratio_median):
        return {"status": "not_evaluable", "reason": "non_finite_ratio_median", "target_ratio": 0.80}
    return {"status": "achieved" if ratio_median <= 0.80 else "not_achieved",
            "target_ratio": 0.80, "ratio_median": ratio_median, "tasks": tasks}


def analyze(summary, preflight, reviews):
    campaign = summary.get("campaign")
    fingerprint = summary.get("fingerprint")
    if (not isinstance(campaign, str) or not isinstance(fingerprint, str) or
            not CAMPAIGN_RE.fullmatch(campaign) or not FINGERPRINT_RE.fullmatch(fingerprint) or
            campaign != f"p5-{fingerprint[:16]}"):
        raise AnalysisError("summaryのcampaign/fingerprint形式が不正")
    if reviews.get("campaign") != campaign or reviews.get("fingerprint") != fingerprint:
        raise AnalysisError("reviewのcampaign/fingerprint不一致")
    if preflight.get("passed") is not True:
        preflight_passed = False
    else:
        preflight_passed = True
    result_values = summary.get("results")
    review_values = reviews.get("reviews")
    if not isinstance(result_values, list) or not isinstance(review_values, list):
        raise AnalysisError("results/reviewsが配列ではありません")
    indexed_runs = index_unique(result_values, "results")
    indexed_reviews = index_unique(review_values, "reviews")
    for record in indexed_runs.values():
        if record.get("campaign") != campaign or record.get("fingerprint") != fingerprint:
            raise AnalysisError("runのcampaign/fingerprint不一致")
    expected = expected_keys()
    missing_runs = sorted(expected - set(indexed_runs))
    missing_reviews = sorted(expected - set(indexed_reviews))
    extra_runs = sorted(set(indexed_runs) - expected)
    extra_reviews = sorted(set(indexed_reviews) - expected)
    review_invalid = sorted(key for key, review in indexed_reviews.items() if not review_complete(review))
    structurally_complete = not (missing_runs or missing_reviews or extra_runs or extra_reviews or review_invalid)
    run_results = []
    if structurally_complete:
        for key in sorted(expected):
            decision = gate_record(indexed_runs[key], indexed_reviews[key], preflight_passed)
            run_results.append({"task_id": key[0], "condition": key[1], "repeat": key[2], **decision})
    all_final_pass = structurally_complete and all(value["final_pass"] for value in run_results)
    speed = speed_result(indexed_runs, all_final_pass) if structurally_complete else {
        "status": "not_evaluable", "reason": "campaign_incomplete", "target_ratio": 0.80,
    }
    records = list(indexed_runs.values())
    aggregate = {
        "schema": 1,
        "campaign": campaign,
        "fingerprint": fingerprint,
        "preflight_passed": preflight_passed,
        "expected_runs": 24,
        "observed_runs": len(indexed_runs),
        "observed_reviews": len(indexed_reviews),
        "missing_runs": [list(key) for key in missing_runs],
        "missing_reviews": [list(key) for key in missing_reviews],
        "invalid_reviews": [list(key) for key in review_invalid],
        "campaign_complete": structurally_complete,
        "all_runs_final_pass": all_final_pass,
        "run_results": run_results,
        "speed_target": speed,
        "measurements": {
            "cost_usd_total": metric_or_unknown(records, "cost_usd"),
            "approval_wait_seconds_total": metric_or_unknown(records, "approval_wait_seconds"),
            "acceptance_completion_seconds_total": metric_or_unknown(records, "acceptance_completion_seconds"),
        },
    }
    if not structurally_complete:
        aggregate["decision"] = "incomplete"
    elif all_final_pass and speed["status"] == "achieved":
        aggregate["decision"] = "adopt"
    else:
        aggregate["decision"] = "do_not_adopt"
    return aggregate


def public_markdown(aggregate):
    speed = aggregate["speed_target"]
    lines = [
        "# P5 新campaign集計",
        "",
        f"- campaign: `{aggregate['campaign']}`",
        f"- fingerprint: `{aggregate['fingerprint']}`",
        f"- 24run・独立レビュー完了: **{str(aggregate['campaign_complete']).lower()}**",
        f"- 全run 4ゲート合格: **{str(aggregate['all_runs_final_pass']).lower()}**",
        f"- 20%限定速度目標: **{speed['status']}**",
        f"- 判定: **{aggregate['decision']}**",
        "",
        "費用、承認待ち、受入完了時間は取得できない項目を`unknown`のまま記録し、推測していません。",
    ]
    if "tasks" in speed:
        lines.extend(["", "| 課題 | A中央値秒 | B中央値秒 | B/A |", "|---|---:|---:|---:|"])
        for task in TASKS:
            value = speed["tasks"][task]
            lines.append(f"| {task} | {value['A_median_seconds']:.3f} | {value['B_median_seconds']:.3f} | {value['B_over_A']:.3f} |")
        lines.extend(["", f"6課題の比率中央値: **{speed['ratio_median']:.3f}**"])
    return "\n".join(lines) + "\n"


def write_public(path, text):
    path = Path(path)
    if path.is_symlink():
        raise AnalysisError("public outputがsymlinkです")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary_path, path)
        path.chmod(0o644)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--private-output", type=Path)
    parser.add_argument("--public-output", type=Path)
    args = parser.parse_args()
    summary = load_json(args.campaign_dir / "batch-summary.json")
    preflight = load_json(args.campaign_dir / "sandbox-preflight.json")
    reviews = load_json(args.reviews)
    aggregate = analyze(summary, preflight, reviews)
    private_output = args.private_output or args.campaign_dir / "aggregate.json"
    batch.atomic_json(private_output, aggregate)
    markdown = public_markdown(aggregate)
    if args.public_output:
        write_public(args.public_output, markdown)
    print(markdown, end="")


if __name__ == "__main__":
    main()
