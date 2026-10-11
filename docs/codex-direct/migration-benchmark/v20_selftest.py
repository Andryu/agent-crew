#!/usr/bin/env python3
"""v20 offline ledger/schema/privacy regression tests. No Codex or model client is imported."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from unittest.mock import patch

import v20_diagnostic as v20
import v20_driver


class FakeRemote:
    def __init__(self):
        self.head_hash = "a" * 40
        self.records = [dict(x, type="historical_attempt") for x in v20.HISTORICAL]
        self.commits = {self.head_hash}
        self.mode = None
        self.pushes = 0

    def head(self):
        return None if self.mode == "missing" else self.head_hash

    def ls_remote(self):
        if self.mode == "missing" or self.head_hash is None:
            return None
        if self.mode == "rewritten":
            return "b" * 40
        return self.head_hash
    def chain(self, head):
        if self.mode == "unreachable":
            raise OSError("private fake unreachable detail")
        if self.mode == "mismatch":
            return []
        return self.records

    def push_ff(self, parent, payload):
        if self.mode == "non_ff":
            raise v20.LedgerError("remote_non_ff")
        if self.mode == "race":
            self.head_hash = "c" * 40
            raise v20.LedgerError("remote_competition")
        if parent != self.head_hash:
            raise v20.LedgerError("remote_non_ff")
        self.pushes += 1
        obj = v20.strict_json(payload)
        if "records" in obj:
            self.records = obj["records"]
        self.head_hash = hashlib.sha1((parent or "").encode() + payload).hexdigest()
        self.commits.add(self.head_hash)
        return self.head_hash


ROOT_ID = {"realpath_sha256": "c" * 64, "device": 1, "inode": 2}


def _report(**overrides):
    value = {"schema": 1, "attempt_id": "attempt", "fingerprint": "f" * 64,
             "environment_fit": "mismatch",
             "path": {"matched_profile": "normal_shell_login", "component_count": 2,
                      "unapproved_component_count": 0, "order_classification": "exact_profile"},
             "unknown_keys": {"codex_home_present": False, "classification": "none",
                              "unknown_count": 0, "other_unknown_count": 0},
             "determination": "resolved"}
    value.update(overrides)
    return value


PASS_EVIDENCE = {key: True for key in ("env", "runtime", "binding", "event", "scope", "residual", "cli")}


def schema_tests():
    expected = {"attempt_id": "attempt", "fingerprint": "f" * 64}
    valid = _report()
    assert v20.validate_report(valid, **expected) == valid
    duplicate = b'{"schema":1,"schema":1}'
    try:
        v20.strict_json(duplicate)
    except v20.LedgerError as exc:
        assert str(exc) == "duplicate_json_key"
    else:
        raise AssertionError("duplicate JSON key passed")
    nested_duplicate = b'{"outer":{"field":1,"field":2}}'
    try:
        v20.strict_json(nested_duplicate)
    except v20.LedgerError as exc:
        assert str(exc) == "duplicate_json_key"
    else:
        raise AssertionError("nested duplicate JSON key passed")
    invalid = []
    for val in (True, -1, 0.1, 129, "2"):
        p = _report()
        p["path"]["component_count"] = val
        invalid.append(p)
    p = _report(); p["path"]["unexpected"] = "PATH secret"; invalid.append(p)
    p = _report(); p["unknown_keys"]["unknown_count"] = 7; invalid.append(p)
    p = _report(); p["environment_fit"] = "unknown"; invalid.append(p)
    p = _report(); p["environment_fit"] = "pass"; p["path"]["matched_profile"] = "none"; p["path"]["order_classification"] = "known_components_reordered"; invalid.append(p)
    p = _report(); p["path"]["order_classification"] = "malformed"; invalid.append(p)
    p = _report(); p["unknown_keys"]["other_unknown_count"] = 1; p["unknown_keys"]["unknown_count"] = 2; p["unknown_keys"]["classification"] = "other_unknown_present"; p["determination"] = "inconclusive"; invalid.append(p)
    for item in invalid:
        try:
            v20.validate_report(item, **expected)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("tampered report accepted")
    for item in (_report(environment_fit="unknown", determination="inconclusive"),
                 _report(path={"matched_profile": "none", "component_count": 0,
                               "unapproved_component_count": 0, "order_classification": "malformed"},
                         determination="inconclusive")):
        try:
            v20.report_for_storage(item, attempt_id="attempt", fingerprint="f" * 64)
        except v20.LedgerError as exc:
            assert str(exc) == "diagnostic_inconclusive"
        else:
            raise AssertionError("unknown/malformed partial report was saveable")
    assert v20.fixed_error(ValueError("short-secret-42")) == "internal_error"
    return 15


def privacy_tests():
    secrets = ["qz7", "ordinary-value", "short-secret-42", "PATH:/tmp/private-component", "digest-candidate-0a91"]
    secret_names = ["SECRETISH_NAME", "/private/synthetic/path-entry"]
    cases = 0
    for secret in secrets:
        safe = v20.report_for_storage(_report(), attempt_id="attempt", fingerprint="f" * 64)
        bundles = [v20.artifact_bundle(report_bytes=safe),
                   v20.artifact_bundle(error=RuntimeError(secret)),
                   v20.artifact_bundle(error=v20.LedgerError("invocation_timeout"))]
        for index, bundle in enumerate(bundles):
            assert set(bundle) == v20.ARTIFACT_NAMES and bundle["raw.jsonl"] == b"" and bundle["answer.json"] == b""
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / f"case-{index}"
                v20.save_artifact_bundle(out, bundle)
                saved = b"".join(p.read_bytes() for p in out.iterdir())
                assert secret.encode() not in saved
                assert not any(name.encode() in saved for name in secret_names)
                assert not any(item.encode() in saved for item in secrets)
            cases += 1
    return cases


def path_and_unknown_tests():
    exact_hash = hashlib.sha256(v20.canonical_bytes(["/bin", "/usr/bin"])).hexdigest()
    profiles = {"normal_shell_login": exact_hash}
    known = frozenset({hashlib.sha256(b"/bin").hexdigest(), hashlib.sha256(b"/usr/bin").hexdigest()})
    assert v20.classify_path("/bin:/usr/bin", profiles, known)["order_classification"] == "exact_profile"
    assert v20.classify_path("/usr/bin:/bin", profiles, known)["order_classification"] == "known_components_reordered"
    assert v20.classify_path(None, profiles, known)["order_classification"] == "empty"
    assert v20.classify_path("/bin:/tmp/PRIVATE", profiles, known)["unapproved_component_count"] == 1
    assert v20.classify_path("/bin:\x00secret", profiles, known)["order_classification"] == "malformed"
    assert v20.classify_path(":".join("/bin" for _ in range(129)), profiles, known)["order_classification"] == "malformed"
    unknown = v20.classify_unknown_keys(["PATH", "CODEX_HOME", "SECRETISH_NAME"], frozenset({"PATH"}))
    assert unknown == {"codex_home_present": True, "classification": "mixed", "unknown_count": 2, "other_unknown_count": 1}
    assert "SECRETISH_NAME" not in repr(unknown)
    try:
        v20.classify_unknown_keys([f"K{i}" for i in range(129)], frozenset())
    except v20.LedgerError as exc:
        assert str(exc) == "unknown_key_inventory_invalid"
    else:
        raise AssertionError("unknown key overflow accepted")
    return 8


def _seed_local(ledger, remote):
    records = [dict(x, type="historical_attempt") for x in v20.HISTORICAL]
    # Provisioning is a test fixture only; this does not call bootstrap or a real remote.
    ledger._write_local(records, remote.head_hash)


def ledger_tests():
    cases = 0
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote)
        _seed_local(ledger, remote)
        # Remote mismatch, missing, rewritten, unreachable and chain divergence fail before a push.
        for mode in ("missing", "rewritten", "unreachable", "mismatch"):
            remote.mode = mode
            before = remote.pushes
            try:
                ledger.reserve(role="diagnostic", fingerprint="f" * 64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
            except (v20.LedgerError, OSError):
                pass
            else:
                raise AssertionError(f"remote {mode} accepted")
            assert remote.pushes == before
            remote.mode = None; cases += 1
        # Non-FF and a concurrent remote move fail closed.
        for mode in ("non_ff", "race"):
            previous_head = remote.head_hash
            remote.mode = mode
            try:
                ledger.reserve(role="diagnostic", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
            except v20.LedgerError:
                pass
            else:
                raise AssertionError("non-FF/race accepted")
            remote.mode = None
            if mode == "race":
                remote.head_hash = previous_head
            cases += 1
        # One diagnostic can be reserved and completed; duplicates, failed/inconclusive histories stop progression.
        record = ledger.reserve(role="diagnostic", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        diagnostic_report = _report(); diagnostic_report["attempt_id"] = record["id"]
        report_bytes = v20.report_for_storage(diagnostic_report, attempt_id=record["id"], fingerprint="f"*64)
        ledger.complete(record["id"], "completed_diagnostic", diagnostic_report=report_bytes)
        try:
            ledger.reserve(role="diagnostic", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("second diagnostic accepted")
        final = ledger.reserve(role="final_probe", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        ledger.complete(final["id"], "final_pass", gate_evidence=PASS_EVIDENCE)
        assert ledger.formal_gate("f"*64)
        first = ledger.reserve(role="formal_run", run_id="C1-A-1", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        ledger.complete(first["id"], "formal_run_pass", run_id="C1-A-1", gate_evidence=PASS_EVIDENCE)
        try:
            ledger.reserve(role="formal_run", run_id="C1-A-1", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("duplicate formal run accepted")
        # Same-time local ledger+seal rollback and local deletion are detected by remote anchor.
        good_ledger, good_seal = ledger.ledger.read_bytes(), ledger.seal.read_bytes()
        stale = dict(ledger._read_local()); stale["remote_head"] = "9" * 40
        v20._atomic(ledger.ledger, v20.canonical_bytes(stale))
        v20._atomic(ledger.seal, v20.canonical_bytes({"sequence": len(stale["records"]), "chain_sha256": v20.sha256(v20.canonical_bytes(stale["records"])), "remote_head": stale["remote_head"]}))
        try:
            ledger.reserve(role="formal_run", run_id="C1-A-2", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("simultaneous ledger+seal rollback passed")
        ledger.ledger.unlink(); ledger.seal.unlink()
        try:
            ledger.bootstrap(b'{"schema":1,"records":[]}\n')
        except v20.LedgerError as exc:
            assert str(exc) == "rebootstrap_forbidden"
        else:
            raise AssertionError("deleted local ledger allowed rebootstrap")
        assert remote.head_hash is not None
        cases += 7
    # A timeout cannot be masked by another fingerprint or a later PASS role.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        first = ledger.reserve(role="diagnostic", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        ledger.complete(first["id"], "timeout")
        for role in ("diagnostic", "final_probe"):
            try:
                ledger.reserve(role=role, fingerprint="e"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
            except v20.LedgerError:
                pass
            else:
                raise AssertionError("timeout was masked by a later phase/fingerprint")
    cases += 2
    # A failed final is permanent and cannot be retried under another fingerprint.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        diag = ledger.reserve(role="diagnostic", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        d = _report(); d["attempt_id"] = diag["id"]
        ledger.complete(diag["id"], "completed_diagnostic", diagnostic_report=v20.report_for_storage(d, attempt_id=diag["id"], fingerprint="f"*64))
        final = ledger.reserve(role="final_probe", fingerprint="e"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        ledger.complete(final["id"], "final_fail")
        try:
            ledger.reserve(role="final_probe", fingerprint="d"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("failed final probe retry accepted")
    cases += 1
    # A persisted seed pin is permanent even if both local files and the remote ref disappear.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        ledger.ledger.unlink(); ledger.seal.unlink(); remote.mode = "missing"; remote.seed_commit_pin = "e" * 40
        try:
            ledger.bootstrap(b'{"schema":1,"records":[]}\n')
        except v20.LedgerError as exc:
            assert str(exc) == "rebootstrap_forbidden"
        else:
            raise AssertionError("pinned all-deleted ledger allowed rebootstrap")
    cases += 1
    # Every failed bootstrap must not touch remote; expected SHA tampering is refused.
    remote = FakeRemote(); remote.head_hash = None
    with tempfile.TemporaryDirectory() as td:
        ledger = v20.GlobalLedger(Path(td) / "state", remote)
        try:
            ledger.bootstrap(b'{"schema":1,"records":[]}\n')
        except v20.LedgerError as exc:
            assert str(exc) == "seed_digest_mismatch"
        else:
            raise AssertionError("wrong seed accepted")
        assert remote.pushes == 0
    cases += 1
    # Bootstrap transport path with injected already-validated seed bytes; the production validator is tested separately.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); remote.head_hash = None
        ledger = v20.GlobalLedger(Path(td) / "state", remote)
        seed_records = [{"elapsed_seconds": x["elapsed_seconds"], "fingerprint": x["fingerprint"], "id": x["id"],
                         "result_sha256": x["result_sha256"], "state": x["state"],
                         "type": "historical_attempt", "version": x["version"]} for x in v20.HISTORICAL]
        seed_obj = {"schema": 1, "records": seed_records}
        payload = v20.canonical_bytes(seed_obj)
        with patch.object(v20, "validate_seed_payload", return_value=(seed_obj, v20.sha256(payload))):
            seed_commit = ledger.bootstrap(payload)
        assert remote.ls_remote() == seed_commit and ledger._read_local()["records"] == remote.chain(seed_commit)
    cases += 1
    # Remote reservation commit succeeded; a crash before local persistence still consumes its slot.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        with patch.object(ledger, "_write_local", side_effect=OSError("simulated crash")):
            try:
                ledger.reserve(role="diagnostic", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
            except OSError:
                pass
            else:
                raise AssertionError("crash injection missed")
        assert len(remote.records) == 3 and remote.records[-1]["state"] == "reserved"
        try:
            ledger.reserve(role="diagnostic", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("remote-consumed slot was retried")
    cases += 1
    # Exactly 28 records exhaust the immutable ceiling; no 29th reservation.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        filler = [dict(x) for x in remote.records]
        for i in range(26):
            start = 1000 + i
            filler.append({"sequence": len(filler) + 1, "id": f"{i:032x}", "role": "final_probe", "state": "final_pass",
                           "fingerprint": "f"*64, "root_identity": ROOT_ID, "spec_sha256": "a"*64,
                           "command_sha256": "b"*64, "pid": os.getpid(), "pgid": os.getpgrp(), "owner_uid": os.getuid(),
                           "started_epoch": start, "deadline_epoch": start + 600, "ended_epoch": start + 1,
                           "gate_evidence_sha256": "d"*64})
        remote.records = filler
        ledger._write_local(filler, remote.head_hash)
        try:
            ledger.reserve(role="formal_run", run_id="C1-A-1", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
        except v20.LedgerError as exc:
            assert str(exc) == "global_budget_exhausted"
        else:
            raise AssertionError("29th invocation accepted")
    cases += 1
    # Simultaneous callers serialize under flock; only one can claim diagnostic role.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        outcomes = []
        def contender():
            try:
                ledger.reserve(role="diagnostic", fingerprint="f"*64, root_identity=ROOT_ID, spec_sha256="a"*64, command_sha256="b"*64)
                outcomes.append("ok")
            except v20.LedgerError:
                outcomes.append("refused")
        threads = [threading.Thread(target=contender) for _ in range(2)]
        [t.start() for t in threads]; [t.join() for t in threads]
        assert sorted(outcomes) == ["ok", "refused"]
    cases += 1
    return cases


def gate_tests():
    hist = [dict(x, type="historical_attempt") for x in v20.HISTORICAL]
    diag = {"id": "a"*32, "role": "diagnostic", "state": "completed_diagnostic", "determination": "resolved", "report_sha256": "a"*64}
    final = {"id": "b"*32, "role": "final_probe", "state": "final_pass", "gate_evidence_sha256": "b"*64}
    assert v20.formal_start_eligible(hist + [diag, final])
    assert not v20.formal_start_eligible(hist + [{**diag, "determination": "inconclusive"}, final])
    assert not v20.formal_start_eligible(hist + [diag, {**final, "state": "final_fail"}])
    assert not v20.formal_start_eligible(hist + [diag, final, {"role": "unknown"}])
    runs = []
    for i, run_id in enumerate(f"C{c}-{side}-{repeat}" for c in range(1, 7) for side in ("A", "B") for repeat in (1, 2)):
        runs.append({"id": f"{i + 1:032x}", "role": "formal_run", "run_id": run_id,
                     "state": "formal_run_pass", "gate_evidence_sha256": "c"*64})
    assert v20.formal_complete(hist + [diag, final] + runs)
    assert not v20.formal_complete(hist + [diag, final] + runs[:-1])
    import contextlib
    import io
    for forbidden in ("diagnostic", "probe", "formal", "retry"):
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                v20_driver.main([forbidden])
        except SystemExit as exc:
            assert exc.code == 2 and stderr.getvalue() == "v20_fixed_artifact_invalid\n"
        else:
            raise AssertionError("fixed driver exposed a non-verify operation")
    return 8


def git_remote_fixture_tests():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); bare = root / "remote.git"; repo = root / "client"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(bare)], check=True, capture_output=True)
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "--initial-branch=main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "P5 Fixture"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "p5-fixture-local"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(bare)], check=True, capture_output=True)
        adapter = v20.GitRemote(repo)
        history = [dict(x, type="historical_attempt") for x in v20.HISTORICAL]
        seed = v20.canonical_bytes({"schema": 1, "records": history})
        normalized = {"schema": 1, "records": history}
        with patch.object(v20, "validate_seed_payload", return_value=(normalized, v20.sha256(seed))):
            first = adapter.push_ff(None, seed)
            adapter.seed_commit_pin = first
            assert adapter.ls_remote() == first and adapter.chain(first) == history
        second = adapter.push_ff(first, v20.canonical_bytes({"schema": 1, "version": 20, "records": history}))
        assert adapter.ls_remote() == second and adapter.chain(second) == history
        try:
            adapter.push_ff(first, v20.canonical_bytes({"schema": 1, "version": 20, "records": history}))
        except v20.LedgerError as exc:
            assert str(exc) == "remote_head_changed"
        else:
            raise AssertionError("fixture remote accepted stale non-FF parent")
        assert adapter.ls_remote() == second
    return 3


def run_all():
    counts = {"schema": schema_tests(), "privacy": privacy_tests(), "path_unknown": path_and_unknown_tests(),
              "ledger": ledger_tests(), "formal_gate": gate_tests(), "remote_fixture": git_remote_fixture_tests()}
    return counts


if __name__ == "__main__":
    counts = run_all()
    print("v20 selftest: PASS " + json.dumps(counts, sort_keys=True))
