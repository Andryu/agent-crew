#!/usr/bin/env python3
"""P5のABBA/BAABを上限付きで逐次実行する。"""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
WORK = Path("/private/tmp/agent-crew-p5-benchmark/formal")
TASKS = ["C1", "C2", "C3", "C4", "C5", "C6"]
LIMIT_SECONDS = 120 * 60


def complete_record(record, campaign, fingerprint):
    return (record.get("fingerprint") == fingerprint and record.get("campaign") == campaign
            and all(key in record for key in ("ended_at", "validation", "cli_exit")))


def load_clock(path, fingerprint, now=None):
    now = time.time() if now is None else now
    if path.exists():
        clock = json.loads(path.read_text(encoding="utf-8"))
        if clock.get("fingerprint") != fingerprint:
            raise ValueError("campaign clock fingerprint不一致")
        return clock
    clock = {"fingerprint": fingerprint, "started_epoch": now,
             "deadline_epoch": now + LIMIT_SECONDS}
    path.write_text(json.dumps(clock, indent=2) + "\n", encoding="utf-8")
    return clock


def require_preflight(campaign_dir):
    """不合格ならモデルrunを開始させない。"""
    preflight_file = campaign_dir / "sandbox-preflight.json"
    preflight = subprocess.run([sys.executable, "-B", str(HERE / "sandbox_preflight.py")],
                               cwd=HERE, text=True, capture_output=True)
    preflight_file.write_text(preflight.stdout, encoding="utf-8")
    preflight_file.chmod(0o600)
    if preflight.returncode != 0:
        raise SystemExit(f"sandbox preflight失敗。モデルrunを開始しません: {preflight_file}")
    try:
        if not json.loads(preflight.stdout).get("passed"):
            raise SystemExit(f"sandbox preflight不合格。モデルrunを開始しません: {preflight_file}")
    except json.JSONDecodeError:
        raise SystemExit(f"sandbox preflight証跡が不正。モデルrunを開始しません: {preflight_file}")


def main():
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
    campaign_dir = WORK / campaign
    campaign_dir.mkdir(parents=True, exist_ok=True)
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
    for task, condition, repeat in schedule:
        remaining = clock["deadline_epoch"] - time.time()
        if remaining < 70:
            break
        run_file = campaign_dir / f"{task}-{condition}-{repeat}/.benchmark-result.json"
        if run_file.exists():
            recorded = json.loads(run_file.read_text(encoding="utf-8"))
            if not complete_record(recorded, campaign, fingerprint):
                raise SystemExit(f"resume不一致: {run_file}")
            results.append(recorded)
            continue
        if run_file.parent.exists():
            results.append({"task_id": task, "condition": condition, "repeat": repeat,
                            "infrastructure_error": "部分runが存在。自動再実行せず監査待ち"})
            continue
        run_dir = run_file.parent
        active = campaign_dir / "active-run.json"
        active.write_text(json.dumps({"task": task, "condition": condition, "repeat": repeat,
                                      "started_epoch": time.time()}, indent=2) + "\n", encoding="utf-8")
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
        active.unlink(missing_ok=True)
        if run_file.exists():
            results.append(json.loads(run_file.read_text(encoding="utf-8")))
        else:
            results.append({"task_id": task, "condition": condition, "repeat": repeat,
                            "infrastructure_error": error, "exit_code": code})
        print(f"{task} {condition}{repeat}: {results[-1].get('pass_preliminary', 'infra_error')}", flush=True)
        summary = {"schema": 1, "campaign": campaign, "fingerprint": fingerprint,
                   "planned_runs": len(schedule), "completed_records": len(results),
                   "elapsed_seconds": round(time.time() - clock["started_epoch"], 3),
                   "schedule": schedule, "results": results}
        summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"schema": 1, "planned_runs": len(schedule), "completed_records": len(results),
               "campaign": campaign, "fingerprint": fingerprint,
               "elapsed_seconds": round(time.time() - clock["started_epoch"], 3),
               "B_contract_sha256": {contract.parent.name: hashlib.sha256(contract.read_bytes()).hexdigest()
                                     for contract in contracts},
               "B_skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
               "schedule": schedule, "results": results}
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"summary: {summary_file}", flush=True)


if __name__ == "__main__":
    main()
