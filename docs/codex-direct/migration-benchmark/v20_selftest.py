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
    argv = ("/opt/homebrew/Caskroom/codex/0.163.0/bin/codex", *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)
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
        ("/opt/homebrew/Caskroom/codex/0.163.0/bin/codex", "exec", "--json", "--retry")):
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
        command = ("/opt/homebrew/Caskroom/codex/0.163.0/bin/codex", *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)
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
    original_ledgers = [cache / rel for rel, *_ in v20_driver.HISTORICAL_LEDGER_FILES]
    ledger_hashes_before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in original_ledgers]
    assert ledger_hashes_before == [x[2] for x in v20_driver.HISTORICAL_LEDGER_FILES]
    with tempfile.TemporaryDirectory(prefix="p5-v20-seed-input-") as td:
        temp=Path(td); copies=[]; ledger_copies=[]
        for i,(rel,*_) in enumerate(v20_driver.HISTORICAL_RESULT_FILES):
            dst=temp/f"historic-{i}.json"; dst.write_bytes((cache/rel).read_bytes()); dst.chmod(0o600); copies.append(dst)
        for i,(rel,*_) in enumerate(v20_driver.HISTORICAL_LEDGER_FILES):
            dst=temp/f"historic-ledger-{i}.json"; dst.write_bytes((cache/rel).read_bytes()); dst.chmod(0o600); ledger_copies.append(dst)
        remote=EmptyRemote()
        result=v20_driver.bootstrap_seed(base,dict(config,seed_commit_pin=None),remote_factory=lambda _:remote,
            result_paths=copies,ledger_paths=ledger_copies,ledger_root=temp/"ledger")
        assert result["seed_payload_sha256"]==v20.SEED_SHA256 and result["seed_commit_sha"]==remote.head_hash
        assert remote.pushes==1 and len(remote.records)==2
        bad=temp/"tampered.json"; bad.write_bytes(copies[0].read_bytes()+b" "); bad.chmod(0o600)
        calls={"remote":0}
        try:
            v20_driver.bootstrap_seed(base,dict(config,seed_commit_pin=None),
                remote_factory=lambda _:calls.__setitem__("remote",1),result_paths=(bad,copies[1]),
                ledger_paths=ledger_copies,ledger_root=temp/"bad-ledger")
        except Exception:
            pass
        else: raise AssertionError("tampered historical result accepted")
        assert calls["remote"]==0
        cases += 2

        # F-2: the original v18/v19 ledgers must match the fixed references before any remote object exists.
        # Every rejection below must happen with remote factory/callback == 0 and no local ledger created.
        def seed_rejected(label, ledger_paths, *, pins=None):
            calls = {"remote": 0}
            root = temp / f"reject-{label}"
            def factory(_config):
                calls["remote"] += 1
                raise AssertionError("remote factory reached")
            patcher = (patch.object(v20_driver, "HISTORICAL_LEDGER_FILES", pins) if pins is not None
                       else patch.object(v20_driver, "HISTORICAL_LEDGER_FILES", v20_driver.HISTORICAL_LEDGER_FILES))
            with patcher:
                try:
                    v20_driver.bootstrap_seed(base, dict(config, seed_commit_pin=None), remote_factory=factory,
                        result_paths=copies, ledger_paths=ledger_paths, ledger_root=root)
                except AssertionError:
                    raise
                except Exception:
                    pass
                else:
                    raise AssertionError(f"historical ledger fault accepted: {label}")
            assert calls["remote"] == 0 and not root.exists(), label
        # missing, hash mismatch (whitespace), swapped order, same ledger twice
        seed_rejected("missing", (temp / "no-such-ledger.json", ledger_copies[1]))
        trailing = temp / "ledger-trailing.json"; trailing.write_bytes(ledger_copies[0].read_bytes() + b"\n"); trailing.chmod(0o600)
        seed_rejected("hash-mismatch", (trailing, ledger_copies[1]))
        seed_rejected("swapped", (ledger_copies[1], ledger_copies[0]))
        seed_rejected("same-ledger-twice", (ledger_copies[0], ledger_copies[0]))
        cases += 4
        # Value changes keep the (re-pinned) hash valid, so only the semantic cross-check can reject them.
        original = [json.loads(p.read_bytes()) for p in ledger_copies]
        def mutate(index, change):
            value = json.loads(json.dumps(original[index]))
            change(value)
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        mutations = {
            "elapsed-changed": (0, lambda v: v["attempts"][0].__setitem__("elapsed_seconds", 11.0)),
            "elapsed-int": (0, lambda v: v["attempts"][0].__setitem__("elapsed_seconds", 11)),
            "state-changed": (1, lambda v: v["attempts"][0].__setitem__("state", "pass")),
            "fingerprint-changed": (0, lambda v: v["attempts"][0].__setitem__("fingerprint", "0" * 64)),
            "id-changed": (1, lambda v: v["attempts"][0].__setitem__("id", "0" * 32)),
            "result-ref-detail": (1, lambda v: v["attempts"][0].__setitem__("detail", "other_failure")),
            "not-reaped": (0, lambda v: v["attempts"][0].__setitem__("child_reaped", False)),
            "residual-unverified": (1, lambda v: v["attempts"][0].__setitem__("residual_verified", False)),
            "duplicate-attempt": (0, lambda v: v["attempts"].append(json.loads(json.dumps(v["attempts"][0])))),
            "no-attempt": (1, lambda v: v.__setitem__("attempts", [])),
            "version-changed": (0, lambda v: v.__setitem__("version", 19)),
        }
        for label, (index, change) in mutations.items():
            data = mutate(index, change)
            path = temp / f"mutated-{label}.json"; path.write_bytes(data); path.chmod(0o600)
            paths = list(ledger_copies); paths[index] = path
            pins = list(v20_driver.HISTORICAL_LEDGER_FILES)
            pins[index] = (pins[index][0], pins[index][1], hashlib.sha256(data).hexdigest())
            seed_rejected(label, tuple(paths), pins=tuple(pins))
            # The semantic check alone must also reject it (hash independent).
            try:
                v20_driver.validate_historical_ledger_bytes(data, index)
            except ValueError:
                pass
            else:
                raise AssertionError(f"semantic ledger check accepted: {label}")
            cases += 1
        # A hard-linked ledger (nlink != 1) is not an independent private original.
        os.link(ledger_copies[0], temp / "ledger-link.json")
        seed_rejected("hardlink", tuple(ledger_copies))
        cases += 1
    ledger_hashes_after = [hashlib.sha256(p.read_bytes()).hexdigest() for p in original_ledgers]
    assert ledger_hashes_after == ledger_hashes_before  # original ledgers are read-only evidence

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
        codex = "/opt/homebrew/Caskroom/codex/0.163.0/bin/codex"
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


def _spawn_context(root, label, *, mutate_config=None, clock=None):
    """Seeded fixture ledger + sealed production adapter. No real remote, CLI or model client."""
    base = Path(v20.__file__).resolve().parent
    artifact_config = v20.strict_json((base / "config.json").read_bytes())
    config = dict(artifact_config, seed_commit_pin="a" * 40)
    if mutate_config:
        config = mutate_config(config)
    codex = artifact_config["codex_binding"]["realpath"]
    binding = _binding("spawn-" + label)
    argv = (codex, *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)
    assert binding["command_sha256"] == v20.runner_command_sha256(codex)
    adapter = v20.FixedOpenAIDirectCodexAdapter(argv, command_sha256=binding["command_sha256"],
        binding=binding, residual_scanner=v20._production_residual_scanner)
    remote = FakeRemote()
    ledger = v20.GlobalLedger(Path(root) / f"ledger-{label}", remote, **({"clock": clock} if clock else {}))
    _seed_local(ledger, remote)
    return config, codex, argv, binding, adapter, remote, ledger


def _spawn_denied(config, ledger, adapter, binding, deadline, attempt_id, sandbox, expected_code):
    """Direct adapter.invoke with actual_enabled=True must stop before the CLI process boundary."""
    with patch.object(v20, "_fixed_config", lambda _binding: config), \
            patch.object(v20, "_fixed_ledger", lambda _config: ledger), \
            patch("v20_diagnostic.subprocess.Popen") as popen, patch("v20_diagnostic.subprocess.run") as run:
        try:
            adapter.invoke(deadline, attempt_id=attempt_id, binding=binding, sandbox_directory=sandbox,
                           actual_enabled=True)
        except v20.LedgerError as exc:
            assert str(exc) == expected_code, (str(exc), expected_code)
        else:
            raise AssertionError("spawn boundary accepted an unauthorized invocation")
        assert popen.call_count == 0 and run.call_count == 0


def spawn_boundary_tests():
    cases = 0
    with tempfile.TemporaryDirectory(prefix="p5-v20-spawn-boundary-") as td:
        root = Path(td); sandbox = root / "sandbox"; sandbox.mkdir(mode=0o700)
        fake_id = "0123456789abcdef0123456789abcdef"

        # F-1: UNPINNED immutable config, even for a structurally valid binding/ID and actual_enabled=True.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "unpinned",
            mutate_config=lambda c: dict(c, seed_commit_pin=None))
        _spawn_denied(config, ledger, adapter, binding, time.time() + 60, fake_id, sandbox, "seed_commit_pin_missing")
        assert remote.pushes == 0 and len(ledger._read_local()["records"]) == 2
        cases += 1
        # Config enable flag false.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "disabled",
            mutate_config=lambda c: dict(c, actual_invocations_enabled=False))
        _spawn_denied(config, ledger, adapter, binding, time.time() + 60, fake_id, sandbox, "actual_invocation_disabled")
        cases += 1
        # Pinned and enabled, but no reservation exists: an arbitrary well-formed ID is not authority.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "unreserved")
        _spawn_denied(config, ledger, adapter, binding, time.time() + 60, fake_id, sandbox, "spawn_reservation_invalid")
        assert remote.pushes == 0 and len(ledger._read_local()["records"]) == 2
        cases += 1
        # A real reservation exists, but the invoked ID is invented.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "invented")
        record = ledger.reserve(role="diagnostic", binding=binding)
        _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"], fake_id, sandbox, "spawn_reservation_invalid")
        cases += 1
        # N-1: a reservation already marked running ("spawned") is never spawn-authorized again.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "already-running")
        record = ledger.reserve(role="diagnostic", binding=binding); ledger.mark_running(record["id"], binding=binding)
        _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"], record["id"], sandbox, "spawn_reservation_invalid")
        cases += 1
        # Consumed IDs (terminal states) cannot be re-invoked.
        for terminal in ("unknown", "timeout", "diagnostic_inconclusive"):
            config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "consumed-" + terminal)
            record = ledger.reserve(role="diagnostic", binding=binding); ledger.mark_running(record["id"], binding=binding)
            ledger.complete(record["id"], terminal, binding=binding,
                            determination="inconclusive" if terminal == "diagnostic_inconclusive" else None)
            _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"], record["id"], sandbox, "spawn_reservation_invalid")
            cases += 1
        # Reservation bound to another binding / deadline mismatch / expired deadline.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "other-binding")
        other = _binding("spawn-other-binding-record")
        record = ledger.reserve(role="diagnostic", binding=other)
        _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"], record["id"], sandbox, "spawn_reservation_invalid")
        cases += 1
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "deadline")
        record = ledger.reserve(role="diagnostic", binding=binding)
        _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"] + 1, record["id"], sandbox, "spawn_reservation_invalid")
        cases += 1
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "expired",
            clock=lambda: time.time() - 3600)
        record = ledger.reserve(role="diagnostic", binding=binding)
        _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"], record["id"], sandbox, "spawn_reservation_invalid")
        cases += 1

        # Missing / wrong sandbox directory (with an otherwise valid running reservation): fixed error, no spawn.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "sandbox-missing")
        record = ledger.reserve(role="diagnostic", binding=binding)
        for bad_sandbox in (None, root / "does-not-exist", root / "plain-file"):
            if bad_sandbox == root / "plain-file":
                bad_sandbox.write_text("x")
            _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"], record["id"], bad_sandbox,
                          "host_containment_unavailable")
            cases += 1

        # Helper-level bypass: the fixed Codex argv cannot be started through run_process_group directly,
        # nor with extra arguments, nor via _invoke_diagnostic_cli with a different executable/profile argv.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "helper-bypass")
        record = ledger.reserve(role="diagnostic", binding=binding)
        with patch.object(v20, "_fixed_config", lambda _binding: config), \
                patch.object(v20, "_fixed_ledger", lambda _config: ledger), \
                patch("v20_diagnostic.subprocess.Popen") as popen, patch("v20_diagnostic.subprocess.run") as run:
            for label, call in {
                "run_process_group fixed argv": lambda: v20.run_process_group(argv, deadline_epoch=time.time() + 30,
                    residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox),
                "run_process_group extra arg": lambda: v20.run_process_group((*argv, "--extra"),
                    deadline_epoch=time.time() + 30, residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox),
                "run_process_group other codex": lambda: v20.run_process_group(("/tmp/codex", "exec"),
                    deadline_epoch=time.time() + 30, residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox),
                "invoke extra arg": lambda: v20._invoke_diagnostic_cli((*argv, "--extra"),
                    deadline_epoch=record["deadline_epoch"], attempt_id=record["id"], binding=binding, sandbox_directory=sandbox),
                "invoke other executable": lambda: v20._invoke_diagnostic_cli(("/usr/bin/env", *argv[1:]),
                    deadline_epoch=record["deadline_epoch"], attempt_id=record["id"], binding=binding, sandbox_directory=sandbox),
                "invoke nested sandbox profile": lambda: v20._invoke_diagnostic_cli(
                    (v20.SANDBOX_EXEC, "-p", "(version 1)(allow default)", *argv),
                    deadline_epoch=record["deadline_epoch"], attempt_id=record["id"], binding=binding, sandbox_directory=sandbox),
            }.items():
                try:
                    call()
                except v20.LedgerError as exc:
                    assert str(exc) == "fixed_cli_binding_invalid", (label, str(exc))
                else:
                    raise AssertionError(f"helper bypass accepted: {label}")
                cases += 1
            assert popen.call_count == 0 and run.call_count == 0

        # Positive control through the real lifecycle: reserve -> running -> authorized spawn. The only
        # process creation is a mocked Popen; its argv must be the complete fixed sandbox-exec command.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "positive")
        out_parent = root / "positive-out"; out_parent.mkdir(mode=0o700)
        class Spawned(Exception):
            pass
        with patch.object(v20, "_fixed_config", lambda _binding: config), \
                patch.object(v20, "_fixed_ledger", lambda _config: ledger), \
                patch("v20_diagnostic.subprocess.Popen", side_effect=OSError("mock spawn")) as popen, \
                patch("v20_diagnostic.subprocess.run") as run:
            def fake_probe(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, b"", b"")
            run.side_effect = fake_probe
            try:
                v20.run_diagnostic_once(ledger, binding=binding, adapter=adapter,
                    artifact_directory=out_parent / "result", next_binding_factory=lambda _: _binding("e" * 64),
                    actual_enabled=True)
            except v20.LedgerError:
                pass
            else:
                raise AssertionError("mocked spawn failure unexpectedly succeeded")
            assert popen.call_count == 1 and run.call_count == 1
            final_argv = popen.call_args.args[0]
            probe_argv = run.call_args.args[0]
            assert final_argv[0] == v20.SANDBOX_EXEC and final_argv[1] == "-p" and probe_argv[:2] == [v20.SANDBOX_EXEC, "-p"]
            profile = final_argv[2]
            assert probe_argv == [v20.SANDBOX_EXEC, "-p", profile, "/usr/bin/true"]
            assert final_argv == [v20.SANDBOX_EXEC, "-p", profile, codex, *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments]
            assert profile.startswith("(version 1)\n(deny default)\n") and "(allow network-outbound)" in profile
            assert profile == v20.SANDBOX_PROFILE_TEMPLATE.format(directory=str(Path(popen.call_args.kwargs["cwd"]).resolve()))
            assert popen.call_args.kwargs["start_new_session"] is True
        # The reservation was consumed (fixed terminal state), never released for another attempt.
        assert ledger._read_local()["records"][-1]["state"] == "unknown" and remote.pushes == 3
        cases += 1
    return cases


def spawn_once_and_wiring_tests():
    """N-1 (at most one spawn per reservation), M-1 (real _fixed_config/_fixed_ledger wiring),
    m-1 (pre-reserve remote check) and m-2 (codex identity)."""
    from unittest.mock import MagicMock
    cases = 0
    real_run = subprocess.run
    real_popen = subprocess.Popen
    def selective_popen(args, *a, **kw):
        # Only the sandboxed Codex spawn is faked (and fails); git on the local bare remote stays real.
        if args and args[0] == v20.SANDBOX_EXEC:
            raise OSError("mock spawn")
        return real_popen(args, *a, **kw)
    def sandbox_spawns(mock):
        return [c for c in mock.call_args_list if c.args and c.args[0] and c.args[0][0] == v20.SANDBOX_EXEC]
    def fake_probe(args, **kwargs):
        # Only the sandbox-exec availability probe is faked; git (local bare remote) stays real.
        if args and args[0] == v20.SANDBOX_EXEC:
            return subprocess.CompletedProcess(args, 0, b"", b"")
        return real_run(args, **kwargs)
    with tempfile.TemporaryDirectory(prefix="p5-v20-spawn-once-") as td:
        root = Path(td)
        counter = {"n": 0}
        def sandbox_dir():
            counter["n"] += 1
            path = root / f"sandbox-{counter['n']}"; path.mkdir(mode=0o700)
            return path
        def invoke(adapter, record, binding, sandbox):
            return adapter.invoke(record["deadline_epoch"], attempt_id=record["id"], binding=binding,
                                  sandbox_directory=sandbox, actual_enabled=True)

        # N-1: one reservation spawns at most once, whether or not the first spawn succeeded.
        for label in ("spawn-failed", "spawn-ok"):
            config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "once-" + label)
            record = ledger.reserve(role="diagnostic", binding=binding)
            child = MagicMock(); child.communicate.return_value = (b"", b""); child.poll.return_value = 0
            child.returncode = 0; child.pid = 4242
            popen_patch = (patch("v20_diagnostic.subprocess.Popen", side_effect=OSError("mock spawn"))
                           if label == "spawn-failed" else patch("v20_diagnostic.subprocess.Popen", return_value=child))
            with patch.object(v20, "_fixed_config", lambda _b: config), \
                    patch.object(v20, "_fixed_ledger", lambda _c: ledger), \
                    patch.object(v20, "_production_residual_scanner", lambda *_: True), \
                    popen_patch as popen, patch("v20_diagnostic.subprocess.run", side_effect=fake_probe):
                try:
                    invoke(adapter, record, binding, sandbox_dir())
                except v20.LedgerError:
                    pass
                else:
                    raise AssertionError("first invocation produced a report from a mock")
                assert popen.call_count == 1
                assert ledger._read_local()["records"][-1]["state"] == "running"
                pushes = remote.pushes
                for _ in range(2):
                    try:
                        invoke(adapter, record, binding, sandbox_dir())
                    except v20.LedgerError as exc:
                        assert str(exc) == "spawn_reservation_invalid", str(exc)
                    else:
                        raise AssertionError("second spawn of one reservation accepted")
                assert popen.call_count == 1 and remote.pushes == pushes
            cases += 1

        # M-1(3): local and remote disagree although the local ledger holds a spawn-authorized reservation.
        for label, tamper, code in (
                ("remote-head-moved", lambda r: setattr(r, "head_hash", "c" * 40), "remote_local_head_mismatch"),
                ("remote-record-lost", lambda r: setattr(r, "records", r.records[:2]), "remote_local_chain_mismatch")):
            config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "mismatch-" + label)
            record = ledger.reserve(role="diagnostic", binding=binding)
            tamper(remote)
            _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"], record["id"], sandbox_dir(), code)
            cases += 1

        # m-2: the executable identity bound in config (dev/ino/size/mode/ctime) is re-checked at the boundary.
        for field, value in (("ctime_ns", None), ("mode", 0o755 if Path(argv[0]).stat().st_mode & 0o777 != 0o755 else 0o700),
                             ("inode", None), ("size", None)):
            def mutate(c, field=field, value=value):
                binding_copy = dict(c["codex_binding"])
                binding_copy[field] = (binding_copy[field] + 1) if value is None else value
                return dict(c, codex_binding=binding_copy)
            config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "identity-" + field, mutate_config=mutate)
            record = ledger.reserve(role="diagnostic", binding=binding)
            _spawn_denied(config, ledger, adapter, binding, record["deadline_epoch"], record["id"], sandbox_dir(),
                          "fixed_cli_binding_invalid")
            assert ledger._read_local()["records"][-1]["state"] == "reserved"
            cases += 1

        # m-1: an unreachable/inconsistent remote stops before reserve(): nothing is consumed.
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "preflight")
        out = root / "preflight-out"; out.mkdir(mode=0o700)
        remote.mode = "unreachable"
        with patch.object(v20, "_fixed_config", lambda _b: config), patch.object(v20, "_fixed_ledger", lambda _c: ledger), \
                patch("v20_diagnostic.subprocess.Popen") as popen, patch("v20_diagnostic.subprocess.run") as run:
            try:
                v20.run_diagnostic_once(ledger, binding=binding, adapter=adapter, artifact_directory=out / "result",
                    next_binding_factory=lambda _: _binding("e" * 64), actual_enabled=True)
            except v20.LedgerError as exc:
                assert str(exc) == "spawn_reservation_invalid"
            else:
                raise AssertionError("lifecycle continued with an unreachable remote")
            assert popen.call_count == 0 and run.call_count == 0
        remote.mode = None
        assert remote.pushes == 0 and len(ledger._read_local()["records"]) == 2
        cases += 1

        # M-1(1): real _fixed_config (no mock).
        art = root / "cfg-artifact"; art.mkdir()
        (art / "config.json").write_bytes(v20.canonical_bytes({"seed_commit_pin": None, "k": 1}))
        assert v20._fixed_config({"artifact_root": str(art)}) == {"seed_commit_pin": None, "k": 1}
        cases += 1
        bad_cases = {"invalid-json": b"{", "not-dict": b"[]\n", "duplicate-key": b'{"a":1,"a":2}'}
        for label, payload in bad_cases.items():
            d = root / f"cfg-{label}"; d.mkdir(); (d / "config.json").write_bytes(payload)
            for binding_arg in ({"artifact_root": str(d)},):
                try:
                    v20._fixed_config(binding_arg)
                except v20.LedgerError as exc:
                    assert str(exc) == "fixed_cli_binding_invalid", (label, str(exc))
                else:
                    raise AssertionError(f"bad config accepted: {label}")
            cases += 1
        (root / "cfg-empty").mkdir()
        for label, binding_arg in (("missing-file", {"artifact_root": str(root / "cfg-empty")}),
                                   ("missing-key", {}), ("wrong-type", {"artifact_root": None})):
            try:
                v20._fixed_config(binding_arg)
            except v20.LedgerError as exc:
                assert str(exc) == "fixed_cli_binding_invalid", (label, str(exc))
            else:
                raise AssertionError(f"unreadable config accepted: {label}")
            cases += 1

        # M-1(2): real _fixed_ledger passes the config values (pin, repository, ledger directory) through.
        seen = {}
        class StubRemote:
            def __init__(self, repo, **kwargs):
                seen["remote"] = (repo, kwargs)
        class StubLedger:
            def __init__(self, directory, remote):
                seen["ledger"] = (directory, remote)
        with patch.object(v20, "GitRemote", StubRemote), patch.object(v20, "GlobalLedger", StubLedger):
            produced = v20._fixed_ledger({"repository_path": "/fixture/repo", "seed_commit_pin": "b" * 40,
                                          "global_ledger_directory": "/fixture/ledger"})
        assert isinstance(produced, StubLedger)
        assert seen["remote"] == (Path("/fixture/repo"), {"seed_commit_pin": "b" * 40})
        assert seen["ledger"][0] == Path("/fixture/ledger") and isinstance(seen["ledger"][1], StubRemote)
        cases += 1

        # M-1: end to end through the real _fixed_config + _fixed_ledger + GitRemote on a local bare remote.
        bare = root / "wired-remote.git"; repo = root / "wired-client"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(bare)], check=True, capture_output=True)
        repo.mkdir()
        for args in (["init", "--initial-branch=main"], ["config", "user.name", "P5 Fixture"],
                     ["config", "user.email", "p5-fixture-local"], ["remote", "add", "origin", str(bare)]):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        history = [dict(x, type="historical_attempt") for x in v20.HISTORICAL]
        seed = v20.canonical_bytes({"schema": 1, "records": history})
        first = v20.GitRemote(repo).push_ff(None, seed)
        artifact_config = v20.strict_json((Path(v20.__file__).resolve().parent / "config.json").read_bytes())
        codex = artifact_config["codex_binding"]["realpath"]
        argv = (codex, *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)
        def wired(label, *, pin):
            art_dir = root / f"wired-art-{label}"; art_dir.mkdir()
            wired_config = dict(artifact_config, seed_commit_pin=pin, repository_path=str(repo),
                                global_ledger_directory=str(root / f"wired-state-{label}"))
            (art_dir / "config.json").write_bytes(v20.canonical_bytes(wired_config))
            binding = dict(_binding("wired-" + label), artifact_root=str(art_dir))
            return wired_config, binding
        with patch.object(v20, "validate_binding", lambda b: b), \
                patch("v20_diagnostic.subprocess.run", side_effect=fake_probe):
            # unpinned config read from disk by the real _fixed_config
            wired_config, binding = wired("unpinned", pin=None)
            adapter = v20.FixedOpenAIDirectCodexAdapter(argv, command_sha256=binding["command_sha256"],
                binding=binding, residual_scanner=v20._production_residual_scanner)
            with patch("v20_diagnostic.subprocess.Popen") as popen:
                try:
                    adapter.invoke(time.time() + 60, attempt_id="0123456789abcdef0123456789abcdef", binding=binding,
                                   sandbox_directory=sandbox_dir(), actual_enabled=True)
                except v20.LedgerError as exc:
                    assert str(exc) == "seed_commit_pin_missing"
                else:
                    raise AssertionError("unpinned config accepted")
                assert popen.call_count == 0
            cases += 1
            # pinned: reserve in the real fixed ledger, spawn once, then refuse a second spawn.
            wired_config, binding = wired("pinned", pin=first)
            fixed = v20._fixed_ledger(wired_config)
            fixed._write_local(history, first)
            record = fixed.reserve(role="diagnostic", binding=binding)
            adapter = v20.FixedOpenAIDirectCodexAdapter(argv, command_sha256=binding["command_sha256"],
                binding=binding, residual_scanner=v20._production_residual_scanner)
            with patch("v20_diagnostic.subprocess.Popen", side_effect=selective_popen) as popen:
                try:
                    invoke(adapter, record, binding, sandbox_dir())
                except v20.LedgerError as exc:
                    assert str(exc) == "diagnostic_cli_spawn_failed"
                else:
                    raise AssertionError("mock spawn unexpectedly succeeded")
                assert len(sandbox_spawns(popen)) == 1
                remote_view = v20.GitRemote(repo, seed_commit_pin=first)
                assert remote_view.chain(remote_view.ls_remote())[-1]["state"] == "running"
                try:
                    invoke(adapter, record, binding, sandbox_dir())
                except v20.LedgerError as exc:
                    assert str(exc) == "spawn_reservation_invalid"
                else:
                    raise AssertionError("second spawn through the real fixed ledger accepted")
                assert len(sandbox_spawns(popen)) == 1
            cases += 1
    return cases


def profile_negative_tests():
    """Profile body / sandbox directory / extra-argv faults: fixed error, no process, no reservation."""
    cases = 0
    with tempfile.TemporaryDirectory(prefix="p5-v20-profile-negative-") as td:
        root = Path(td); sandbox = root / "sandbox"; sandbox.mkdir(mode=0o700)
        python = os.path.realpath(__import__("sys").executable)
        tampered = v20.SANDBOX_PROFILE_TEMPLATE.replace("(allow network-outbound)\n", "(allow network*)\n")
        assert tampered != v20.SANDBOX_PROFILE_TEMPLATE
        # (a) template body changed while the pinned hash constant is kept.
        with patch.object(v20, "SANDBOX_PROFILE_TEMPLATE", tampered), \
                patch("v20_diagnostic.subprocess.Popen") as popen, patch("v20_diagnostic.subprocess.run") as run:
            assert v20.sha256(v20.SANDBOX_PROFILE_TEMPLATE.encode()) != v20.SANDBOX_PROFILE_SHA256
            for call in (lambda: v20.sandboxed_argv((python,), sandbox),
                         lambda: v20.run_process_group((python, "-c", "pass"), deadline_epoch=time.time() + 5,
                             residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox)):
                try:
                    call()
                except v20.LedgerError as exc:
                    assert str(exc) == "host_containment_profile_mismatch"
                else:
                    raise AssertionError("profile body drift accepted")
                cases += 1
            assert popen.call_count == 0 and run.call_count == 0
        # (b) sandbox_directory missing/not a directory.
        with patch("v20_diagnostic.subprocess.Popen") as popen, patch("v20_diagnostic.subprocess.run") as run:
            for bad in (None, root / "absent", root / "file-not-dir"):
                if bad == root / "file-not-dir":
                    bad.write_text("x")
                for call in (lambda: v20.sandboxed_argv((python,), bad),
                             lambda: v20.run_process_group((python, "-c", "pass"), deadline_epoch=time.time() + 5,
                                 residual_scanner=lambda *_: True, cwd=root, sandbox_directory=bad)):
                    try:
                        call()
                    except v20.LedgerError as exc:
                        assert str(exc) == "host_containment_unavailable"
                    else:
                        raise AssertionError("missing sandbox directory accepted")
                    cases += 1
            assert popen.call_count == 0 and run.call_count == 0
        # (c) another profile / extra argv supplied as the child command.
        with patch("v20_diagnostic.subprocess.Popen") as popen, patch("v20_diagnostic.subprocess.run") as run:
            for argv in ((v20.SANDBOX_EXEC, "-p", "(version 1)(allow default)", "/usr/bin/true"),
                         (v20.SANDBOX_EXEC, "-f", "/private/tmp/other.sb", "/usr/bin/true")):
                try:
                    v20.run_process_group(argv, deadline_epoch=time.time() + 5, residual_scanner=lambda *_: True,
                                          cwd=sandbox, sandbox_directory=sandbox)
                except v20.LedgerError as exc:
                    assert str(exc) == "host_containment_profile_mismatch"
                else:
                    raise AssertionError("caller-supplied sandbox profile accepted")
                cases += 1
            assert popen.call_count == 0 and run.call_count == 0

        # Adapter-level: profile drift/replacement/extra argv stops before reservation and callback.
        base_cfg, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "profile-adapter")
        def lifecycle_rejected(label, candidate, *, patches=()):
            calls_before = remote.pushes
            from contextlib import ExitStack
            with ExitStack() as stack, patch("v20_diagnostic.subprocess.Popen") as popen, \
                    patch("v20_diagnostic.subprocess.run") as run:
                for item in patches:
                    stack.enter_context(item)
                try:
                    v20.run_diagnostic_once(ledger, binding=binding, adapter=candidate,
                        artifact_directory=root / "out", next_binding_factory=lambda _: _binding("e" * 64),
                        actual_enabled=True)
                except v20.LedgerError as exc:
                    assert str(exc) == "fixed_cli_binding_invalid", (label, str(exc))
                else:
                    raise AssertionError(f"profile fault accepted: {label}")
                assert popen.call_count == 0 and run.call_count == 0
            assert remote.pushes == calls_before and len(ledger._read_local()["records"]) == 2, label
        # template body replaced (hash constant kept): command hash no longer matches the binding.
        lifecycle_rejected("template body", adapter, patches=(patch.object(v20, "SANDBOX_PROFILE_TEMPLATE", tampered),))
        # template and its hash replaced together: the adapter's sealed profile hash differs.
        lifecycle_rejected("template and hash", adapter, patches=(
            patch.object(v20, "SANDBOX_PROFILE_TEMPLATE", tampered),
            patch.object(v20, "SANDBOX_PROFILE_SHA256", v20.sha256(tampered.encode()))))
        # sealed argv replaced by an explicit other-profile sandbox-exec command / extra argument.
        for label, replacement in (("other profile argv", (v20.SANDBOX_EXEC, "-p", "(version 1)(allow default)", codex,
                                                           *v20.FixedOpenAIDirectCodexAdapter.fixed_arguments)),
                                   ("extra argv", (*argv, "--dangerously-bypass-approvals-and-sandbox"))):
            _, _, _, _, victim, _, _ = _spawn_context(root, "victim-" + label.replace(" ", "-"))
            object.__setattr__(victim, "_argv", replacement)
            lifecycle_rejected(label, victim)
        cases += 4
    return cases


def canary_classification_tests():
    """Run the production canary in a fixture subprocess (no Codex, no model): only PATH is classifiable."""
    import sys as _sys
    cases = 0
    uid_name = __import__("pwd").getpwuid(os.getuid()).pw_name
    with tempfile.TemporaryDirectory(prefix="p5-v20-canary-fixture-") as td:
        def run_case(label, *, env_changes=None, expected_changes=None, other_cwd=False, drop_env=()):
            case_root = Path(td) / label
            work = case_root / "work"; work.mkdir(parents=True, mode=0o700)
            work = work.resolve(strict=True)
            home = str(case_root / "home")
            expected_cwd = str(work)
            if other_cwd:
                other = case_root / "other"; other.mkdir(); expected_cwd = str(other.resolve(strict=True))
            parts = ["/usr/bin", "/bin"]
            path_hash = hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()
            required = {"PATH": os.pathsep.join(parts), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": home,
                        "TMPDIR": str(work / "tmp"), "TMP": str(work / "tmp"), "TEMP": str(work / "tmp"),
                        "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                        "GIT_OPTIONAL_LOCKS": "0", "P5_RUN_TOKEN": "ab" * 16}
            if _sys.platform == "darwin":
                required["__CF_USER_TEXT_ENCODING"] = f"0x{os.getuid():X}:0x0:0x0"
            uuid7 = "01234567-89ab-7cde-8f01-23456789abcd"
            runtime = {"CODEX_CI": "1", "CODEX_PERMISSION_PROFILE": "p5_fixture", "CODEX_SANDBOX": "seatbelt",
                       "CODEX_SANDBOX_NETWORK_DISABLED": "1", "CODEX_SESSION_ID": uuid7, "CODEX_THREAD_ID": uuid7,
                       "CODEX_VERSION": "0.163.0", "COLORTERM": "", "GH_PAGER": "cat", "GIT_PAGER": "cat",
                       "LC_CTYPE": "C.UTF-8", "LOGNAME": uid_name, "NO_COLOR": "1", "OLDPWD": expected_cwd,
                       "PAGER": "cat", "PWD": expected_cwd, "SHLVL": "0", "TERM": "dumb", "_": _sys.executable}
            expected = {"attempt_id": TRUSTED_ID.replace("a", "b"), "fingerprint": TRUSTED_FP,
                        "env": dict(required), "required_keys": list(v20._DIAGNOSTIC_REQUIRED_KEYS),
                        "runtime_keys": sorted(v20._DIAGNOSTIC_RUNTIME_KEYS),
                        "path_profiles": {"normal_shell_login": path_hash}, "home": home,
                        "locale_sha256": v20.sha256(b"C.UTF-8"), "cli_version": "0.163.0",
                        "uuid7_pattern": r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                        "python_executable": _sys.executable, "cwd": expected_cwd, "known_path_components": []}
            expected.update(expected_changes or {})
            env = {**required, **runtime, **(env_changes or {})}
            for key in drop_env:
                env.pop(key, None)
            (work / ".p5-v20-expected.json").write_bytes(v20.canonical_bytes(expected))
            (work / ".p5-v20-env-canary.py").write_text(v20._diagnostic_canary_source(), encoding="utf-8")
            outcome = subprocess.run([_sys.executable, "-I", "-B", ".p5-v20-env-canary.py"], cwd=work, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            return outcome, expected
        # Baseline and PATH-only mismatch stay classifiable (resolved diagnostic, never final eligibility).
        outcome, expected = run_case("baseline")
        assert outcome.returncode == 0, outcome.stderr
        report = v20.validate_report(v20.strict_json(outcome.stdout), attempt_id=expected["attempt_id"],
                                     fingerprint=expected["fingerprint"])
        assert report["environment_fit"] == "pass" and report["determination"] == "resolved"
        cases += 1
        outcome, expected = run_case("path-only", env_changes={"PATH": "/usr/bin:/bin:/opt/not-approved"})
        assert outcome.returncode == 0, outcome.stderr
        report = v20.validate_report(v20.strict_json(outcome.stdout), attempt_id=expected["attempt_id"],
                                     fingerprint=expected["fingerprint"])
        assert report["environment_fit"] == "mismatch" and report["determination"] == "resolved"
        assert report["path"]["order_classification"] == "unapproved_component_present"
        cases += 1
        # Any non-PATH required/runtime/cwd mismatch (or several) has no schema cause: no report at all.
        unresolved = {
            "required-value": dict(env_changes={"HOME": "/unexpected/home"}),
            "required-token": dict(env_changes={"P5_RUN_TOKEN": "cd" * 16}),
            "required-missing": dict(drop_env=("GIT_OPTIONAL_LOCKS",)),
            "runtime-value": dict(env_changes={"TERM": "xterm-256color"}),
            "runtime-sandbox": dict(env_changes={"CODEX_SANDBOX": "none"}),
            "runtime-version": dict(env_changes={"CODEX_VERSION": "9.9.9"}),
            "cwd-only": dict(other_cwd=True),
            "multiple": dict(env_changes={"HOME": "/unexpected/home", "TERM": "xterm", "NO_COLOR": "0"}, other_cwd=True),
            "path-and-runtime": dict(env_changes={"PATH": "/usr/bin:/bin:/opt/not-approved", "TERM": "xterm"}),
        }
        for label, kwargs in unresolved.items():
            outcome, _ = run_case(label, **kwargs)
            assert outcome.returncode == 2 and outcome.stdout == b"", (label, outcome.returncode, outcome.stdout[:80])
            cases += 1

    # The fixed exit code is audited as a fixed inconclusive stop (not completed/resolved, not a raw failure).
    command = "/bin/zsh -lc /fixed/canary"
    events = [{"type": "thread.started", "thread_id": "synthetic"}, {"type": "turn.started"},
              {"type": "item.started", "item": {"id": "tool-1", "type": "command_execution", "command": command,
                                                 "status": "in_progress"}},
              {"type": "item.completed", "item": {"id": "tool-1", "type": "command_execution", "command": command,
                                                   "status": "failed", "exit_code": 2, "aggregated_output": ""}},
              {"type": "turn.completed"}]
    def encode(items):
        return b"\n".join(v20.canonical_bytes(item).rstrip(b"\n") for item in items)
    try:
        v20._audit_diagnostic_events(encode(events), canary_command=command, attempt_id=TRUSTED_ID, fingerprint=TRUSTED_FP)
    except v20.LedgerError as exc:
        assert str(exc) == "diagnostic_inconclusive"
    else:
        raise AssertionError("canary exit 2 produced a report")
    cases += 1
    for code in (1, 3, 127):
        changed = json.loads(json.dumps(events)); changed[3]["item"]["exit_code"] = code
        try:
            v20._audit_diagnostic_events(encode(changed), canary_command=command, attempt_id=TRUSTED_ID, fingerprint=TRUSTED_FP)
        except v20.LedgerError as exc:
            assert str(exc) == "diagnostic_event_audit_failed"
        else:
            raise AssertionError("non-fixed canary failure accepted")
        cases += 1
    # exit 2 without a complete event lifecycle remains an audit failure.
    try:
        v20._audit_diagnostic_events(encode(events[:4]), canary_command=command, attempt_id=TRUSTED_ID, fingerprint=TRUSTED_FP)
    except v20.LedgerError as exc:
        assert str(exc) == "diagnostic_event_audit_failed"
    else:
        raise AssertionError("incomplete lifecycle accepted")
    cases += 1

    # End to end: the inconclusive stop consumes the reservation and is recorded as diagnostic_inconclusive.
    with tempfile.TemporaryDirectory(prefix="p5-v20-canary-lifecycle-") as td:
        root = Path(td); (root / "out").mkdir(mode=0o700)
        config, codex, argv, binding, adapter, remote, ledger = _spawn_context(root, "canary-inconclusive")
        def inconclusive_cli(*args, **kwargs):
            raise v20.LedgerError("diagnostic_inconclusive")
        with patch.object(v20, "_invoke_diagnostic_cli", inconclusive_cli), \
                patch.object(v20, "_fixed_config", lambda _b: config), patch.object(v20, "_fixed_ledger", lambda _c: ledger), \
                patch("v20_diagnostic.subprocess.Popen") as popen:
            try:
                v20.run_diagnostic_once(ledger, binding=binding, adapter=adapter,
                    artifact_directory=root / "out" / "result", next_binding_factory=lambda _: _binding("e" * 64),
                    actual_enabled=True)
            except v20.LedgerError as exc:
                assert str(exc) == "diagnostic_inconclusive"
            else:
                raise AssertionError("inconclusive diagnostic completed")
            assert popen.call_count == 0
        last = ledger._read_local()["records"][-1]
        assert last["state"] == "diagnostic_inconclusive" and last["determination"] == "inconclusive"
        cases += 1
    return cases


def run_all():
    counts = {"schema": schema_tests(), "privacy": privacy_tests(), "path_unknown": path_and_unknown_tests(),
              "ledger": ledger_tests(), "phase_binding": phase_binding_tests(), "artifact_attribution": artifact_attribution_tests(),
              "formal_gate": gate_tests(), "remote_fixture": git_remote_fixture_tests(),
              "seed_canonical": seed_canonical_tests(), "diagnostic_lifecycle": diagnostic_lifecycle_tests(),
              "production_runner": production_runner_tests(), "spawn_boundary": spawn_boundary_tests(),
              "spawn_once_wiring": spawn_once_and_wiring_tests(), "profile_negative": profile_negative_tests(), "canary_classification": canary_classification_tests()}
    return counts


if __name__ == "__main__":
    counts = run_all()
    print("v20 selftest: PASS " + json.dumps(counts, sort_keys=True))
