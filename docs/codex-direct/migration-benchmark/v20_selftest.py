#!/usr/bin/env python3
"""v20 offline ledger/schema/privacy regression tests. No Codex or model client is imported."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
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
        return json.loads(json.dumps(self.records))

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


_BINDING_TMP = tempfile.TemporaryDirectory(prefix="p5-v20-binding-fixture-")
_BINDING_ROOT = Path(_BINDING_TMP.name).resolve(strict=True)
ROOT_ID = None
TRUSTED_ID = "a" * 32
TRUSTED_FP = "f" * 64
PREFLIGHT_SHA = "c" * 64
MANIFEST_SHA = "d" * 64


_BINDINGS = {}


def _binding(label=TRUSTED_FP, *, root=None, marker="a"):
    key = (label, marker)
    if key in _BINDINGS:
        return json.loads(json.dumps(_BINDINGS[key]))
    artifact_root = Path(v20.__file__).resolve().parent
    manifest_bytes = (artifact_root / "manifest.json").read_bytes()
    manifest_path = artifact_root / "manifest.json"
    manifest_info = manifest_path.lstat()
    config = v20.strict_json((artifact_root / "config.json").read_bytes())
    run_root = _BINDING_ROOT / f"run-{len(_BINDINGS):03d}"
    run_root.mkdir(mode=0o700)
    preflight_path = run_root / "preflight.json"
    preflight_bytes = v20.canonical_bytes({"schema": 1, "version": 20,
        "fingerprint": v20.strict_json(manifest_bytes)["fingerprint"],
        "manifest_sha256": v20.sha256(manifest_bytes),
        "files": v20.strict_json(manifest_bytes)["files"], "runtime_bindings": {},
        "selftest_counts": {"fixture": 1}, "model_calls": 0, "probe_attempts": 0,
        "formal_runs": 0, "result": "pass"})
    preflight_path.write_bytes(preflight_bytes); preflight_path.chmod(0o400)
    info = run_root.lstat()
    identity = {"realpath": str(run_root.resolve(strict=True)), "device": info.st_dev, "inode": info.st_ino}
    spec = config["binding_spec_sha256"]
    command = config["command_sha256"]
    preflight_hash = v20.sha256(preflight_bytes)
    phase_fp = v20.sha256(v20.canonical_bytes({"artifact_fingerprint": v20.strict_json(manifest_bytes)["fingerprint"],
        "root_identity": identity, "spec_sha256": spec, "command_sha256": command,
        "preflight_sha256": preflight_hash}))
    result = {"fingerprint": phase_fp, "root_identity": identity, "artifact_root": str(artifact_root),
        "preflight_path": str(preflight_path), "spec_sha256": spec, "command_sha256": command,
        "preflight_sha256": preflight_hash, "manifest_sha256": v20.sha256(manifest_bytes),
        "manifest_identity": {"absolute_path": str(manifest_path.absolute()),
            "realpath": str(manifest_path.resolve(strict=True)), "device": manifest_info.st_dev,
            "inode": manifest_info.st_ino, "owner": manifest_info.st_uid,
            "mode": __import__("stat").S_IMODE(manifest_info.st_mode)}}
    _BINDINGS[key] = result
    return json.loads(json.dumps(result))


def _complete_from_saved(ledger, record, state, binding, *, next_binding=None, run_id=None):
    """Tests use the same trusted saver and path-based verifier as production."""
    with tempfile.TemporaryDirectory() as td:
        directory = Path(td) / "evidence"
        if state == "completed_diagnostic":
            report = _report(); report["attempt_id"] = record["id"]; report["fingerprint"] = binding["fingerprint"]
            payload = v20.canonical_bytes(report)
        else:
            payload = v20.canonical_bytes({"schema": 1, "attempt_id": record["id"], "role": record["role"],
                "run_id": record.get("run_id"), "fingerprint": binding["fingerprint"], "gates": PASS_EVIDENCE})
        result_path, sidecar_path = v20.save_verified_result(directory, attempt_id=record["id"],
            role=record["role"], run_id=record.get("run_id"), binding=binding, result_bytes=payload)
        return ledger.complete(record["id"], state, binding=binding, result_artifact_path=result_path,
            evidence_sidecar_path=sidecar_path, next_binding=next_binding, run_id=run_id)


def _report(**overrides):
    value = {"schema": 1, "attempt_id": TRUSTED_ID, "fingerprint": TRUSTED_FP,
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
    expected = {"attempt_id": TRUSTED_ID, "fingerprint": TRUSTED_FP}
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
    p = _report(); p["path"]["component_count"] = 1; p["path"]["unapproved_component_count"] = 2
    try:
        v20.report_for_storage(p, attempt_id=TRUSTED_ID, fingerprint=TRUSTED_FP,
                               binding_sha256=v20.binding_digest(_binding()))
    except v20.LedgerError as exc:
        assert str(exc) == "diagnostic_inconclusive"
    else:
        raise AssertionError("unapproved PATH count greater than total persisted")
    for item in (_report(environment_fit="unknown", determination="inconclusive"),
                 _report(path={"matched_profile": "none", "component_count": 0,
                               "unapproved_component_count": 0, "order_classification": "malformed"},
                         determination="inconclusive")):
        try:
            v20.report_for_storage(item, attempt_id=TRUSTED_ID, fingerprint=TRUSTED_FP,
                                   binding_sha256=v20.binding_digest(_binding()))
        except v20.LedgerError as exc:
            assert str(exc) == "diagnostic_inconclusive"
        else:
            raise AssertionError("unknown/malformed partial report was saveable")
    assert v20.fixed_error(ValueError("short-secret-42")) == "internal_error"
    return 16


def seed_canonical_tests():
    # Derive the approved bytes independently from the production serializer.
    history = [{"elapsed_seconds": item["elapsed_seconds"], "fingerprint": item["fingerprint"],
                "id": item["id"], "result_sha256": item["result_sha256"], "state": item["state"],
                "type": "historical_attempt", "version": item["version"]} for item in v20.HISTORICAL]
    root = {"schema": 1, "records": history}
    expected = (json.dumps(root, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    fixture = Path(__file__).with_name("v20_seed_fixture.json").read_bytes()
    assert expected == fixture
    digest = "f5cb2275c0b4c397e76dea473809c8e56da7a3f0f7aceb1c0cdfe277cdd979c8"
    assert hashlib.sha256(expected).hexdigest() == digest == v20.SEED_SHA256
    assert v20.validate_seed_payload(expected) == (root, digest)

    mutations = [
        expected.replace(b'{"records":', b'{"extra":0,"records":', 1),
        v20.canonical_bytes({"schema": 1}),
        b'{"schema":1,"schema":1,"records":' + expected.split(b'"records":', 1)[1],
        v20.canonical_bytes({"schema": 1, "records": list(reversed(history))}),
        v20.canonical_bytes({"schema": 1, "records": [dict(history[0], extra=0), history[1]]}),
        v20.canonical_bytes({"schema": 1, "records": [dict(history[0], version=True), history[1]]}),
        expected.replace(repr(history[0]["elapsed_seconds"]).encode("ascii"),
                         bytes([49, 46, 49, 49, 54, 53, 48, 52, 51, 49, 49, 53, 54, 49, 53, 56, 52, 53, 101, 49]), 1),
        expected[:-1], expected + b"\n",
        b'{"schema":1,"records":' + expected.split(b'"records":', 1)[1].rsplit(b',"schema":1}', 1)[0] + b'}\n',
        json.dumps(root, ensure_ascii=False, sort_keys=False, separators=(",", ":")).encode("utf-8") + b"\n",
    ]
    for payload in mutations:
        try:
            with patch.object(v20, "SEED_SHA256", hashlib.sha256(payload).hexdigest()):
                v20.validate_seed_payload(payload)
        except v20.LedgerError:
            continue
        raise AssertionError("noncanonical or altered historical seed accepted")
    return 1 + len(mutations)


def privacy_tests():
    secrets = ["qz7", "ordinary-value", "short-secret-42", "PATH:/tmp/private-component", "digest-candidate-0a91"]
    secret_names = ["SECRETISH_NAME", "/private/synthetic/path-entry"]
    cases = 0
    trusted = {"trusted_attempt_id": TRUSTED_ID, "trusted_fingerprint": TRUSTED_FP,
               "trusted_binding_sha256": v20.binding_digest(_binding())}
    for secret in secrets:
        safe = v20.report_for_storage(_report(), attempt_id=TRUSTED_ID, fingerprint=TRUSTED_FP,
                                      binding_sha256=trusted["trusted_binding_sha256"])
        bundles = [v20.artifact_bundle(report_bytes=safe, **trusted),
                   v20.artifact_bundle(error=RuntimeError(secret), **trusted),
                   v20.artifact_bundle(error=v20.LedgerError("invocation_timeout"), **trusted)]
        for index, bundle in enumerate(bundles):
            assert set(bundle) == v20.ARTIFACT_NAMES and bundle["raw.jsonl"] == b"" and bundle["answer.json"] == b""
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / f"case-{index}"
                v20.save_artifact_bundle(out, bundle, **trusted)
                saved = b"".join(p.read_bytes() for p in out.iterdir())
                assert secret.encode() not in saved
                assert not any(name.encode() in saved for name in secret_names)
                assert not any(item.encode() in saved for item in secrets)
            cases += 1
    setters = [lambda x, v: x.__setitem__("attempt_id", v), lambda x, v: x.__setitem__("fingerprint", v),
               lambda x, v: x.__setitem__("environment_fit", v),
               lambda x, v: x.__setitem__("determination", v),
               lambda x, v: x["path"].__setitem__("matched_profile", v),
               lambda x, v: x["path"].__setitem__("order_classification", v),
               lambda x, v: x["unknown_keys"].__setitem__("classification", v)]
    for field_setter in setters:
        for secret in ("qz7", "ordinary-value", "high-entropy-synthetic-7c4e8a1d"):
            tampered = _report(); field_setter(tampered, secret)
            try:
                v20.artifact_bundle(report_bytes=v20.canonical_bytes(tampered), **trusted)
            except v20.LedgerError:
                pass
            else:
                raise AssertionError("string field sentinel accepted for persistence")
            cases += 1
    for secret in secrets + secret_names:
        unsafe = v20.artifact_bundle(error=RuntimeError(secret), **trusted)
        unsafe["stdout.txt"] = secret.encode()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "unsafe"
            try:
                v20.save_artifact_bundle(out, unsafe, **trusted)
            except v20.LedgerError:
                pass
            else:
                raise AssertionError("save API persisted caller-supplied raw string")
            assert not out.exists()
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
                ledger.reserve(role="diagnostic", binding=_binding("f" * 64))
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
                ledger.reserve(role="diagnostic", binding=_binding("f"*64))
            except v20.LedgerError:
                pass
            else:
                raise AssertionError("non-FF/race accepted")
            remote.mode = None
            if mode == "race":
                remote.head_hash = previous_head
            cases += 1
        # One diagnostic can be reserved and completed; duplicates, failed/inconclusive histories stop progression.
        record = ledger.reserve(role="diagnostic", binding=_binding("f"*64))
        _complete_from_saved(ledger, record, "completed_diagnostic", _binding("f"*64), next_binding=_binding("e"*64))
        try:
            ledger.reserve(role="diagnostic", binding=_binding("f"*64))
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("second diagnostic accepted")
        try:
            ledger.reserve(role="final_probe", binding=_binding("f"*64))
        except v20.LedgerError as exc:
            assert str(exc) == "final_probe_gate_not_satisfied"
        else:
            raise AssertionError("diagnostic binding reused for final role")
        final = ledger.reserve(role="final_probe", binding=_binding("e"*64))
        _complete_from_saved(ledger, final, "final_pass", _binding("e"*64), next_binding=_binding("2"*64))
        assert ledger.formal_gate(_binding("2"*64))
        first = ledger.reserve(role="formal_run", run_id="C1-A-1", binding=_binding("2"*64))
        _complete_from_saved(ledger, first, "formal_run_pass", _binding("2"*64), run_id="C1-A-1")
        try:
            ledger.reserve(role="formal_run", run_id="C1-A-1", binding=_binding("2"*64))
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("duplicate formal run accepted")
        try:
            ledger.reserve(role="formal_run", run_id="C1-A-2", binding=_binding("3"*64))
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("formal campaign binding changed")
        second = ledger.reserve(role="formal_run", run_id="C1-A-2", binding=_binding("2"*64))
        try:
            _complete_from_saved(ledger, second, "formal_run_pass", _binding("2"*64), run_id="C1-A-1")
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("formal run id was mutable at completion")
        _complete_from_saved(ledger, second, "formal_run_pass", _binding("2"*64), run_id="C1-A-2")
        # Same-time local ledger+seal rollback and local deletion are detected by remote anchor.
        good_ledger, good_seal = ledger.ledger.read_bytes(), ledger.seal.read_bytes()
        stale = dict(ledger._read_local()); stale["remote_head"] = "9" * 40
        v20._atomic(ledger.ledger, v20.canonical_bytes(stale))
        v20._atomic(ledger.seal, v20.canonical_bytes({"sequence": len(stale["records"]), "chain_sha256": v20.sha256(v20.canonical_bytes(stale["records"])), "remote_head": stale["remote_head"]}))
        try:
            ledger.reserve(role="formal_run", run_id="C1-A-3", binding=_binding("2"*64))
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
        cases += 10
    # A timeout cannot be masked by another fingerprint or a later PASS role.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        first = ledger.reserve(role="diagnostic", binding=_binding("f"*64))
        ledger.complete(first["id"], "timeout", binding=_binding("f"*64))
        for role in ("diagnostic", "final_probe"):
            try:
                ledger.reserve(role=role, binding=_binding("e"*64))
            except v20.LedgerError:
                pass
            else:
                raise AssertionError("timeout was masked by a later phase/fingerprint")
    cases += 2
    # A failed final is permanent and cannot be retried under another fingerprint.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        diag = ledger.reserve(role="diagnostic", binding=_binding("f"*64))
        _complete_from_saved(ledger, diag, "completed_diagnostic", _binding("f"*64), next_binding=_binding("e"*64))
        final = ledger.reserve(role="final_probe", binding=_binding("e"*64))
        ledger.complete(final["id"], "final_fail", binding=_binding("e"*64))
        try:
            ledger.reserve(role="final_probe", binding=_binding("d"*64))
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
                ledger.reserve(role="diagnostic", binding=_binding("f"*64))
            except OSError:
                pass
            else:
                raise AssertionError("crash injection missed")
        assert len(remote.records) == 3 and remote.records[-1]["state"] == "reserved"
        try:
            ledger.reserve(role="diagnostic", binding=_binding("f"*64))
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("remote-consumed slot was retried")
    cases += 1
    # Exactly 28 records exhaust the immutable ceiling; no 29th reservation.
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        filler = [dict(x) for x in remote.records]
        run_ids = [f"C{c}-{side}-{n}" for c in range(1, 7) for side in ("A", "B") for n in (1, 2)]
        formal_binding = _binding("2"*64)
        for i in range(26):
            role = "diagnostic" if i == 0 else "final_probe" if i == 1 else "formal_run"
            fp = "f"*64 if i == 0 else "e"*64 if i == 1 else "2"*64
            binding = _binding(fp); digest = v20.binding_digest(binding); attempt_id = f"{i+1:032x}"
            record = {"sequence": len(filler) + 1, "id": attempt_id, "role": role,
                      "state": "completed_diagnostic" if i == 0 else "final_pass" if i == 1 else "formal_run_pass",
                      "fingerprint": binding["fingerprint"], "root_identity": binding["root_identity"], "spec_sha256": binding["spec_sha256"],
                      "command_sha256": binding["command_sha256"], "preflight_sha256": binding["preflight_sha256"],
                      "manifest_sha256": binding["manifest_sha256"], "binding": binding, "binding_sha256": digest,
                      "pid": os.getpid(), "pgid": os.getpgrp(), "owner_uid": os.getuid(),
                      "started_epoch": 1000+i, "deadline_epoch": 1600+i if role != "formal_run" else 1240+i,
                      "ended_epoch": 1001+i}
            result_hash = f"{i+1:064x}"
            if role == "diagnostic":
                record.update({"determination": "resolved", "report_sha256": "a"*64, "result_artifact_sha256": "a"*64})
                next_binding = _binding("e"*64)
                record.update({"expected_next_role": "final_probe", "expected_next_binding": next_binding,
                               "expected_next_binding_sha256": v20.binding_digest(next_binding)})
            if role in {"final_probe", "formal_run"}:
                run_id = run_ids[i-2] if role == "formal_run" else None
                if run_id: record["run_id"] = run_id
                record.update({"result_artifact_sha256": result_hash, "gate_schema": 1, "gate_evidence": PASS_EVIDENCE,
                               "gate_evidence_sha256": v20.gate_evidence_digest(attempt_id=attempt_id,
                                  binding_sha256=digest, result_artifact_sha256=result_hash, evidence=PASS_EVIDENCE, run_id=run_id)})
            if role == "formal_run": record["run_set_sha256"] = v20.sha256(v20.canonical_bytes(run_ids))
            if role == "final_probe":
                record.update({"expected_next_role": "formal_run", "expected_next_binding": formal_binding,
                               "expected_next_binding_sha256": v20.binding_digest(formal_binding),
                               "expected_next_run_set_sha256": v20.sha256(v20.canonical_bytes(run_ids))})
            filler.append(record)
        remote.records = filler
        ledger._write_local(filler, remote.head_hash)
        try:
            ledger.reserve(role="formal_run", run_id="C1-A-1", binding=_binding("2"*64))
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
                ledger.reserve(role="diagnostic", binding=_binding("f"*64))
                outcomes.append("ok")
            except v20.LedgerError:
                outcomes.append("refused")
        threads = [threading.Thread(target=contender) for _ in range(2)]
        [t.start() for t in threads]; [t.join() for t in threads]
        assert sorted(outcomes) == ["ok", "refused"]
    cases += 1
    return cases


def phase_binding_tests():
    with tempfile.TemporaryDirectory() as td:
        remote = FakeRemote(); ledger = v20.GlobalLedger(Path(td) / "state", remote); _seed_local(ledger, remote)
        db = _binding("f"*64); diag = ledger.reserve(role="diagnostic", binding=db)
        altered = dict(db, preflight_sha256="e"*64)
        before = remote.pushes
        try:
            ledger.complete(diag["id"], "timeout", binding=altered)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("completion accepted a different preflight binding")
        assert remote.pushes == before and ledger._read_local()["records"][-1]["state"] == "reserved"
        _complete_from_saved(ledger, diag, "completed_diagnostic", db, next_binding=_binding("e"*64))
        try:
            ledger.reserve(role="final_probe", binding=db)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("final role reused diagnostic binding")
        fb = _binding("e"*64); final = ledger.reserve(role="final_probe", binding=fb)
        result_hash = "1"*64
        _complete_from_saved(ledger, final, "final_pass", fb, next_binding=_binding("2"*64))
        assert ledger.formal_gate(_binding("2"*64))
        formal = _binding("2"*64); run = ledger.reserve(role="formal_run", run_id="C1-A-1", binding=formal)
        expected_digest = v20.gate_evidence_digest(attempt_id=run["id"], binding_sha256=v20.binding_digest(formal),
                    result_artifact_sha256="2"*64, evidence=PASS_EVIDENCE, run_id="C1-A-1")
        assert expected_digest != v20.gate_evidence_digest(attempt_id=final["id"], binding_sha256=v20.binding_digest(formal),
                    result_artifact_sha256="2"*64, evidence=PASS_EVIDENCE, run_id="C1-A-1")
        try:
            ledger.complete(run["id"], "formal_run_pass", binding=formal, run_id="C1-A-2",
                            gate_evidence=PASS_EVIDENCE, result_artifact_sha256="2"*64)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("formal run_id changed after reservation")
        _complete_from_saved(ledger, run, "formal_run_pass", formal, run_id="C1-A-1")
        chain = ledger._read_local()["records"]
        tampered = [dict(x) for x in chain]; tampered[-1] = dict(tampered[-1]); tampered[-1]["gate_evidence_sha256"] = "f"*64
        try:
            v20.validate_record_chain(tampered)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("attempt-bound PASS evidence hash tamper accepted")
    return 7


def artifact_attribution_tests():
    """Persisted result/sidecar provenance cannot cross attempt, role or phase."""
    def persist(parent, record, binding):
        if record["role"] == "diagnostic":
            report = _report(); report.update(attempt_id=record["id"], fingerprint=binding["fingerprint"])
            payload = v20.canonical_bytes(report)
        else:
            payload = v20.canonical_bytes({"schema": 1, "attempt_id": record["id"], "role": record["role"],
                "run_id": record.get("run_id"), "fingerprint": binding["fingerprint"], "gates": PASS_EVIDENCE})
        return v20.save_verified_result(parent / f"result-{record['id']}", attempt_id=record["id"],
            role=record["role"], run_id=record.get("run_id"), binding=binding, result_bytes=payload)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td); remote = FakeRemote(); ledger = v20.GlobalLedger(root / "ledger", remote); _seed_local(ledger, remote)
        db = _binding("binding-diagnostic"); diag = ledger.reserve(role="diagnostic", binding=db)
        diag_paths = persist(root, diag, db)
        copied_attempt = dict(diag, id="b" * 32)
        try:
            v20.verify_saved_result(diag_paths[0], diag_paths[1], record=copied_attempt, binding=db)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("sidecar/result reused for a different attempt")
        _complete_from_saved(ledger, diag, "completed_diagnostic", db, next_binding=_binding("binding-final"))
        final_binding = _binding("binding-final")
        before = remote.pushes
        fingerprint_only = dict(final_binding, fingerprint="0" * 64)
        try:
            ledger.reserve(role="final_probe", binding=fingerprint_only)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("fingerprint-only changed phase binding accepted")
        assert remote.pushes == before
        final = ledger.reserve(role="final_probe", binding=final_binding)
        before = remote.pushes
        try:
            ledger.complete(final["id"], "final_pass", binding=final_binding,
                result_artifact_path=diag_paths[0], evidence_sidecar_path=diag_paths[1],
                next_binding=_binding("binding-formal"))
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("diagnostic artifact reused for final role")
        assert remote.pushes == before
        final_paths = persist(root, final, final_binding)
        ledger.complete(final["id"], "final_pass", binding=final_binding,
            result_artifact_path=final_paths[0], evidence_sidecar_path=final_paths[1],
            next_binding=_binding("binding-formal"))
        formal_binding = _binding("binding-formal")
        formal = ledger.reserve(role="formal_run", run_id="C1-A-1", binding=formal_binding)
        before = remote.pushes
        try:
            ledger.complete(formal["id"], "formal_run_pass", binding=formal_binding, run_id="C1-A-1",
                result_artifact_path=final_paths[0], evidence_sidecar_path=final_paths[1])
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("final evidence/result reused for formal role")
        assert remote.pushes == before
    return 3


def gate_tests():
    hist = [dict(x, type="historical_attempt") for x in v20.HISTORICAL]
    diag_binding, final_binding, formal_binding = _binding("f"*64), _binding("e"*64), _binding("2"*64)
    run_ids = [f"C{c}-{side}-{repeat}" for c in range(1, 7) for side in ("A", "B") for repeat in (1, 2)]
    run_set = v20.sha256(v20.canonical_bytes(run_ids))
    def base_record(i, role, state, binding, run_id=None):
        record = {"sequence": i + 3, "id": f"{i+1:032x}", "role": role, "state": state,
                  "fingerprint": binding["fingerprint"], "root_identity": binding["root_identity"],
                  "spec_sha256": binding["spec_sha256"], "command_sha256": binding["command_sha256"],
                  "preflight_sha256": binding["preflight_sha256"], "manifest_sha256": binding["manifest_sha256"],
                  "binding": binding, "binding_sha256": v20.binding_digest(binding),
                  "pid": os.getpid(), "pgid": os.getpgrp(), "owner_uid": os.getuid(),
                  "started_epoch": 1000+i, "deadline_epoch": 1600+i if role != "formal_run" else 1240+i,
                  "ended_epoch": 1001+i}
        if run_id is not None: record["run_id"] = run_id
        return record
    diag = base_record(0, "diagnostic", "completed_diagnostic", diag_binding)
    diag.update({"determination": "resolved", "report_sha256": "a"*64, "result_artifact_sha256": "a"*64,
                 "expected_next_role": "final_probe", "expected_next_binding": final_binding,
                 "expected_next_binding_sha256": v20.binding_digest(final_binding)})
    final = base_record(1, "final_probe", "final_pass", final_binding)
    final_result = "b"*64
    final.update({"result_artifact_sha256": final_result, "gate_schema": 1, "gate_evidence": PASS_EVIDENCE,
                  "gate_evidence_sha256": v20.gate_evidence_digest(attempt_id=final["id"],
                      binding_sha256=final["binding_sha256"], result_artifact_sha256=final_result, evidence=PASS_EVIDENCE),
                  "expected_next_role": "formal_run", "expected_next_binding": formal_binding,
                  "expected_next_binding_sha256": v20.binding_digest(formal_binding),
                  "expected_next_run_set_sha256": run_set})
    prefix = hist + [diag, final]
    assert v20.formal_start_eligible(prefix)
    assert not v20.formal_start_eligible(hist + [{**diag, "determination": "inconclusive"}, final])
    assert not v20.formal_start_eligible(hist + [diag, {**final, "state": "final_fail"}])
    assert not v20.formal_start_eligible(hist + [diag, final, {"role": "unknown"}])
    runs = []
    for i, run_id in enumerate(run_ids):
        record = base_record(i+2, "formal_run", "formal_run_pass", formal_binding, run_id)
        result_hash = f"{i+3:064x}"
        record.update({"result_artifact_sha256": result_hash, "gate_schema": 1, "gate_evidence": PASS_EVIDENCE,
                       "gate_evidence_sha256": v20.gate_evidence_digest(attempt_id=record["id"],
                           binding_sha256=record["binding_sha256"], result_artifact_sha256=result_hash,
                           evidence=PASS_EVIDENCE, run_id=run_id), "run_set_sha256": run_set})
        runs.append(record)
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
        ledger = v20.GlobalLedger(root / "state", adapter)
        ledger._write_local(history, first)
        reservation = ledger.reserve(role="diagnostic", binding=_binding())
        current = adapter.ls_remote(); current_records = adapter.chain(current)
        assert current_records[-1]["id"] == reservation["id"]
        attacks = []
        attacks.append(history)  # drop the consumed reservation / rollback to old snapshot
        altered = [dict(x) for x in current_records]; altered[-1]["binding"] = _binding("e"*64); attacks.append(altered)
        reordered = [*current_records[:2], *reversed(current_records[2:])]; attacks.append(reordered)
        for candidate in attacks:
            try:
                adapter.push_ff(current, v20.canonical_bytes({"schema": 1, "version": 20, "records": candidate}))
            except v20.LedgerError:
                pass
            else:
                raise AssertionError("fixture remote accepted deletion/rollback/binding tamper")
        ledger.mark_running(reservation["id"], binding=_binding())
        running_head = adapter.ls_remote(); running_records = adapter.chain(running_head)
        reverse = [dict(x) for x in running_records]; reverse[-1]["state"] = "reserved"
        try:
            adapter.push_ff(running_head, v20.canonical_bytes({"schema": 1, "version": 20, "records": reverse}))
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("fixture remote accepted state reversal")
        _complete_from_saved(ledger, reservation, "completed_diagnostic", _binding(), next_binding=_binding("e"*64))
        completed_head = adapter.ls_remote()
        assert completed_head != running_head and adapter.chain(completed_head)[-1]["state"] == "completed_diagnostic"
    return 8


def diagnostic_lifecycle_tests():
    # Arbitrary Python callbacks are rejected before reservation or invocation.
    class Callback:
        calls = 0
        def invoke(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("callback executed")
    cases = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); remote = FakeRemote(); ledger = v20.GlobalLedger(root / "ledger", remote); _seed_local(ledger, remote)
        cb = Callback()
        try:
            v20.run_diagnostic_once(ledger, binding=_binding(), adapter=cb,
                artifact_directory=root / "out", next_binding_factory=lambda _: _binding("e"*64))
        except v20.LedgerError as exc:
            assert str(exc) == "fixed_cli_binding_invalid"
        else:
            raise AssertionError("arbitrary callback adapter accepted")
        assert cb.calls == 0 and len(ledger._read_local()["records"]) == 2
    cases += 1

    # If the host disables sandbox-exec (as this managed runtime does), fail
    # before launching any fake subprocess. Never fall back to uncontained exec.
    with tempfile.TemporaryDirectory() as td:
        fixture = Path(td); sandbox = fixture / "sandbox"; sandbox.mkdir(mode=0o700)
        sibling = fixture / "sibling.raw"; escaped = sandbox.parent / "escaped.raw"
        containment_available = True
        for target in (sibling, escaped, Path(td) / "absolute.raw"):
            code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('sentinel')"
            try:
                outcome = v20.run_process_group((__import__("sys").executable, "-I", "-B", "-c", code, str(target)),
                    deadline_epoch=time.time()+10, residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox)
            except v20.LedgerError as exc:
                assert str(exc) == "host_containment_unavailable"
                containment_available = False
            else:
                assert outcome["child_reaped"] and outcome["residual_verified"] and outcome["returncode"] != 0
            assert not target.exists()
            cases += 1
        # Even an allowed in-sandbox write does not justify bypassing an unavailable OS boundary.
        allowed = sandbox / "inside.txt"
        try:
            outcome = v20.run_process_group((__import__("sys").executable, "-I", "-B", "-c",
                "import pathlib; pathlib.Path('inside.txt').write_text('ok')"), deadline_epoch=time.time()+10,
                residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox)
        except v20.LedgerError as exc:
            assert str(exc) == "host_containment_unavailable"
            containment_available = False
        else:
            assert outcome["returncode"] == 0 and allowed.read_text() == "ok"
        assert allowed.exists() == containment_available
        cases += 1
        try:
            outcome = v20.run_process_group((__import__("sys").executable, "-I", "-B", "-c", "import time; time.sleep(5)"),
                deadline_epoch=time.time()+0.1, residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox)
        except v20.LedgerError as exc:
            assert str(exc) == "host_containment_unavailable"
        else:
            assert outcome["timed_out"] and outcome["child_reaped"] and outcome["residual_verified"]
        cases += 1
    argv = ("/opt/homebrew/Caskroom/codex/0.162.1/bin/codex", *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)
    production_binding = _binding()
    production_binding["command_sha256"] = v20.runner_command_sha256(argv[0])
    production = v20.FixedOpenAIDirectCodexAdapter(argv, command_sha256=production_binding["command_sha256"],
        binding=production_binding, residual_scanner=v20._production_residual_scanner)
    try:
        production.invoke(time.time()+30, attempt_id=TRUSTED_ID, binding=production_binding,
                          sandbox_directory=Path("/private/tmp"))
    except v20.LedgerError as exc:
        assert str(exc) == "actual_invocation_disabled"
    else:
        raise AssertionError("production Codex adapter invoked while disabled")
    for forbidden in (("/usr/bin/env", "vercel"),
        ("/opt/homebrew/Caskroom/codex/0.162.1/bin/codex", "exec", "--json", "--retry")):
        try:
            v20.FixedOpenAIDirectCodexAdapter(forbidden,
                command_sha256=v20.sha256(v20.canonical_bytes(list(forbidden))),
                binding=dict(production_binding, command_sha256=v20.sha256(v20.canonical_bytes(list(forbidden)))),
                residual_scanner=v20._production_residual_scanner)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("alternate route/retry command accepted")
        cases += 1

    # Adapter sealing attacks must fail before any remote reservation or callback.
    def sealed_rejection(label, factory):
        with tempfile.TemporaryDirectory(prefix="p5-v20-adapter-seal-") as td:
            root = Path(td); remote = FakeRemote(); ledger = v20.GlobalLedger(root / "ledger", remote); _seed_local(ledger, remote)
            binding = dict(production_binding)
            counter = {"calls": 0}
            candidate = factory(binding, counter)
            before_head = remote.ls_remote()
            try:
                v20.run_diagnostic_once(ledger, binding=binding, adapter=candidate,
                    artifact_directory=root / "out", next_binding_factory=lambda _: _binding("e"*64), actual_enabled=True)
            except v20.LedgerError:
                pass
            else:
                raise AssertionError(f"adapter seal attack accepted: {label}")
            assert counter["calls"] == 0
            assert len(ledger._read_local()["records"]) == 2
            assert remote.ls_remote() == before_head
            assert not list(root.rglob("*sentinel*"))
    def adapter_for(binding, counter):
        command = ("/opt/homebrew/Caskroom/codex/0.162.1/bin/codex", *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)
        cmdhash = v20.runner_command_sha256(command[0])
        binding["command_sha256"] = cmdhash
        obj = v20.FixedOpenAIDirectCodexAdapter(command, command_sha256=cmdhash, binding=binding,
                                                residual_scanner=v20._production_residual_scanner)
        return obj
    class OverrideAdapter(v20.FixedOpenAIDirectCodexAdapter):
        def invoke(self, *args, **kwargs):
            raise AssertionError("subclass callback executed")
    def subclass_factory(binding, counter):
        base = adapter_for(binding, counter)
        obj = object.__new__(OverrideAdapter)
        for field in ("_argv", "_binding_bytes", "_command_sha256", "_profile_sha256", "_root_bytes"):
            object.__setattr__(obj, field, getattr(base, field))
        return obj
    sealed_rejection("subclass override", subclass_factory); cases += 1
    def instance_invoke_factory(binding, counter):
        obj = adapter_for(binding, counter)
        try:
            object.__setattr__(obj, "invoke", lambda *a, **k: counter.__setitem__("calls", counter["calls"] + 1))
        except (AttributeError, TypeError, v20.LedgerError):
            pass
        else:
            raise AssertionError("instance invoke monkeypatch accepted")
        object.__setattr__(obj, "_command_sha256", "0"*64)
        return obj
    sealed_rejection("instance invoke replacement", instance_invoke_factory); cases += 1
    def class_invoke_factory(binding, counter):
        obj = adapter_for(binding, counter)
        type.__setattr__(v20.FixedOpenAIDirectCodexAdapter, "invoke",
                         lambda *a, **k: counter.__setitem__("calls", counter["calls"] + 1))
        return obj
    try:
        sealed_rejection("class invoke replacement", class_invoke_factory); cases += 1
    finally:
        type.__setattr__(v20.FixedOpenAIDirectCodexAdapter, "invoke", v20._FIXED_ADAPTER_INVOKE)
    def invoke_descriptor_factory(binding, counter):
        obj = adapter_for(binding, counter)
        def property_callback(_instance):
            counter["calls"] += 1
            return v20._FIXED_ADAPTER_INVOKE
        type.__setattr__(v20.FixedOpenAIDirectCodexAdapter, "invoke", property(property_callback))
        return obj
    try:
        sealed_rejection("invoke property descriptor replacement", invoke_descriptor_factory); cases += 1
    finally:
        type.__setattr__(v20.FixedOpenAIDirectCodexAdapter, "invoke", v20._FIXED_ADAPTER_INVOKE)
    def actual_false_factory(binding, counter):
        obj = adapter_for(binding, counter)
        # Bypass Python's metaclass guard to model hostile in-process tampering; outer check must catch it.
        type.__setattr__(v20.FixedOpenAIDirectCodexAdapter, "actual_enabled", False)
        return obj
    try:
        sealed_rejection("class actual_enabled spoof", actual_false_factory); cases += 1
    finally:
        type.__setattr__(v20.FixedOpenAIDirectCodexAdapter, "actual_enabled", True)
    def instance_actual_factory(binding, counter):
        obj = adapter_for(binding, counter)
        try: object.__setattr__(obj, "actual_enabled", False)
        except (AttributeError, TypeError, v20.LedgerError): pass
        else: raise AssertionError("instance actual_enabled spoof accepted")
        object.__setattr__(obj, "_command_sha256", "0"*64)
        return obj
    sealed_rejection("instance actual_enabled spoof", instance_actual_factory); cases += 1
    def argv_tamper_factory(binding, counter):
        obj = adapter_for(binding, counter); object.__setattr__(obj, "_argv", ("/usr/bin/env", "vercel")); return obj
    sealed_rejection("argv replacement", argv_tamper_factory); cases += 1
    def profile_tamper_factory(binding, counter):
        obj = adapter_for(binding, counter); object.__setattr__(obj, "_profile_sha256", "0"*64); return obj
    sealed_rejection("profile replacement", profile_tamper_factory); cases += 1
    def root_tamper_factory(binding, counter):
        obj = adapter_for(binding, counter); object.__setattr__(obj, "_root_bytes", v20.canonical_bytes({"realpath": "/private/tmp/changed", "device": 1, "inode": 2})); return obj
    sealed_rejection("root identity replacement", root_tamper_factory); cases += 1

    # End-to-end synthetic reservations consume their slot on escape denial and timeout.
    for mode in ("escape", "timeout"):
        with tempfile.TemporaryDirectory(prefix="p5-v20-synthetic-attempt-") as td:
            root = Path(td); remote = FakeRemote(); ledger = v20.GlobalLedger(root / "ledger", remote); _seed_local(ledger, remote)
            binding = _binding("synthetic-" + mode)
            reservation = ledger.reserve(role="diagnostic", binding=binding)
            ledger.mark_running(reservation["id"], binding=binding)
            sandbox = root / "sandbox"; sandbox.mkdir(mode=0o700)
            escaped = root / "escaped.raw"
            if mode == "escape":
                argv = (__import__("sys").executable, "-I", "-B", "-c",
                        "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('sentinel')", str(escaped))
                expected_state = "unknown"
            else:
                timeout_code = ("import pathlib,sys,time\ntry: pathlib.Path(sys.argv[1]).write_text('sentinel')\n"
                                "except OSError: pass\ntime.sleep(5)")
                argv = (__import__("sys").executable, "-I", "-B", "-c", timeout_code, str(escaped))
                expected_state = "timeout"
            try:
                outcome = v20.run_process_group(argv, deadline_epoch=time.time()+(0.1 if mode == "timeout" else 10),
                    residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox)
                if mode == "escape":
                    assert outcome["returncode"] != 0 and not escaped.exists()
                else:
                    assert outcome["timed_out"] and outcome["child_reaped"] and outcome["residual_verified"]
            except v20.LedgerError as exc:
                # The Codex outer sandbox cannot invoke sandbox-exec; the attempt still stops consumed.
                assert str(exc) == "host_containment_unavailable"
                expected_state = "unknown"
            ledger.complete(reservation["id"], expected_state, binding=binding)
            assert ledger._read_local()["records"][-1]["state"] == expected_state and not escaped.exists()
            cases += 1

    # Reservation failure is before any child process. A marker file would prove launch.
    with tempfile.TemporaryDirectory(prefix="p5-v20-no-reserve-") as td:
        root = Path(td); remote = FakeRemote(); ledger = v20.GlobalLedger(root / "ledger", remote); _seed_local(ledger, remote)
        remote.mode = "non_ff"; marker = root / "launched"
        try:
            reservation = ledger.reserve(role="diagnostic", binding=_binding("reservation-failure"))
            v20.run_process_group(("/usr/bin/touch", str(marker)), deadline_epoch=time.time()+5,
                residual_scanner=lambda *_: True, cwd=root, sandbox_directory=root)
        except v20.LedgerError:
            pass
        else:
            raise AssertionError("non-FF reservation continued to a fake child")
        assert not marker.exists() and remote.pushes == 0
        cases += 1
    return cases


def production_runner_tests():
    cases = 0
    base = Path(v20.__file__).resolve().parent
    config = v20_driver.strict_json(base / "config.json")
    # Missing plan-pinned remote seed hash stops before remote/local setup or CLI invocation.
    with tempfile.TemporaryDirectory(prefix="p5-v20-unpinned-gate-") as td:
        denied = dict(config, seed_commit_pin=None, global_ledger_directory=str(Path(td) / "ledger"),
                      diagnostic_root=str(Path(td) / "diagnostic"))
        try:
            v20_driver.run_diagnostic_once(base, v20_driver.strict_json(base / "manifest.json"), denied)
        except v20.LedgerError as exc:
            assert str(exc) == "seed_commit_pin_missing"
        else:
            raise AssertionError("unpinned diagnostic runner accepted")
        assert not Path(denied["global_ledger_directory"]).exists()
        assert not Path(denied["diagnostic_root"]).exists()
    cases += 1

    class EmptyRemote:
        seed_commit_pin = None
        def __init__(self): self.head_hash=None; self.records=[]; self.pushes=0
        def head(self): return self.head_hash
        def ls_remote(self): return self.head_hash
        def push_ff(self, parent, payload):
            assert parent is None and self.head_hash is None
            self.records=v20.strict_json(payload)["records"]
            self.head_hash=hashlib.sha1(payload).hexdigest(); self.pushes+=1
            return self.head_hash
    cache=Path(__import__("pwd").getpwuid(os.getuid()).pw_dir)/"Library/Caches/agent-crew-p5-benchmark"
    with tempfile.TemporaryDirectory(prefix="p5-v20-seed-input-") as td:
        temp=Path(td); copies=[]
        for i,(rel,*_) in enumerate(v20_driver.HISTORICAL_RESULT_FILES):
            dst=temp/f"historic-{i}.json"; dst.write_bytes((cache/rel).read_bytes()); dst.chmod(0o600); copies.append(dst)
        remote=EmptyRemote()
        result=v20_driver.bootstrap_seed(base,dict(config,seed_commit_pin=None),remote_factory=lambda _:remote,
            result_paths=copies,ledger_root=temp/"ledger")
        assert result["seed_payload_sha256"]==v20.SEED_SHA256 and result["seed_commit_sha"]==remote.head_hash
        assert remote.pushes==1 and len(remote.records)==2
        bad=temp/"tampered.json"; bad.write_bytes(copies[0].read_bytes()+b" "); bad.chmod(0o600)
        calls={"remote":0}
        try:
            v20_driver.bootstrap_seed(base,dict(config,seed_commit_pin=None),
                remote_factory=lambda _:calls.__setitem__("remote",1),result_paths=(bad,copies[1]),ledger_root=temp/"bad-ledger")
        except Exception:
            pass
        else: raise AssertionError("tampered historical result accepted")
        assert calls["remote"]==0
    cases += 2

    report=_report(); command="/bin/zsh -lc /fixed/canary"
    events=[{"type":"thread.started","thread_id":"synthetic"},{"type":"turn.started"},
        {"type":"item.started","item":{"id":"tool-1","type":"command_execution","command":command,"status":"in_progress"}},
        {"type":"item.completed","item":{"id":"tool-1","type":"command_execution","command":command,"status":"completed","exit_code":0,"aggregated_output":v20.canonical_bytes(report).decode()}},
        {"type":"turn.completed"}]
    encoded=b"\n".join(v20.canonical_bytes(item).rstrip(b"\n") for item in events)
    assert v20._audit_diagnostic_events(encoded,canary_command=command,attempt_id=TRUSTED_ID,fingerprint=TRUSTED_FP)==report
    extra=events[:3]+[{"type":"item.started","item":{"id":"tool-2","type":"command_execution","command":"curl https://invalid","status":"in_progress"}}]+events[3:]
    try:
        v20._audit_diagnostic_events(b"\n".join(v20.canonical_bytes(item).rstrip(b"\n") for item in extra),
            canary_command=command,attempt_id=TRUSTED_ID,fingerprint=TRUSTED_FP)
    except v20.LedgerError: pass
    else: raise AssertionError("additional tool event accepted")
    cases += 2

    # The sandbox profile itself is a fixed runner argv value and is included in
    # the command binding, alongside Codex's independent read-only sandbox flag.
    with tempfile.TemporaryDirectory(prefix="p5-v20-fixed-profile-argv-") as td:
        sandbox = Path(td) / "sandbox"; sandbox.mkdir(mode=0o700)
        codex = "/opt/homebrew/Caskroom/codex/0.162.1/bin/codex"
        profile = v20.SANDBOX_PROFILE_TEMPLATE.format(directory=str(sandbox.resolve(strict=True)))
        expected = [v20.SANDBOX_EXEC, "-p", profile, "/usr/bin/true"]
        with patch("v20_diagnostic.subprocess.run", return_value=subprocess.CompletedProcess(expected, 0, b"", b"")) as probe:
            actual = v20.sandboxed_argv(("/usr/bin/true",), sandbox)
        assert actual == expected
        assert probe.call_args.args[0] == expected
        bound_sandbox = str(sandbox.resolve(strict=True))
        write_rule = '(allow file-write* (subpath "' + bound_sandbox + '"))'
        assert "(deny default)" in profile and write_rule in profile
        assert "(allow network-outbound)" in profile and "(allow file-write*)" not in profile.replace(write_rule, "")
        spec = v20.runner_argv_spec(codex)
        assert spec == (v20.SANDBOX_EXEC, "-p", v20.SANDBOX_PROFILE_TEMPLATE,
                        codex, *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)
        assert spec[1:3] == ("-p", v20.SANDBOX_PROFILE_TEMPLATE)
        assert "--sandbox" in spec and spec[spec.index("--sandbox") + 1] == "read-only"
        assert v20.runner_command_sha256(codex) == v20.sha256(v20.canonical_bytes(list(spec)))
        assert v20.runner_command_sha256(codex) != v20.sha256(v20.canonical_bytes(list(spec[3:])))
    cases += 1
    return cases


def run_all():
    counts = {"schema": schema_tests(), "privacy": privacy_tests(), "path_unknown": path_and_unknown_tests(),
              "ledger": ledger_tests(), "phase_binding": phase_binding_tests(), "artifact_attribution": artifact_attribution_tests(),
              "formal_gate": gate_tests(), "remote_fixture": git_remote_fixture_tests(),
              "seed_canonical": seed_canonical_tests(), "diagnostic_lifecycle": diagnostic_lifecycle_tests(),
              "production_runner": production_runner_tests()}
    return counts


if __name__ == "__main__":
    counts = run_all()
    print("v20 selftest: PASS " + json.dumps(counts, sort_keys=True))
