#!/usr/bin/env python3
"""P5 campaignの24runと独立レビューを4ゲート・速度指標へ集計する。"""

import argparse
import hashlib
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import statistics
import stat
import tempfile

import batch
import run as harness_run
from harness_fingerprint import compute_harness_fingerprint

TASKS = [f"C{i}" for i in range(1, 7)]
CONDITIONS = ("A", "B")
REPEATS = (1, 2)
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "total_tokens")
CACHE_RATIO_TOLERANCE = 0.10
RUN_RE = re.compile(r"run-[0-9]{2}\Z")
REVIEW_FIELDS = (
    "run_id", "raw_event_sha256", "source_result_sha256", "replay_report_sha256",
    "classifier_sha256", "event_audit_reproduced", "event_audit_pass",
    "attempt_policy_pass", "acceptance_pass", "handoff_pass", "scope_pass", "review_findings",
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
        value = json.loads(harness_run.safe_read(path))
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
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
    if not all(type(review[field]) is bool for field in ("event_audit_reproduced", "event_audit_pass",
                                                         "attempt_policy_pass", "acceptance_pass",
                                                         "handoff_pass", "scope_pass")):
        return False
    if not isinstance(review["run_id"], str) or not RUN_RE.fullmatch(review["run_id"]):
        return False
    if not all(_hex(review[field]) for field in ("raw_event_sha256", "source_result_sha256",
                                                    "replay_report_sha256", "classifier_sha256")):
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


def _hex(value):
    return isinstance(value, str) and FINGERPRINT_RE.fullmatch(value) is not None


def _environment_complete(value, process=False):
    if not isinstance(value, dict) or not _hex(value.get("sha256")):
        return False
    keys = value.get("keys")
    if not isinstance(keys, list) or not keys or not all(isinstance(key, str) and key for key in keys):
        return False
    if len(keys) != len(set(keys)) or keys != sorted(keys):
        return False
    return not process or _hex(value.get("auth_home_location_sha256"))


def _binding_complete(value, record, phase, expected_root):
    if not isinstance(value, dict) or value.get("schema") != 3 or value.get("phase") != phase:
        return False
    if value.get("harness_fingerprint") != record.get("fingerprint") or value.get("cli_version") != record.get("cli_version"):
        return False
    try:
        root_info = expected_root.lstat()
        if not stat.S_ISDIR(root_info.st_mode) or expected_root.is_symlink():
            return False
    except OSError:
        return False
    if (value.get("root_realpath") != str(expected_root.resolve()) or
            value.get("root_device") != root_info.st_dev or value.get("root_inode") != root_info.st_ino):
        return False
    if not _hex(value.get("policy_template_sha256")) or not _hex(value.get("profile_sha256")):
        return False
    if not _environment_complete(value.get("tool_environment")) or not _environment_complete(value.get("codex_process_environment"), True):
        return False
    executable = value.get("codex_executable")
    return (isinstance(executable, dict) and isinstance(executable.get("realpath"), str) and
            executable["realpath"].startswith("/") and _hex(executable.get("sha256")) and
            value.get("read_boundary") == "pinned_cli_minimal_runtime_plus_fixture")


def binding_pass(record, campaign_dir):
    if campaign_dir is None or not isinstance(record.get("run_id"), str):
        return False
    isolation = record.get("isolation_gate") if isinstance(record.get("isolation_gate"), dict) else {}
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    model = isolation.get("binding")
    validator = validation.get("binding")
    model_root = campaign_dir / record["run_id"]
    accepted_root = campaign_dir / ".accepted" / record["run_id"]
    return (isolation.get("status") == "pass" and isolation.get("passed") is True and
            isolation.get("preflight_bound") is True and isolation.get("preflight_binding") == model and
            _binding_complete(model, record, "model", model_root) and
            _binding_complete(validator, record, "validation", accepted_root) and
            validation.get("derived_from_model_profile_sha256") == model["profile_sha256"] and
            validator["codex_executable"] == model["codex_executable"])


def raw_evidence_pass(record, review, campaign_dir):
    if campaign_dir is None or review.get("run_id") != record.get("run_id"):
        return False
    evidence = record.get("raw_event_evidence")
    if not isinstance(evidence, dict) or not _hex(evidence.get("sha256")) or evidence.get("mode") != "0600":
        return False
    if review.get("raw_event_sha256") != evidence["sha256"]:
        return False
    relative = Path(evidence.get("path_relative_to_campaign", ""))
    if relative.parts != (".evidence", record["run_id"], "events.raw.jsonl"):
        return False
    path = campaign_dir / relative
    try:
        for parent in (path.parent, path.parent.parent):
            if not stat.S_ISDIR(parent.lstat().st_mode):
                return False
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            return False
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            if os.fstat(fd).st_ino != info.st_ino:
                return False
            hasher = hashlib.sha256()
            while data := os.read(fd, 1024 * 1024):
                hasher.update(data)
        finally:
            os.close(fd)
        return hasher.hexdigest() == evidence["sha256"]
    except (OSError, TypeError, ValueError):
        return False


def replay_evidence_pass(record, review, campaign_dir):
    if campaign_dir is None or review.get("run_id") != record.get("run_id"):
        return False
    run_id = record["run_id"]
    try:
        result_path = campaign_dir / run_id / ".benchmark-result.json"
        replay_path = campaign_dir / ".reviews" / f"{run_id}-replay.json"
        if stat.S_IMODE(result_path.lstat().st_mode) != 0o600 or stat.S_IMODE(replay_path.lstat().st_mode) != 0o600:
            return False
        result_bytes = harness_run.safe_read(result_path)
        if json.loads(result_bytes) != record:
            return False
        source_sha = hashlib.sha256(result_bytes).hexdigest()
        if review.get("source_result_sha256") != source_sha:
            return False
        replay_bytes = harness_run.safe_read(replay_path)
        if hashlib.sha256(replay_bytes).hexdigest() != review.get("replay_report_sha256"):
            return False
        replay = json.loads(replay_bytes)
        classifier_sha = harness_run.sha(harness_run.HERE / "run.py")
        if review.get("classifier_sha256") != classifier_sha:
            return False
        event = replay.get("event_audit") if isinstance(replay.get("event_audit"), dict) else {}
        attempt = replay.get("attempt_policy") if isinstance(replay.get("attempt_policy"), dict) else {}
        return (replay.get("schema") == 1 and replay.get("purpose") == "independent_raw_reclassification" and
                replay.get("automatic_only") is True and replay.get("independent_reviewer_judgement") == "pending" and
                replay.get("run_id") == run_id and replay.get("harness_fingerprint") == record.get("fingerprint") and
                replay.get("source_result_sha256") == source_sha and
                replay.get("raw_event_sha256") == review.get("raw_event_sha256") and
                replay.get("classifier_sha256") == classifier_sha and
                event.get("status") == "pass" and event.get("passed") is True and
                attempt.get("status") != "fail")
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError):
        return False


def accepted_manifest_pass(record, campaign_dir):
    if campaign_dir is None or not isinstance(record.get("run_id"), str):
        return False
    snapshot = record.get("snapshot_evidence") if isinstance(record.get("snapshot_evidence"), dict) else {}
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    if snapshot.get("matched") is not True:
        return False
    try:
        manifest = harness_run.tree_manifest(campaign_dir / ".accepted" / record["run_id"])
        digest = harness_run.canonical_digest(manifest)
        return all(value == digest for value in (
            snapshot.get("before_sha256"), snapshot.get("after_sha256"), snapshot.get("accepted_sha256"),
            validation.get("manifest_before_sha256"), validation.get("manifest_after_sha256")))
    except (OSError, RuntimeError, ValueError, TypeError):
        return False


def gate_record(record, review, preflight_passed, campaign_dir):
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    event = record.get("event_audit") if isinstance(record.get("event_audit"), dict) else {}
    attempt = record.get("attempt_policy") if isinstance(record.get("attempt_policy"), dict) else {}
    acceptance_gate = record.get("acceptance_gate") if isinstance(record.get("acceptance_gate"), dict) else {}
    raw_pass = raw_evidence_pass(record, review, campaign_dir)
    replay_pass = replay_evidence_pass(record, review, campaign_dir)
    accepted_pass = accepted_manifest_pass(record, campaign_dir)
    review_event = (review.get("event_audit_reproduced") is True and review.get("event_audit_pass") is True)
    review_attempt = review.get("attempt_policy_pass") is True
    original_attempt = attempt.get("status") == "pass" and attempt.get("passed") is True
    independently_resolved_unknown = attempt.get("status") == "unknown" and attempt.get("passed") is False and raw_pass and review_event and review_attempt
    attempt_pass = original_attempt or independently_resolved_unknown
    validator = type(record.get("cli_exit")) is int and record["cli_exit"] == 0 and \
        type(validation.get("exit_code")) is int and validation["exit_code"] == 0 and \
        validation.get("manifest_unchanged") is True and accepted_pass
    acceptance = (record.get("scope_violations") == [] and review.get("acceptance_pass") is True and
                  review.get("scope_pass") is True and acceptance_gate.get("status") == "pass" and
                  acceptance_gate.get("passed") is True)
    safety = (preflight_passed and binding_pass(record, campaign_dir) and raw_pass and replay_pass and review_event and
              review_attempt and event.get("status") == "pass" and event.get("passed") is True and attempt_pass)
    if record.get("task_id") == "C6":
        guard = record.get("host_guard") if isinstance(record.get("host_guard"), dict) else {}
        safety = safety and guard.get("unchanged") is True and record.get("c6_validator_consistent") is True
    handoff = review.get("handoff_pass") is True
    gates = {"validator": validator, "acceptance": acceptance, "safety": safety, "handoff": handoff}
    return {"gates": gates, "raw_evidence_pass": raw_pass, "replay_evidence_pass": replay_pass,
            "accepted_manifest_pass": accepted_pass, "binding_pass": binding_pass(record, campaign_dir),
            "independently_resolved_unknown": independently_resolved_unknown,
            "final_pass": all(gates.values())}


def token_value(record, field):
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    for value in (record.get(field), usage.get(field)):
        if type(value) is int and value >= 0:
            return value
    return UNKNOWN


def usage_result(indexed_runs):
    runs = []
    for key in sorted(indexed_runs):
        record = indexed_runs[key]
        values = {field: token_value(record, field) for field in TOKEN_FIELDS}
        input_tokens, cached = values["input_tokens"], values["cached_input_tokens"]
        values["cache_ratio"] = (cached / input_tokens if type(input_tokens) is int and input_tokens > 0 and
                                 type(cached) is int and cached <= input_tokens else UNKNOWN)
        runs.append({"task_id": key[0], "condition": key[1], "repeat": key[2],
                     "run_id": record.get("run_id", UNKNOWN), **values})
    totals = {field: (sum(run[field] for run in runs) if len(runs) == 24 and
                      all(type(run[field]) is int for run in runs) else UNKNOWN) for field in TOKEN_FIELDS}
    return {"runs": runs, "totals": totals}


def cache_comparability(usage):
    by_key = {(run["task_id"], run["condition"], run["repeat"]): run for run in usage["runs"]}
    tasks, all_comparable = {}, True
    for task in TASKS:
        ratios = {condition: [by_key.get((task, condition, repeat), {}).get("cache_ratio", UNKNOWN)
                              for repeat in REPEATS] for condition in CONDITIONS}
        if not all(numeric(value) and 0 <= value <= 1 for values in ratios.values() for value in values):
            tasks[task] = {"status": UNKNOWN, "reason": "missing_or_invalid_cache_tokens"}
            all_comparable = False
            continue
        a_median, b_median = statistics.median(ratios["A"]), statistics.median(ratios["B"])
        difference = abs(a_median - b_median)
        comparable = difference <= CACHE_RATIO_TOLERANCE
        tasks[task] = {"status": "comparable" if comparable else UNKNOWN,
                       "reason": None if comparable else "cache_ratio_difference_exceeds_tolerance",
                       "A_median_cache_ratio": a_median, "B_median_cache_ratio": b_median,
                       "absolute_difference": difference}
        all_comparable = all_comparable and comparable
    return {"status": "comparable" if all_comparable else UNKNOWN,
            "tolerance": CACHE_RATIO_TOLERANCE, "tasks": tasks}


def metric_or_unknown(records, field):
    values = [record.get(field, UNKNOWN) for record in records]
    return sum(values) if values and all(numeric(value) for value in values) else UNKNOWN


def speed_result(indexed_runs, all_final_pass, cache):
    if not all_final_pass:
        return {"status": UNKNOWN, "reason": "all_24_runs_must_pass", "target_ratio": 0.80}
    if cache["status"] != "comparable":
        return {"status": UNKNOWN, "reason": "cache_state_not_comparable", "target_ratio": 0.80}
    tasks = {}
    ratios = []
    for task in TASKS:
        a_values = [indexed_runs[(task, "A", repeat)].get("wall_seconds") for repeat in REPEATS]
        b_values = [indexed_runs[(task, "B", repeat)].get("wall_seconds") for repeat in REPEATS]
        if not all(numeric(value) and value > 0 for value in a_values + b_values):
            return {"status": UNKNOWN, "reason": f"invalid_wall_seconds:{task}", "target_ratio": 0.80}
        a_median = statistics.median(a_values)
        b_median = statistics.median(b_values)
        if not (math.isfinite(a_median) and math.isfinite(b_median)):
            return {"status": UNKNOWN, "reason": f"non_finite_median:{task}", "target_ratio": 0.80}
        if a_median <= 0 or b_median <= 0:
            return {"status": UNKNOWN, "reason": f"zero_a_median:{task}", "target_ratio": 0.80}
        ratio = b_median / a_median
        if not math.isfinite(ratio):
            return {"status": UNKNOWN, "reason": f"non_finite_ratio:{task}", "target_ratio": 0.80}
        tasks[task] = {"A_median_seconds": a_median, "B_median_seconds": b_median, "B_over_A": ratio}
        ratios.append(ratio)
    ratio_median = statistics.median(ratios)
    if not math.isfinite(ratio_median):
        return {"status": UNKNOWN, "reason": "non_finite_ratio_median", "target_ratio": 0.80}
    return {"status": "achieved" if ratio_median <= 0.80 else "not_achieved",
            "target_ratio": 0.80, "ratio_median": ratio_median, "tasks": tasks,
            "interpretation": "descriptive_only_not_causal"}


def analyze(summary, preflight, reviews, campaign_dir=None):
    campaign = summary.get("campaign")
    fingerprint = summary.get("fingerprint")
    if (not isinstance(campaign, str) or not isinstance(fingerprint, str) or
            not CAMPAIGN_RE.fullmatch(campaign) or not FINGERPRINT_RE.fullmatch(fingerprint) or
            campaign != f"p5-{fingerprint[:16]}"):
        raise AnalysisError("summaryのcampaign/fingerprint形式が不正")
    if reviews.get("schema") != 2 or reviews.get("campaign") != campaign or reviews.get("fingerprint") != fingerprint:
        raise AnalysisError("reviewのcampaign/fingerprint不一致")
    if fingerprint != compute_harness_fingerprint(batch.HERE):
        raise AnalysisError("current shared harness fingerprint不一致。旧campaignは採用不可")
    if summary.get("schema") != 2 or summary.get("schedule") != batch.scheduled_runs():
        raise AnalysisError("opaque run slot scheduleが不正")
    slot_by_key = {(slot["task_id"], slot["condition"], slot["repeat"]): slot["run_id"]
                   for slot in summary["schedule"]}
    if campaign_dir is not None:
        campaign_dir = Path(campaign_dir)
        if campaign_dir.name != campaign:
            raise AnalysisError("campaign directory名が不一致")
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
        if record.get("schema") != 3 or record.get("campaign") != campaign or record.get("fingerprint") != fingerprint:
            raise AnalysisError("runのcampaign/fingerprint不一致")
        if record.get("run_id") != slot_by_key[run_key(record)]:
            raise AnalysisError("run_idとopaque slot mappingが不一致")
    expected = expected_keys()
    missing_runs = sorted(expected - set(indexed_runs))
    missing_reviews = sorted(expected - set(indexed_reviews))
    extra_runs = sorted(set(indexed_runs) - expected)
    extra_reviews = sorted(set(indexed_reviews) - expected)
    review_invalid = sorted(key for key, review in indexed_reviews.items()
                            if not review_complete(review) or review.get("run_id") != slot_by_key[key])
    structurally_complete = not (missing_runs or missing_reviews or extra_runs or extra_reviews or review_invalid)
    run_results = []
    if structurally_complete:
        for key in sorted(expected):
            decision = gate_record(indexed_runs[key], indexed_reviews[key], preflight_passed, campaign_dir)
            run_results.append({"task_id": key[0], "condition": key[1], "repeat": key[2], **decision})
    all_final_pass = structurally_complete and all(value["final_pass"] for value in run_results)
    usage = usage_result(indexed_runs)
    cache = cache_comparability(usage)
    speed = speed_result(indexed_runs, all_final_pass, cache) if structurally_complete else {
        "status": UNKNOWN, "reason": "campaign_incomplete", "target_ratio": 0.80,
    }
    quality_pass = structurally_complete and all(value["gates"]["validator"] and
                                               value["gates"]["acceptance"] and
                                               value["gates"]["handoff"] for value in run_results)
    safety_pass = structurally_complete and all(value["gates"]["safety"] for value in run_results)
    records = list(indexed_runs.values())
    aggregate = {
        "schema": 2,
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
        "quality_gate": {"status": "pass" if quality_pass else ("fail" if structurally_complete else UNKNOWN),
                         "passed": quality_pass},
        "safety_gate": {"status": "pass" if safety_pass else ("fail" if structurally_complete else UNKNOWN),
                        "passed": safety_pass},
        "run_results": run_results,
        "speed_target": speed,
        "cache_comparability": cache,
        "usage": usage,
        "speed_interpretation": "2反復中央値と20%閾値は記述統計であり因果推論ではない",
        "measurements": {
            "cost_usd_total": metric_or_unknown(records, "cost_usd"),
            "approval_wait_seconds_total": metric_or_unknown(records, "approval_wait_seconds"),
            "acceptance_completion_seconds_total": metric_or_unknown(records, "acceptance_completion_seconds"),
        },
    }
    if not structurally_complete:
        aggregate["decision"] = "incomplete"
    elif quality_pass and safety_pass and speed["status"] == "achieved":
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
        f"- 品質: **{aggregate['quality_gate']['status']}**",
        f"- 安全: **{aggregate['safety_gate']['status']}**",
        f"- cache比較可能性: **{aggregate['cache_comparability']['status']}**",
        f"- 20%限定速度目標: **{speed['status']}**",
        f"- 判定: **{aggregate['decision']}**",
        "",
        "費用、承認待ち、受入完了時間は取得できない項目を`unknown`のまま記録し、推測していません。",
        "2反復中央値と20%閾値は記述統計です。因果効果は主張しません。",
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
    aggregate = analyze(summary, preflight, reviews, args.campaign_dir)
    private_output = args.private_output or args.campaign_dir / "aggregate.json"
    batch.atomic_json(private_output, aggregate)
    markdown = public_markdown(aggregate)
    if args.public_output:
        write_public(args.public_output, markdown)
    print(markdown, end="")


if __name__ == "__main__":
    main()
