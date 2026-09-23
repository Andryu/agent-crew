#!/usr/bin/env python3
"""P5最終集計器をモデル呼出しなしの合成24runで検証する。"""

import importlib.util
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


batch = load_module("batch")
analyze = load_module("analyze")


def fixtures(a_seconds=100.0, b_seconds=70.0):
    fingerprint = "f" * 64
    campaign = f"p5-{fingerprint[:16]}"
    runs = []
    reviews = []
    for task in analyze.TASKS:
        for condition in analyze.CONDITIONS:
            for repeat in analyze.REPEATS:
                runs.append({
                    "campaign": campaign, "fingerprint": fingerprint,
                    "task_id": task, "condition": condition, "repeat": repeat,
                    "cli_exit": 0, "validation": {"exit_code": 0},
                    "scope_violations": [], "event_audit": {"status": "pass", "passed": True},
                    "safety_gate": {"status": "pass", "passed": True},
                    "host_guard": {"unchanged": True} if task == "C6" else None,
                    "c6_validator_consistent": True if task == "C6" else None,
                    "wall_seconds": a_seconds if condition == "A" else b_seconds,
                    "cost_usd": "unknown", "approval_wait_seconds": "unknown",
                })
                reviews.append({
                    "task_id": task, "condition": condition, "repeat": repeat,
                    "acceptance_pass": True, "handoff_pass": True, "scope_pass": True,
                    "review_findings": [], "reviewed_by": "independent-reviewer",
                    "reviewed_at": "2026-09-23T00:00:00Z",
                })
    summary = {"campaign": campaign, "fingerprint": fingerprint, "results": runs}
    review_file = {"schema": 1, "campaign": campaign, "fingerprint": fingerprint,
                   "reviews": reviews}
    return summary, {"passed": True}, review_file


def expect_error(summary, preflight, reviews, fragment):
    try:
        analyze.analyze(summary, preflight, reviews)
    except analyze.AnalysisError as error:
        assert fragment in str(error), error
    else:
        raise AssertionError(f"AnalysisErrorにならない: {fragment}")


def main():
    summary, preflight, reviews = fixtures()
    positive = analyze.analyze(summary, preflight, reviews)
    assert positive["campaign_complete"] is True
    assert positive["all_runs_final_pass"] is True
    assert positive["speed_target"]["status"] == "achieved"
    assert positive["speed_target"]["ratio_median"] == 0.7
    assert positive["decision"] == "adopt"
    assert positive["measurements"]["cost_usd_total"] == "unknown"
    assert batch.stop_reason(positive_summary_record := summary["results"][0]) is None
    audit_stop = dict(positive_summary_record)
    audit_stop["event_audit"] = {"status": "unknown", "passed": False}
    assert batch.stop_reason(audit_stop) == "event_audit_not_pass"
    cli_stop = dict(positive_summary_record)
    cli_stop["cli_exit"] = 1
    assert batch.stop_reason(cli_stop) == "cli_not_successful"

    slow_summary, slow_preflight, slow_reviews = fixtures(b_seconds=90.0)
    slow = analyze.analyze(slow_summary, slow_preflight, slow_reviews)
    assert slow["campaign_complete"] is True
    assert slow["speed_target"]["status"] == "not_achieved"
    assert slow["decision"] == "do_not_adopt"

    failed_summary, failed_preflight, failed_reviews = fixtures()
    failed_reviews["reviews"][0]["acceptance_pass"] = False
    failed = analyze.analyze(failed_summary, failed_preflight, failed_reviews)
    assert failed["campaign_complete"] is True
    assert failed["all_runs_final_pass"] is False
    assert failed["speed_target"]["status"] == "not_evaluable"

    unknown_summary, unknown_preflight, unknown_reviews = fixtures()
    unknown_summary["results"][0]["event_audit"] = {"status": "unknown", "passed": False}
    unknown = analyze.analyze(unknown_summary, unknown_preflight, unknown_reviews)
    assert unknown["all_runs_final_pass"] is False

    incomplete_summary, incomplete_preflight, incomplete_reviews = fixtures()
    incomplete_summary["results"].pop()
    incomplete = analyze.analyze(incomplete_summary, incomplete_preflight, incomplete_reviews)
    assert incomplete["campaign_complete"] is False
    assert incomplete["decision"] == "incomplete"

    duplicate_summary, duplicate_preflight, duplicate_reviews = fixtures()
    duplicate_summary["results"].append(dict(duplicate_summary["results"][0]))
    expect_error(duplicate_summary, duplicate_preflight, duplicate_reviews, "重複")

    mismatch_summary, mismatch_preflight, mismatch_reviews = fixtures()
    mismatch_summary["results"][0]["fingerprint"] = "wrong"
    expect_error(mismatch_summary, mismatch_preflight, mismatch_reviews, "fingerprint")

    zero_summary, zero_preflight, zero_reviews = fixtures(a_seconds=0.0, b_seconds=0.0)
    zero = analyze.analyze(zero_summary, zero_preflight, zero_reviews)
    assert zero["speed_target"]["status"] == "not_evaluable"
    assert "invalid_wall_seconds" in zero["speed_target"]["reason"]

    overflow_summary, overflow_preflight, overflow_reviews = fixtures(a_seconds=1e308, b_seconds=9e307)
    overflow = analyze.analyze(overflow_summary, overflow_preflight, overflow_reviews)
    assert overflow["speed_target"]["status"] == "not_evaluable"
    assert "non_finite_median" in overflow["speed_target"]["reason"]

    bad_review_summary, bad_review_preflight, bad_review_reviews = fixtures()
    del bad_review_reviews["reviews"][0]["reviewed_at"]
    bad_review = analyze.analyze(bad_review_summary, bad_review_preflight, bad_review_reviews)
    assert bad_review["campaign_complete"] is False

    for field, value in (("reviewed_by", "unknown"), ("reviewed_at", "unknown"),
                         ("reviewed_by", 1), ("reviewed_at", True)):
        review_summary, review_preflight, review_reviews = fixtures()
        review_reviews["reviews"][0][field] = value
        rejected = analyze.analyze(review_summary, review_preflight, review_reviews)
        assert rejected["campaign_complete"] is False, (field, value)

    strict_summary, strict_preflight, strict_reviews = fixtures()
    strict_summary["results"][0]["cli_exit"] = False
    strict = analyze.analyze(strict_summary, strict_preflight, strict_reviews)
    assert strict["all_runs_final_pass"] is False

    repeat_summary, repeat_preflight, repeat_reviews = fixtures()
    repeat_summary["results"][0]["repeat"] = True
    expect_error(repeat_summary, repeat_preflight, repeat_reviews, "範囲外")

    infra_summary, infra_preflight, infra_reviews = fixtures()
    first = infra_summary["results"][0]
    infra_summary["results"][0] = batch.infrastructure_record(
        first["task_id"], first["condition"], first["repeat"],
        first["campaign"], first["fingerprint"], "timeout", "timeout")
    infra = analyze.analyze(infra_summary, infra_preflight, infra_reviews)
    assert infra["campaign_complete"] is True
    assert infra["all_runs_final_pass"] is False
    assert infra["speed_target"]["status"] == "not_evaluable"
    assert batch.stop_reason(infra_summary["results"][0]) == "infrastructure_error"

    unsafe_summary, unsafe_preflight, unsafe_reviews = fixtures()
    unsafe_summary["campaign"] = "/private/tmp/secret\nline"
    unsafe_reviews["campaign"] = unsafe_summary["campaign"]
    for record in unsafe_summary["results"]:
        record["campaign"] = unsafe_summary["campaign"]
    expect_error(unsafe_summary, unsafe_preflight, unsafe_reviews, "形式が不正")

    unknown_fp_summary, unknown_fp_preflight, unknown_fp_reviews = fixtures()
    unknown_fp_summary["fingerprint"] = "unknown"
    unknown_fp_reviews["fingerprint"] = "unknown"
    expect_error(unknown_fp_summary, unknown_fp_preflight, unknown_fp_reviews, "形式が不正")

    with tempfile.TemporaryDirectory(prefix="p5-analysis-", dir="/private/tmp",
                                     ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        private = root / "campaign/aggregate.json"
        batch.atomic_json(private, positive)
        assert private.stat().st_mode & 0o777 == 0o600
        assert private.parent.stat().st_mode & 0o777 == 0o700
        public = root / "public.md"
        markdown = analyze.public_markdown(positive)
        assert "/private/" not in markdown and "/Users/" not in markdown
        analyze.write_public(public, markdown)
        assert public.stat().st_mode & 0o777 == 0o644
        policy = batch.private_artifact_policy("p5-ffffffffffffffff", "f" * 64, root / "campaign", now=1000)
        assert policy["retention_days"] == 14
        assert policy["expires_epoch"] == 1000 + 14 * 24 * 60 * 60
        symlink = root / "link.json"
        symlink.symlink_to(root / "target.json")
        try:
            batch.atomic_json(symlink, {})
        except RuntimeError:
            pass
        else:
            raise AssertionError("symlink JSONを上書きした")

    print("P5 analysis selftest: 24run/gates/speed/unknown/duplicate/fingerprint/mode OK")


if __name__ == "__main__":
    main()
