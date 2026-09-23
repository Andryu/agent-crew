#!/usr/bin/env python3
"""P5のABBA/BAABを上限付きで逐次実行する。"""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
WORK = Path("/private/tmp/agent-crew-p5-benchmark/formal")
TASKS = ["C1", "C2", "C3", "C4", "C5", "C6"]
LIMIT_SECONDS = 120 * 60
RETENTION_DAYS = 14


def _reject_symlink(path):
    """既存の対象・親directoryがsymlinkなら保存を止める。"""
    current = Path(path)
    for parent in (current, *current.parents):
        if os.path.lexists(parent) and parent.is_symlink():
            raise RuntimeError(f"symlink pathへの書込みを拒否: {parent}")


def secure_mkdir(path):
    """campaign階層を0700で作成し、既存symlinkを拒否する。"""
    path = Path(path)
    _reject_symlink(path)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError(f"symlink campaign directory: {path}")
    path.chmod(0o700)
    return path


def atomic_json(path, value):
    """0600 JSONを同一directory内の一時fileから原子的に保存する。"""
    path = Path(path)
    _reject_symlink(path)
    secure_mkdir(path.parent)
    if os.path.lexists(path) and path.is_symlink():
        raise RuntimeError(f"symlink JSONを上書きしません: {path}")
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if os.path.lexists(path) and path.is_symlink():
            raise RuntimeError(f"symlink JSONを上書きしません: {path}")
        os.replace(temporary_path, path)
        path.chmod(0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def private_artifact_policy(campaign, fingerprint, campaign_dir, now=None):
    now = time.time() if now is None else now
    return {
        "schema": 1,
        "campaign": campaign,
        "fingerprint": fingerprint,
        "classification": "private",
        "storage": "private_tmp_only",
        "campaign_dir": str(campaign_dir),
        "raw_artifacts": {
            "prompt": "private_only",
            "answer": "private_only",
            "events": "private_only",
            "result": "private_only",
            "preflight": "private_only",
            "summary": "private_only",
        },
        "public_commit_prohibited": True,
        "retention_days": RETENTION_DAYS,
        "expires_epoch": now + RETENTION_DAYS * 24 * 60 * 60,
        "aggregate": {
            "path": str(campaign_dir / "aggregate.json"),
            "status": "pending_review",
            "delete_after_review": True,
            "review_complete_required": True,
            "explicit_extension_required_before_expiry": True,
        },
    }


def complete_record(record, campaign, fingerprint):
    return (record.get("fingerprint") == fingerprint and record.get("campaign") == campaign
            and all(key in record for key in ("ended_at", "validation", "cli_exit")))


def infrastructure_record(task, condition, repeat, campaign, fingerprint, error, exit_code=None):
    return {"campaign": campaign, "fingerprint": fingerprint, "task_id": task,
            "condition": condition, "repeat": repeat, "infrastructure_error": error,
            "exit_code": exit_code if exit_code is not None else "unknown",
            "pass_preliminary": False}


def stop_reason(record):
    """監査不能・利用失敗・infra失敗なら追加のモデルrunを止める。"""
    if record.get("infrastructure_error"):
        return "infrastructure_error"
    if record.get("cli_exit") != 0:
        return "cli_not_successful"
    audit = record.get("event_audit") if isinstance(record.get("event_audit"), dict) else {}
    safety = record.get("safety_gate") if isinstance(record.get("safety_gate"), dict) else {}
    if audit.get("status") != "pass" or audit.get("passed") is not True:
        return "event_audit_not_pass"
    if safety.get("status") != "pass" or safety.get("passed") is not True:
        return "safety_gate_not_pass"
    return None


def load_clock(path, fingerprint, now=None):
    now = time.time() if now is None else now
    if path.exists():
        _reject_symlink(path)
        clock = json.loads(path.read_text(encoding="utf-8"))
        if clock.get("fingerprint") != fingerprint:
            raise ValueError("campaign clock fingerprint不一致")
        return clock
    clock = {"fingerprint": fingerprint, "started_epoch": now,
             "deadline_epoch": now + LIMIT_SECONDS}
    atomic_json(path, clock)
    return clock


def require_preflight(campaign_dir):
    """不合格ならモデルrunを開始させない。"""
    preflight_file = campaign_dir / "sandbox-preflight.json"
    preflight = subprocess.run([sys.executable, "-B", str(HERE / "sandbox_preflight.py")],
                               cwd=HERE, text=True, capture_output=True)
    try:
        preflight_data = json.loads(preflight.stdout)
    except json.JSONDecodeError:
        preflight_data = {"passed": False, "raw_output_invalid": True}
    atomic_json(preflight_file, preflight_data)
    if preflight.returncode != 0:
        raise SystemExit(f"sandbox preflight失敗。モデルrunを開始しません: {preflight_file}")
    try:
        if not preflight_data.get("passed"):
            raise SystemExit(f"sandbox preflight不合格。モデルrunを開始しません: {preflight_file}")
    except json.JSONDecodeError:
        raise SystemExit(f"sandbox preflight証跡が不正。モデルrunを開始しません: {preflight_file}")


def main():
    os.umask(0o077)
    contracts = [HERE / f"b-contract/{repo}/AGENTS.md" for repo in ("agent_crew", "wealth_advisor")]
    skill = HERE / "b-contract/agent_crew/.agents/skills/fable-class/SKILL.md"
    b_index = HERE / "b-contract-index.json"
    a_index = HERE / "a-contract-index.json"
    if any(not contract.is_file() for contract in contracts) or not skill.is_file() or not b_index.is_file() or not a_index.is_file():
        raise SystemExit("P2確定版のB契約とfable-classが未固定です")
    fixed = json.loads(b_index.read_text(encoding="utf-8"))["files"]
    b_tree = HERE / "b-contract"
    actual = {str(path.relative_to(b_tree)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in b_tree.rglob("*") if path.is_file()}
    if fixed != actual or any(path.is_symlink() for path in b_tree.rglob("*")):
        raise SystemExit("B指示treeが固定indexと不一致")
    a_fixed = json.loads(a_index.read_text(encoding="utf-8"))["files"]
    a_tree = HERE / "a-contract"
    a_actual = {str(path.relative_to(a_tree)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in a_tree.rglob("*") if path.is_file()}
    if a_fixed != a_actual or any(path.is_symlink() for path in a_tree.rglob("*")):
        raise SystemExit("A補足指示treeが固定indexと不一致")
    inputs = [HERE / "run.py", HERE / "batch.py", HERE / "sandbox_preflight.py", HERE / "comparison-v2.json", HERE / "validate_c6.py",
              HERE.parent / "migration-baseline/comparison.json", HERE.parent / "migration-baseline/snapshot-index.json",
              b_index, a_index]
    fingerprint = hashlib.sha256("".join(str(path.relative_to(HERE.parent.parent.parent)) + ":" +
                                          hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs).encode()).hexdigest()
    campaign = f"p5-{fingerprint[:16]}"
    secure_mkdir(WORK)
    campaign_dir = secure_mkdir(WORK / campaign)
    policy_file = campaign_dir / "private-artifact-policy.json"
    if not policy_file.exists():
        atomic_json(policy_file, private_artifact_policy(campaign, fingerprint, campaign_dir))
    elif policy_file.is_symlink():
        raise SystemExit(f"private artifact policyがsymlinkです: {policy_file}")
    require_preflight(campaign_dir)
    clock_file = campaign_dir / "campaign-clock.json"
    clock = load_clock(clock_file, fingerprint)
    summary_file = campaign_dir / "batch-summary.json"
    previous = json.loads(summary_file.read_text(encoding="utf-8")) if summary_file.exists() else None
    if previous and previous.get("fingerprint") != fingerprint:
        raise SystemExit("campaign fingerprint不一致。別campaignとして実行してください")
    schedule = []
    for index, task in enumerate(TASKS):
        order = "ABBA" if index % 2 == 0 else "BAAB"
        used = {"A": 0, "B": 0}
        for condition in order:
            used[condition] += 1
            schedule.append((task, condition, used[condition]))
    results = []
    stopped_reason = None
    for task, condition, repeat in schedule:
        remaining = clock["deadline_epoch"] - time.time()
        if remaining < 70:
            stopped_reason = "campaign_deadline"
            break
        run_file = campaign_dir / f"{task}-{condition}-{repeat}/.benchmark-result.json"
        if run_file.exists():
            recorded = json.loads(run_file.read_text(encoding="utf-8"))
            if not complete_record(recorded, campaign, fingerprint):
                raise SystemExit(f"resume不一致: {run_file}")
            results.append(recorded)
            stopped_reason = stop_reason(recorded)
            if stopped_reason:
                break
            continue
        if run_file.parent.exists():
            record = infrastructure_record(task, condition, repeat, campaign, fingerprint,
                                           "部分runが存在。自動再実行せず監査待ち")
            results.append(record)
            stopped_reason = stop_reason(record)
            break
        run_dir = run_file.parent
        active = campaign_dir / "active-run.json"
        atomic_json(active, {"task": task, "condition": condition, "repeat": repeat,
                             "started_epoch": time.time(), "campaign": campaign,
                             "fingerprint": fingerprint})
        process = subprocess.Popen([sys.executable, "-B", str(HERE / "run.py"), task, condition,
                                    str(repeat), "--campaign", campaign, "--fingerprint", fingerprint,
                                    "--deadline-epoch", str(clock["deadline_epoch"])],
                                   cwd=HERE.parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            _, err = process.communicate(timeout=min(315, max(1, remaining)))
            error = err[-500:]
            code = process.returncode
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
            child_file = run_dir / ".benchmark-active-pgid"
            if child_file.exists():
                try:
                    os.killpg(int(child_file.read_text(encoding="ascii")), signal.SIGKILL)
                except (ProcessLookupError, ValueError):
                    pass
            error, code = "outer 315秒 timeout", "timeout"
        if active.exists() and not active.is_symlink():
            active.unlink()
        if run_file.exists():
            record = json.loads(run_file.read_text(encoding="utf-8"))
        else:
            record = infrastructure_record(task, condition, repeat, campaign, fingerprint, error, code)
        results.append(record)
        print(f"{task} {condition}{repeat}: {results[-1].get('pass_preliminary', 'infra_error')}", flush=True)
        stopped_reason = stop_reason(record)
        summary = {"schema": 1, "campaign": campaign, "fingerprint": fingerprint,
                   "planned_runs": len(schedule), "completed_records": len(results),
                   "elapsed_seconds": round(time.time() - clock["started_epoch"], 3),
                   "schedule": schedule, "results": results, "stopped_reason": stopped_reason}
        summary["preflight_file"] = str(campaign_dir / "sandbox-preflight.json")
        summary["clock_file"] = str(clock_file)
        summary["active_file"] = str(active)
        summary["private_artifact_policy_file"] = str(policy_file)
        summary["aggregate_policy"] = json.loads(policy_file.read_text(encoding="utf-8"))["aggregate"]
        atomic_json(summary_file, summary)
        if stopped_reason:
            break
    summary = {"schema": 1, "planned_runs": len(schedule), "completed_records": len(results),
               "campaign": campaign, "fingerprint": fingerprint,
               "elapsed_seconds": round(time.time() - clock["started_epoch"], 3),
               "B_contract_sha256": {contract.parent.name: hashlib.sha256(contract.read_bytes()).hexdigest()
                                     for contract in contracts},
               "B_skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
               "schedule": schedule, "results": results, "stopped_reason": stopped_reason}
    summary["preflight_file"] = str(campaign_dir / "sandbox-preflight.json")
    summary["clock_file"] = str(clock_file)
    summary["active_file"] = str(campaign_dir / "active-run.json")
    summary["private_artifact_policy_file"] = str(policy_file)
    summary["aggregate_policy"] = json.loads(policy_file.read_text(encoding="utf-8"))["aggregate"]
    atomic_json(summary_file, summary)
    print(f"summary: {summary_file}", flush=True)


if __name__ == "__main__":
    main()
