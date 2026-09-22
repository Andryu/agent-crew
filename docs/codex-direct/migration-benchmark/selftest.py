#!/usr/bin/env python3
"""有料CLIを呼ばずに隔離、成功、失敗、timeoutを確認する。"""

import importlib.util
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().with_name("run.py")
SPEC = importlib.util.spec_from_file_location("p5_run", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
BATCH_SPEC = importlib.util.spec_from_file_location("p5_batch", SCRIPT.with_name("batch.py"))
batch = importlib.util.module_from_spec(BATCH_SPEC)
BATCH_SPEC.loader.exec_module(batch)

FAKE = '''#!/usr/bin/env python3
import json,os,subprocess,sys,time
if "--version" in sys.argv:
    print("codex-cli 0.155.1")
    raise SystemExit(0)
if "sandbox" in sys.argv:
    command = sys.argv[sys.argv.index("--")+1:]
    if "unittest" in command:
        raise SystemExit(0)
    raise SystemExit(subprocess.run(command).returncode)
if os.getenv("FAKE_CLI_MODE") == "sleep":
    time.sleep(2)
    raise SystemExit(0)
if os.getenv("FAKE_CLI_MODE") == "fail":
    raise SystemExit(1)
if os.getenv("FAKE_CLI_MODE") == "c6":
    root = sys.argv[sys.argv.index("-C") + 1]
    subprocess.run([sys.executable, "-B", "migration-progress/progress.py", "set",
                    "--task", "P0", "--status", "検証中", "--current", "fake更新",
                    "--next", "fake再読込", "--blocker", "なし"], cwd=root, check=True)
answer = sys.argv[sys.argv.index("-o")+1]
open(answer,"w").write("目的 検証 次の一手\\n")
print(json.dumps({"type":"item.completed","item":{"type":"command_execution","command":"python3.12 -B -m unittest discover -s tests -p test_crew_launcher.py -v","exit_code":0,"aggregated_output":"OK"}}))
print(json.dumps({"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}))
'''


def c6_safety_selftest():
    """C1の既知cleanup障害より前に、C6境界の異常系を単独で確認する。"""
    # managed sandboxが作るmountは削除拒否になり得る。/private/tmpの生成rootだけを対象にし、
    # cleanup失敗を検証失敗にしない（ここで手動rmはしない）。
    with tempfile.TemporaryDirectory(prefix="p5-c6-safety-", dir="/private/tmp",
                                     ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        progress = root / "migration-progress"
        progress.mkdir()
        source = runner.BASE / "snapshot/agent_crew/migration-progress"
        for name in ("progress.py", "README.md"):
            shutil.copy2(source / name, progress / name)
        shutil.copy2(runner.BASE / "fixtures/board-state.json", progress / "state.json")
        before = runner.sha(progress / "state.json")
        validator = SCRIPT.with_name("validate_c6.py")
        base = [sys.executable, "-B", str(validator), "--state-before-sha256", before,
                "--progress-sha256", runner.sha(progress / "progress.py"),
                "--readme-sha256", runner.sha(progress / "README.md")]
        # 未更新・progress改変・不完全stateは、それぞれ独立に不合格になる。
        assert subprocess.run(base, cwd=root, capture_output=True, text=True).returncode == 1
        with (progress / "progress.py").open("a", encoding="utf-8") as handle:
            handle.write("\n# changed\n")
        assert subprocess.run(base, cwd=root, capture_output=True, text=True).returncode == 1
        shutil.copy2(source / "progress.py", progress / "progress.py")
        (progress / "state.json").write_text(json.dumps({"schema": 1, "tasks": {"P0": {}}}), encoding="utf-8")
        assert subprocess.run(base, cwd=root, capture_output=True, text=True).returncode == 1
        (progress / "state.json").unlink()
        (progress / "state.json").symlink_to("missing-state.json")
        assert subprocess.run(base, cwd=root, capture_output=True, text=True).returncode == 1
        (progress / "state.json").unlink()
        symlink_root = root / "intermediate-symlink"
        symlink_root.mkdir()
        (symlink_root / "migration-progress").symlink_to(progress, target_is_directory=True)
        assert subprocess.run(base, cwd=symlink_root, capture_output=True, text=True).returncode == 1
        assert runner.preliminary_pass(0, 0, [], True, False) is False
        c6_allowed = {"migration-progress/state.json"}
        c6_modified = ["docs/plans/unexpected.md"]
        c6_scope = [name for name in c6_modified if name not in c6_allowed]
        assert c6_scope == ["docs/plans/unexpected.md"]
        # 壊れsymlink validatorは上書きしない。sandbox実行はfakeで置換する。
        target = root / "validate_c6.py"
        target.symlink_to("missing-validator.py")
        task = runner.c6_task()
        original = runner.execute_group
        runner.execute_group = lambda *_args, **_kwargs: (0, "", "")
        try:
            try:
                runner.validate(task, root, c6_state_before=before,
                                c6_readonly={"progress": runner.sha(progress / "progress.py"),
                                             "readme": runner.sha(progress / "README.md")})
            except RuntimeError as error:
                assert "上書きしません" in str(error)
            else:
                raise AssertionError("壊れvalidator symlinkを上書きした")
        finally:
            runner.execute_group = original
        original_run = batch.subprocess.run
        batch.subprocess.run = lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="{}")
        try:
            try:
                batch.require_preflight(root)
            except SystemExit:
                pass
            else:
                raise AssertionError("preflight失敗後もbatchが続行した")
        finally:
            batch.subprocess.run = original_run
        print("P5 C6 safety selftest: readonly/state/symlink/host-guard/batch-gate OK", flush=True)


def main():
    c6_safety_selftest()
    # 同上。生成rootは/private/tmpに限定し、cleanup EPERMで本体の検証結果を覆さない。
    with tempfile.TemporaryDirectory(prefix="p5-selftest-", dir="/private/tmp",
                                     ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "codex"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        original_path = os.environ.get("PATH", "")
        original_mode = os.environ.get("FAKE_CLI_MODE")
        original_work = runner.WORK
        original_timeout = runner.CLI_TIMEOUT_SECONDS
        try:
            assert len(runner.verified_a_inputs()) == 1
            assert len(runner.verified_b_inputs()) == 7
            clock_file = root / "campaign-clock.json"
            clock = batch.load_clock(clock_file, "fixture-fingerprint", now=1000)
            assert clock["deadline_epoch"] == 1000 + batch.LIMIT_SECONDS
            assert batch.load_clock(clock_file, "fixture-fingerprint", now=2000) == clock
            assert clock["deadline_epoch"] - 2000 == batch.LIMIT_SECONDS - 1000
            try:
                batch.load_clock(clock_file, "wrong", now=2000)
            except ValueError:
                pass
            else:
                raise AssertionError("campaign clock fingerprint不一致を見逃した")
            os.environ["PATH"] = str(bin_dir) + os.pathsep + original_path
            runner.WORK = root / "formal"
            args = SimpleNamespace(task="C1", condition="A", repeat=1,
                                   campaign="test-fixed", fingerprint="fixture-fingerprint")
            runner.run(args)
            result_file = runner.WORK / "test-fixed/C1-A-1/.benchmark-result.json"
            result = json.loads(result_file.read_text())
            assert result["pass_preliminary"] is True
            assert result["input_tokens"] == 12
            assert result["fingerprint"] == "fixture-fingerprint"
            assert batch.complete_record(result, "test-fixed", "fixture-fingerprint")
            assert not batch.complete_record(result, "wrong", "fixture-fingerprint")
            assert not batch.complete_record({"campaign":"test-fixed"}, "test-fixed", "fixture-fingerprint")
            events = json.loads(result_file.with_name(".benchmark-events.json").read_text())
            assert events["commands"][0]["exit_code"] == 0
            assert not (root / "C1-A-1").exists()  # 旧smokeと正式campaignの分離
            c6_args = SimpleNamespace(task="C6", condition="A", repeat=1,
                                      campaign="test-fixed", fingerprint="fixture-fingerprint")
            os.environ["FAKE_CLI_MODE"] = "c6"
            runner.run(c6_args)
            os.environ.pop("FAKE_CLI_MODE", None)
            c6_root = runner.WORK / "test-fixed/C6-A-1"
            c6 = json.loads((c6_root / ".benchmark-result.json").read_text())
            assert c6["validation"]["command"] == [
                "python3.12", "-B", "validate_c6.py", "--state-before-sha256",
                runner.sha(runner.BASE / "fixtures/board-state.json"),
                "--progress-sha256", runner.sha(c6_root / "migration-progress/progress.py"),
                "--readme-sha256", runner.sha(c6_root / "migration-progress/README.md"),
            ]
            assert c6["validation"]["exit_code"] == 0
            assert c6["pass_preliminary"] is True
            assert "--sandbox" not in c6["validation"]["command"]
            assert c6["input_hashes"]["comparison-v2.json"] == runner.sha(
                SCRIPT.with_name("comparison-v2.json")
            )
            assert c6["input_hashes"]["validate_c6.py"] == runner.sha(
                SCRIPT.with_name("validate_c6.py")
            )
            comparison = runner.load(runner.BASE / "comparison.json")
            snapshot_index = runner.load(runner.BASE / "snapshot-index.json")
            a_contracts = [entry for entry in snapshot_index["entries"]
                           if entry["snapshot"] in comparison["A_instruction_snapshot"]]
            assert len(a_contracts) == len(comparison["A_instruction_snapshot"])
            for entry in a_contracts:
                assert runner.sha(c6_root / entry["source"]) == entry["sha256"]
            c6_validation = json.loads(c6["validation"]["stdout_tail"])
            accepted_root = c6_root.parent / ".accepted" / c6_root.name
            accepted_state = accepted_root / "migration-progress/state.json"
            assert c6_validation == {"ok": True, "state_changed": True,
                                     "p0_status": "検証中", "reload_exit_code": 0,
                                     "state_sha256": runner.sha(accepted_state)}
            assert c6["accepted_state_sha256"] == runner.sha(accepted_state)
            assert c6["c6_validator_consistent"] is True
            assert not (c6_root / "docs/codex-direct/migration-baseline").exists()
            assert (c6_root / "migration-progress/state.json").read_bytes() != (
                runner.BASE / "fixtures/board-state.json").read_bytes()
            # accepted copy後の元fixture改変は、正式snapshotと既に確定した結果へ影響しない。
            c6_root.joinpath("migration-progress/state.json").write_text(
                json.dumps({"schema": 1, "tasks": {"P0": {}}}), encoding="utf-8"
            )
            assert runner.sha(accepted_state) == c6["accepted_state_sha256"]
            accepted_check = subprocess.run(c6["validation"]["command"], cwd=accepted_root,
                                            capture_output=True, text=True)
            assert accepted_check.returncode == 0
            assert json.loads(accepted_check.stdout)["state_sha256"] == c6["accepted_state_sha256"]
            assert json.loads((c6_root / ".benchmark-result.json").read_text())["pass_preliminary"] is True
            c6_b_root, _, _ = runner.prepare("C6", "B", 1, "test-fixed")
            assert not (c6_b_root / "docs/codex-direct/migration-baseline").exists()
            assert runner.sha(c6_b_root / "AGENTS.md") == runner.load(runner.B_INDEX)["files"]["agent_crew/AGENTS.md"]
            b_skill = ".agents/skills/fable-class/SKILL.md"
            assert runner.sha(c6_b_root / b_skill) == runner.load(runner.B_INDEX)["files"][f"agent_crew/{b_skill}"]
            for entry in a_contracts:
                destination = c6_b_root / entry["source"]
                assert destination.is_file(), f"B C6入力が不足: {entry['source']}"
                assert runner.sha(destination) != entry["sha256"], f"B C6にA契約が残存: {entry['source']}"
            before_c6_b = runner.sha(c6_b_root / "migration-progress/state.json")
            invalid_c6 = subprocess.run(
                [sys.executable, "-B", str(SCRIPT.with_name("validate_c6.py")),
                 "--state-before-sha256", before_c6_b,
                 "--progress-sha256", runner.sha(c6_b_root / "migration-progress/progress.py"),
                 "--readme-sha256", runner.sha(c6_b_root / "migration-progress/README.md")], cwd=c6_b_root,
                capture_output=True, text=True,
            )
            assert invalid_c6.returncode == 1
            assert "更新されていません" in invalid_c6.stdout
            try:
                runner.run(args)
            except RuntimeError as error:
                assert "上書きしません" in str(error)
            else:
                raise AssertionError("resumeが既存runを上書きした")
            os.environ["FAKE_CLI_MODE"] = "sleep"
            runner.CLI_TIMEOUT_SECONDS = 0.1
            timeout_args = SimpleNamespace(task="C1", condition="A", repeat=2,
                                           campaign="test-fixed", fingerprint="fixture-fingerprint")
            runner.run(timeout_args)
            timeout = json.loads((runner.WORK / "test-fixed/C1-A-2/.benchmark-result.json").read_text())
            assert timeout["cli_exit"] == "timeout"
            assert timeout["pass_preliminary"] is False
            os.environ["FAKE_CLI_MODE"] = "fail"
            runner.CLI_TIMEOUT_SECONDS = original_timeout
            failed_args = SimpleNamespace(task="C2", condition="A", repeat=1,
                                          campaign="test-fixed", fingerprint="fixture-fingerprint")
            runner.run(failed_args)
            failed = json.loads((runner.WORK / "test-fixed/C2-A-1/.benchmark-result.json").read_text())
            assert failed["cli_exit"] == 1
            assert failed["pass_preliminary"] is False
            os.environ.pop("FAKE_CLI_MODE", None)
            a_wealth = SimpleNamespace(task="C5", condition="A", repeat=1,
                                       campaign="test-fixed", fingerprint="fixture-fingerprint")
            b_wealth = SimpleNamespace(task="C5", condition="B", repeat=1,
                                       campaign="test-fixed", fingerprint="fixture-fingerprint")
            runner.run(a_wealth)
            runner.run(b_wealth)
            a_root = runner.WORK / "test-fixed/C5-A-1"
            b_root = runner.WORK / "test-fixed/C5-B-1"
            shared = ["scripts/check_operational_readiness.py", "tests/test_operational_readiness.py"]
            assert all((a_root / name).read_bytes() == (b_root / name).read_bytes() for name in shared)
            skill = ".agents/skills/wealth-advisor/SKILL.md"
            assert runner.sha(a_root / skill) == runner.load(runner.A_INDEX)["source_sha256"]
            assert runner.sha(b_root / skill) == runner.load(runner.B_INDEX)["files"][f"wealth_advisor/{skill}"]
            assert runner.sha(a_root / skill) != runner.sha(b_root / skill)
            for label in ("cli", "validator"):
                marker = root / f"{label}-grandchild-alive.txt"
                grandchild = f'from pathlib import Path; import time; time.sleep(0.5); Path({str(marker)!r}).write_text("alive")'
                parent = ('import subprocess,sys,time; '
                          f'subprocess.Popen([sys.executable,"-c",{grandchild!r}]); time.sleep(3)')
                code, _, _ = runner.execute_group([sys.executable, "-B", "-c", parent], root,
                                                   runner.limited_env(root), 0.1)
                assert code == "timeout"
                time.sleep(0.7)
                assert not marker.exists(), f"{label}孫processがtimeout後に生存"
            normal_marker = root / "normal-grandchild-alive.txt"
            normal_child = f'from pathlib import Path; import time; time.sleep(0.5); Path({str(normal_marker)!r}).write_text("alive")'
            normal_parent = ('import subprocess,sys; '
                             f'subprocess.Popen([sys.executable,"-c",{normal_child!r}],'
                             'stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)')
            code, _, _ = runner.execute_group([sys.executable, "-B", "-c", normal_parent], root,
                                               runner.limited_env(root), 3)
            assert code == 0
            time.sleep(0.7)
            assert not normal_marker.exists(), "正常終了後に孫processが生存"
            outer_marker = root / "outer-grandchild-alive.txt"
            grandchild = f'from pathlib import Path; import time; time.sleep(0.5); Path({str(outer_marker)!r}).write_text("alive")'
            parent = ('import subprocess,sys,time; '
                      f'subprocess.Popen([sys.executable,"-c",{grandchild!r}]); time.sleep(3)')
            helper = (
                'import importlib.util,pathlib,signal,sys; '
                f's=importlib.util.spec_from_file_location("p5",{str(SCRIPT)!r}); '
                'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
                'signal.signal(signal.SIGTERM,m.terminate_handler); '
                f'm.execute_group([sys.executable,"-B","-c",{parent!r}],'
                f'pathlib.Path({str(root)!r}),m.limited_env(pathlib.Path({str(root)!r})),3)'
            )
            helper_proc = subprocess.Popen([sys.executable, "-B", "-c", helper],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           start_new_session=True)
            active = root / ".benchmark-active-pgid"
            for _ in range(50):
                if active.exists():
                    break
                time.sleep(0.01)
            assert active.exists(), "外側timeout試験の子group未起動"
            helper_proc.terminate()
            helper_proc.wait(timeout=3)
            time.sleep(0.7)
            assert not outer_marker.exists(), "外側SIGTERM後に孫processが生存"
        finally:
            os.environ["PATH"] = original_path
            if original_mode is None:
                os.environ.pop("FAKE_CLI_MODE", None)
            else:
                os.environ["FAKE_CLI_MODE"] = original_mode
            runner.WORK = original_work
            runner.CLI_TIMEOUT_SECONDS = original_timeout
    print("P5 fake CLI selftest: A/B wealth inputs, success/fail, resume/clock, timeouts/grandchildren, smoke isolation OK")


if __name__ == "__main__":
    main()
