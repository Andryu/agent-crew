#!/usr/bin/env python3
"""P5集計を合成24runとprivate raw証跡で検証する。モデルは呼ばない。"""

import hashlib
import json
import importlib.util
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
from harness_fingerprint import compute_harness_fingerprint
import run as harness_run
HASH = "a" * 64


def binding(root, fingerprint, phase):
    return {"schema": 3, "phase": phase, "cli_version": "codex-cli 0.155.1",
            "harness_fingerprint": fingerprint, "root_realpath": str(root.resolve()),
            "root_device": root.stat().st_dev, "root_inode": root.stat().st_ino, "policy_template_sha256": HASH,
            "profile_sha256": HASH if phase == "model" else "b" * 64,
            "tool_environment": {"keys": ["PATH", "TMPDIR"], "sha256": HASH},
            "codex_process_environment": {"keys": ["CODEX_HOME", "PATH"],
                                          "sha256": HASH, "auth_home_location_sha256": HASH},
            "codex_executable": {"realpath": "/usr/bin/true", "sha256": HASH},
            "read_boundary": "pinned_cli_minimal_runtime_plus_fixture"}


def fixtures(campaign_dir, a_seconds=100.0, b_seconds=70.0):
    fingerprint = compute_harness_fingerprint(HERE)
    campaign = f"p5-{fingerprint[:16]}"
    assert campaign_dir.name == campaign
    runs, reviews = [], []
    for slot in batch.scheduled_runs():
        task, condition, repeat, run_id = (slot["task_id"], slot["condition"],
                                            slot["repeat"], slot["run_id"])
        root = campaign_dir / run_id
        accepted = campaign_dir / ".accepted" / run_id
        root.mkdir(parents=True, exist_ok=True)
        accepted.mkdir(parents=True, exist_ok=True)
        raw = campaign_dir / ".evidence" / run_id / "events.raw.jsonl"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes((run_id + "\n").encode())
        raw.chmod(0o600)
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        model = binding(root, fingerprint, "model")
        validator = binding(accepted, fingerprint, "validation")
        empty_digest = harness_run.canonical_digest(harness_run.tree_manifest(accepted))
        runs.append({
            "schema": 3, "campaign": campaign, "fingerprint": fingerprint,
            "run_id": run_id, "task_id": task, "condition": condition, "repeat": repeat,
            "cli_version": "codex-cli 0.155.1", "cli_exit": 0,
            "validation": {"exit_code": 0, "manifest_unchanged": True, "binding": validator,
                           "derived_from_model_profile_sha256": model["profile_sha256"],
                           "manifest_before_sha256": empty_digest, "manifest_after_sha256": empty_digest},
            "snapshot_evidence": {"matched": True, "before_sha256": empty_digest,
                                  "after_sha256": empty_digest, "accepted_sha256": empty_digest},
            "isolation_gate": {"status": "pass", "passed": True, "preflight_bound": True,
                               "binding": model, "preflight_binding": model},
            "event_audit": {"status": "pass", "passed": True},
            "attempt_policy": {"status": "pass", "passed": True},
            "acceptance_gate": {"status": "pass", "passed": True},
            "safety_gate": {"status": "pass", "passed": True},
            "raw_event_evidence": {"path_relative_to_campaign": f".evidence/{run_id}/events.raw.jsonl",
                                   "sha256": digest, "mode": "0600"},
            "scope_violations": [], "host_guard": {"unchanged": True},
            "c6_validator_consistent": True if task == "C6" else None,
            "wall_seconds": a_seconds if condition == "A" else b_seconds,
            "input_tokens": 1000, "cached_input_tokens": 500,
            "cache_write_input_tokens": 100, "output_tokens": 100, "total_tokens": 1100,
            "cost_usd": "unknown", "approval_wait_seconds": "unknown",
            "ended_at": "2026-09-30T00:00:00Z",
        })
        reviews.append({
            "run_id": run_id, "task_id": task, "condition": condition, "repeat": repeat,
            "raw_event_sha256": digest, "source_result_sha256": HASH,
            "replay_report_sha256": HASH, "classifier_sha256": HASH,
            "event_audit_reproduced": True,
            "event_audit_pass": True, "attempt_policy_pass": True,
            "acceptance_pass": True, "handoff_pass": True, "scope_pass": True,
            "review_findings": [], "reviewed_by": "independent-reviewer",
            "reviewed_at": "2026-09-30T00:00:00Z",
        })
    summary = {"schema": 2, "campaign": campaign, "fingerprint": fingerprint,
               "schedule": batch.scheduled_runs(), "results": runs}
    review_file = {"schema": 2, "campaign": campaign, "fingerprint": fingerprint,
                   "reviews": reviews}
    refresh_evidence(summary, review_file, campaign_dir)
    return summary, {"passed": True}, review_file


def refresh_evidence(summary, reviews, campaign_dir):
    review_by_id = {review["run_id"]: review for review in reviews["reviews"]}
    classifier = harness_run.sha(HERE / "run.py")
    for record in summary["results"]:
        run_id = record["run_id"]
        result_path = campaign_dir / run_id / ".benchmark-result.json"
        batch.atomic_json(result_path, record)
        source_sha = hashlib.sha256(harness_run.safe_read(result_path)).hexdigest()
        review = review_by_id[run_id]
        review["source_result_sha256"] = source_sha
        review["classifier_sha256"] = classifier
        replay = {"schema": 1, "purpose": "independent_raw_reclassification",
                  "source_result_sha256": source_sha, "run_id": run_id,
                  "harness_fingerprint": summary["fingerprint"], "classifier_sha256": classifier,
                  "raw_event_sha256": record["raw_event_evidence"]["sha256"],
                  "automatic_only": True, "independent_reviewer_judgement": "pending",
                  "event_audit": {"status": "pass", "passed": True},
                  "attempt_policy": record["attempt_policy"]}
        replay_path = campaign_dir / ".reviews" / f"{run_id}-replay.json"
        batch.atomic_json(replay_path, replay)
        review["replay_report_sha256"] = hashlib.sha256(harness_run.safe_read(replay_path)).hexdigest()


def decide(summary, preflight, reviews, campaign_dir):
    return analyze.analyze(summary, preflight, reviews, campaign_dir)


def main():
    with tempfile.TemporaryDirectory(prefix="p5-analysis-", dir="/private/tmp",
                                     ignore_cleanup_errors=True) as temporary:
        fingerprint = compute_harness_fingerprint(HERE)
        campaign_dir = Path(temporary) / f"p5-{fingerprint[:16]}"
        summary, preflight, reviews = fixtures(campaign_dir)
        positive = decide(summary, preflight, reviews, campaign_dir)
        assert positive["campaign_complete"] and positive["all_runs_final_pass"]
        assert positive["quality_gate"]["status"] == "pass"
        assert positive["safety_gate"]["status"] == "pass"
        assert positive["cache_comparability"]["status"] == "comparable"
        assert positive["speed_target"]["status"] == "achieved"
        assert positive["speed_target"]["ratio_median"] == 0.7
        assert positive["decision"] == "adopt"
        assert positive["usage"]["totals"]["cached_input_tokens"] == 12000
        assert batch.stop_reason(summary["results"][0]) is None

        first = summary["results"][0]
        first_review = reviews["reviews"][0]
        stale_sidecar = dict(first_review)
        first["output_tokens"] = 101
        refresh_evidence(summary, reviews, campaign_dir)
        reviews["reviews"][0] = stale_sidecar
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        reviews["reviews"][0] = first_review
        first["output_tokens"] = 100
        refresh_evidence(summary, reviews, campaign_dir)

        result_path = campaign_dir / first["run_id"] / ".benchmark-result.json"
        original_result_bytes = harness_run.safe_read(result_path)
        result_path.write_text('{"changed":true}\n', encoding="utf-8")
        result_path.chmod(0o600)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        result_path.write_bytes(original_result_bytes)
        result_path.chmod(0o600)
        replay_path = campaign_dir / ".reviews" / f"{first['run_id']}-replay.json"
        original_replay_bytes = harness_run.safe_read(replay_path)
        replay_path.write_text('{"changed":true}\n', encoding="utf-8")
        replay_path.chmod(0o600)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        replay_path.write_bytes(original_replay_bytes)
        replay_path.chmod(0o600)

        accepted_change = campaign_dir / ".accepted" / first["run_id"] / "changed.txt"
        accepted_change.write_text("tampered", encoding="utf-8")
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        accepted_change.unlink()
        old_fingerprint = summary["fingerprint"]
        summary["fingerprint"] = reviews["fingerprint"] = old_fingerprint[:16] + "0" * 48
        try:
            decide(summary, preflight, reviews, campaign_dir)
        except analyze.AnalysisError as error:
            assert "current shared harness fingerprint" in str(error)
        else:
            raise AssertionError("旧fingerprintの採用を拒否しなかった")
        summary["fingerprint"] = reviews["fingerprint"] = old_fingerprint

        original = summary["results"][0]["attempt_policy"]
        summary["results"][0]["attempt_policy"] = {"status": "unknown", "passed": False}
        summary["results"][0]["safety_gate"] = {"status": "fail", "passed": False}
        refresh_evidence(summary, reviews, campaign_dir)
        resolved = decide(summary, preflight, reviews, campaign_dir)
        assert resolved["decision"] == "adopt"
        assert resolved["run_results"][0]["independently_resolved_unknown"] is True
        assert batch.stop_reason(summary["results"][0]) is None
        summary["results"][0]["attempt_policy"] = {"status": "fail", "passed": False}
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        summary["results"][0]["attempt_policy"] = original
        summary["results"][0]["safety_gate"] = {"status": "pass", "passed": True}
        refresh_evidence(summary, reviews, campaign_dir)

        raw = campaign_dir / ".evidence" / summary["results"][0]["run_id"] / "events.raw.jsonl"
        raw_bytes = raw.read_bytes()
        raw.unlink()
        missing_raw = decide(summary, preflight, reviews, campaign_dir)
        assert missing_raw["safety_gate"]["status"] == "fail"
        assert missing_raw["decision"] != "adopt"
        raw.write_bytes(raw_bytes)
        raw.chmod(0o600)
        reviews["reviews"][0]["raw_event_sha256"] = "0" * 64
        mismatch = decide(summary, preflight, reviews, campaign_dir)
        assert mismatch["decision"] != "adopt"
        reviews["reviews"][0]["raw_event_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        reviews["reviews"][0]["event_audit_reproduced"] = False
        no_replay = decide(summary, preflight, reviews, campaign_dir)
        assert no_replay["decision"] != "adopt"
        reviews["reviews"][0]["event_audit_reproduced"] = True
        reviews["reviews"][0]["attempt_policy_pass"] = False
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        reviews["reviews"][0]["attempt_policy_pass"] = True

        model = summary["results"][0]["isolation_gate"]["binding"]
        old_tool = model.pop("tool_environment")
        assert decide(summary, preflight, reviews, campaign_dir)["safety_gate"]["status"] == "fail"
        model["tool_environment"] = old_tool
        refresh_evidence(summary, reviews, campaign_dir)
        summary["results"][0]["isolation_gate"]["preflight_bound"] = False
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        summary["results"][0]["isolation_gate"]["preflight_bound"] = True
        refresh_evidence(summary, reviews, campaign_dir)
        validation = summary["results"][0]["validation"]
        derived = validation.pop("derived_from_model_profile_sha256")
        assert decide(summary, preflight, reviews, campaign_dir)["decision"] != "adopt"
        validation["derived_from_model_profile_sha256"] = derived
        refresh_evidence(summary, reviews, campaign_dir)

        for record in summary["results"]:
            if record["task_id"] == "C1" and record["condition"] == "B":
                record["cached_input_tokens"] = 900
        refresh_evidence(summary, reviews, campaign_dir)
        cache_diff = decide(summary, preflight, reviews, campaign_dir)
        assert cache_diff["cache_comparability"]["status"] == "unknown"
        assert cache_diff["speed_target"]["status"] == "unknown"
        for record in summary["results"]:
            record["cached_input_tokens"] = 500
        del summary["results"][0]["cached_input_tokens"]
        refresh_evidence(summary, reviews, campaign_dir)
        assert decide(summary, preflight, reviews, campaign_dir)["speed_target"]["status"] == "unknown"
        summary["results"][0]["cached_input_tokens"] = 500
        refresh_evidence(summary, reviews, campaign_dir)

        slots = [slot["run_id"] for slot in batch.scheduled_runs()]
        assert len(slots) == len(set(slots)) == 24 and all(len(slot) == 6 for slot in slots)
        mapping_path = campaign_dir / "run-slot-mapping.json"
        mapping = batch.load_or_create_mapping(mapping_path, summary["campaign"], summary["fingerprint"])
        assert mapping == batch.scheduled_runs()
        assert mapping_path.stat().st_mode & 0o777 == 0o600
        assert batch.record_matches_slot(summary["results"][0], summary["campaign"],
                                         summary["fingerprint"], mapping[0])
        assert not batch.record_matches_slot(summary["results"][0], summary["campaign"],
                                             summary["fingerprint"], mapping[1])
        assert campaign_dir / slots[0] / ".benchmark-result.json" != campaign_dir / "C1-A-1" / ".benchmark-result.json"
        try:
            batch.load_or_create_mapping(mapping_path, summary["campaign"], "e" * 64)
        except ValueError:
            pass
        else:
            raise AssertionError("resumeのfingerprint不一致を拒否しなかった")
        summary["results"][0]["run_id"] = "run-24"
        try:
            decide(summary, preflight, reviews, campaign_dir)
        except analyze.AnalysisError:
            pass
        else:
            raise AssertionError("opaque slot mapping不一致を拒否しなかった")
        summary["results"][0]["run_id"] = "run-01"
        private = campaign_dir / "aggregate.json"
        batch.atomic_json(private, positive)
        assert private.stat().st_mode & 0o777 == 0o600
        markdown = analyze.public_markdown(positive)
        assert "/private/" not in markdown and "/Users/" not in markdown
    print("P5 analysis selftest: raw/review/binding/opaque/cache/4gate OK")


if __name__ == "__main__":
    main()
