#!/usr/bin/env python3
"""P5 v20 diagnostic schema and global budget ledger primitives.

This module contains no model client. Remote operations are provided through a
small injected interface so all reservation behavior can be exercised offline.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import uuid

VERSION = 20
HARD_CAP = 28
FORMAL_SECONDS = 120 * 60
def _hex(*chunks):
    return "".join(chunks)

HISTORICAL = (
    {"id": _hex("7425", "e11b", "51a4", "411b", "baa1", "ad30", "7827", "1387"), "version": 18,
     "fingerprint": _hex("0d34", "0831", "6229", "5255", "d680", "6266", "19bf", "3960", "fd45", "e698", "b140", "2e0e", "1d99", "8d6a", "22fa", "c321"),
     "result_sha256": _hex("7c16", "dae0", "ff7d", "d580", "a89b", "4cc2", "3d2b", "c937", "1ad4", "ab00", "3bd1", "2828", "fb6e", "3aa3", "f30b", "7785"),
     "state": "fail", "elapsed_seconds": float.fromhex("0x1.6548" + "0880" + "0000p+3")},
    {"id": _hex("7999", "12ca", "d216", "402f", "bfb4", "711b", "8d8b", "6b60"), "version": 19,
     "fingerprint": _hex("8120", "5c4f", "7c39", "89b4", "39dc", "4baa", "4ed9", "5d04", "329d", "dd35", "53bb", "3200", "13ed", "c4df", "7f0f", "62e6"),
     "result_sha256": _hex("2eec", "ef40", "bb3b", "3e7f", "d5f1", "d1f6", "a8e9", "cc9a", "2c8f", "2e2c", "6e94", "3ec3", "32ea", "df17", "ae37", "089b"),
     "state": "fail", "elapsed_seconds": float.fromhex("0x1.8a4a" + "6200" + "0000p+3")},
)
SEED_SHA256 = _hex("65c0", "9467", "91cf", "ac1e", "f0ad", "63ad", "9c5b", "a08d", "e833", "0f64", "21f7", "9b69", "caa3", "cff1", "5b40", "ef90")
REMOTE_REF = "refs/heads/codex/runtime-migration-p5-ledger"
PATH_PROFILES = frozenset({"normal_shell_login", "normal_shell_codex_host_projection", "codex_host"})
PATH_CLASSES = frozenset({"exact_profile", "known_components_reordered", "unapproved_component_present", "empty", "malformed"})
UNKNOWN_CLASSES = frozenset({"none", "codex_home_only", "other_unknown_present", "mixed"})
FIT = frozenset({"pass", "mismatch", "unknown"})
DETERMINATIONS = frozenset({"resolved", "inconclusive"})
STATES = frozenset({"reserved", "running", "completed_diagnostic", "diagnostic_inconclusive",
                    "final_pass", "final_fail", "formal_run_pass", "formal_run_fail",
                    "timeout", "crash", "unknown"})


class LedgerError(ValueError):
    """Stable, non-sensitive ledger failure."""


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError("duplicate_json_key")
        result[key] = value
    return result


def strict_json(data: bytes | str):
    try:
        return json.loads(data, object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(LedgerError("invalid_json_number")))
    except LedgerError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError):
        raise LedgerError("invalid_json") from None


def canonical_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                        allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_seed_payload(payload: bytes) -> tuple[dict, str]:
    """Check committed seed bytes, exact historical records and pinned digest."""
    digest = sha256(payload)
    if digest != SEED_SHA256:
        raise LedgerError("seed_digest_mismatch")
    parsed = strict_json(payload)
    if type(parsed) is not dict or set(parsed) != {"schema", "records"} or type(parsed["schema"]) is not int or parsed["schema"] != 1:
        raise LedgerError("seed_schema_invalid")
    expected = []
    for record in HISTORICAL:
        expected.append({"elapsed_seconds": record["elapsed_seconds"], "fingerprint": record["fingerprint"],
                         "id": record["id"], "result_sha256": record["result_sha256"],
                         "state": record["state"], "type": "historical_attempt", "version": record["version"]})
    if parsed["records"] != expected or payload != canonical_bytes(parsed):
        raise LedgerError("seed_history_mismatch")
    return parsed, digest


def classify_path(path_value, profile_hashes: dict[str, str], known_component_hashes: frozenset[str]) -> dict:
    """Return aggregate-only PATH classification; never return values or digests."""
    if path_value is None:
        path_value = ""
    if not isinstance(path_value, str) or "\x00" in path_value:
        return {"matched_profile": "none", "component_count": 0,
                "unapproved_component_count": 0, "order_classification": "malformed"}
    parts = path_value.split(os.pathsep) if path_value else []
    if len(parts) > 128:
        return {"matched_profile": "none", "component_count": 0,
                "unapproved_component_count": 0, "order_classification": "malformed"}
    digest = sha256(canonical_bytes(parts))
    matched = next((name for name, value in profile_hashes.items() if name in PATH_PROFILES and value == digest), None)
    unknown = sum(1 for part in parts if not part or sha256(part.encode("utf-8")) not in known_component_hashes)
    if not parts:
        kind = "empty"
    elif matched:
        kind = "exact_profile"
    elif unknown:
        kind = "unapproved_component_present"
    else:
        kind = "known_components_reordered"
    return {"matched_profile": matched or "none", "component_count": len(parts),
            "unapproved_component_count": unknown, "order_classification": kind}


def classify_unknown_keys(keys, allowed_keys: frozenset[str]) -> dict:
    if type(keys) not in (list, tuple) or len(keys) > 128 or any(type(k) is not str for k in keys):
        raise LedgerError("unknown_key_inventory_invalid")
    unknown = [key for key in keys if key == "CODEX_HOME" or key not in allowed_keys]
    codex_home = "CODEX_HOME" in unknown
    other_count = len(unknown) - int(codex_home)
    count = len(unknown)
    category = ("none" if count == 0 else "codex_home_only" if codex_home and other_count == 0
                else "other_unknown_present" if not codex_home else "mixed")
    return {"codex_home_present": codex_home, "classification": category,
            "unknown_count": count, "other_unknown_count": other_count}


def validate_report(report: dict, *, attempt_id: str, fingerprint: str) -> dict:
    top = {"schema", "attempt_id", "fingerprint", "environment_fit", "path", "unknown_keys", "determination"}
    if type(report) is not dict or set(report) != top:
        raise LedgerError("diagnostic_schema_invalid")
    if type(report["schema"]) is not int or report["schema"] != 1:
        raise LedgerError("diagnostic_schema_invalid")
    if (type(report["attempt_id"]) is not str or type(report["fingerprint"]) is not str
            or report["attempt_id"] != attempt_id or report["fingerprint"] != fingerprint):
        raise LedgerError("diagnostic_binding_mismatch")
    if (type(report["environment_fit"]) is not str or report["environment_fit"] not in FIT
            or type(report["determination"]) is not str or report["determination"] not in DETERMINATIONS):
        raise LedgerError("diagnostic_enum_invalid")
    p, u = report["path"], report["unknown_keys"]
    if type(p) is not dict or set(p) != {"matched_profile", "component_count", "unapproved_component_count", "order_classification"}:
        raise LedgerError("diagnostic_path_schema_invalid")
    if (type(p["matched_profile"]) is not str or p["matched_profile"] not in PATH_PROFILES | {"none"}
            or type(p["order_classification"]) is not str or p["order_classification"] not in PATH_CLASSES
            or any(type(p[k]) is not int or not 0 <= p[k] <= 128 for k in ("component_count", "unapproved_component_count"))):
        raise LedgerError("diagnostic_path_value_invalid")
    if report["environment_fit"] == "unknown" or p["order_classification"] == "malformed":
        raise LedgerError("diagnostic_inconclusive")
    if type(u) is not dict or set(u) != {"codex_home_present", "classification", "unknown_count", "other_unknown_count"}:
        raise LedgerError("diagnostic_unknown_schema_invalid")
    if (type(u["codex_home_present"]) is not bool or type(u["classification"]) is not str or u["classification"] not in UNKNOWN_CLASSES
            or any(type(u[k]) is not int or not 0 <= u[k] <= 128 for k in ("unknown_count", "other_unknown_count"))):
        raise LedgerError("diagnostic_unknown_value_invalid")
    if u["unknown_count"] != int(u["codex_home_present"]) + u["other_unknown_count"]:
        raise LedgerError("diagnostic_unknown_count_inconsistent")
    expected_class = ("none" if u["unknown_count"] == 0 else "codex_home_only" if u["codex_home_present"] and u["other_unknown_count"] == 0
                      else "other_unknown_present" if not u["codex_home_present"] else "mixed")
    if expected_class != u["classification"]:
        raise LedgerError("diagnostic_unknown_class_inconsistent")
    if ((p["order_classification"] == "exact_profile") != (p["matched_profile"] != "none")
            or (p["order_classification"] == "unapproved_component_present") != (p["unapproved_component_count"] > 0)
            or (p["order_classification"] == "empty") != (p["component_count"] == 0)
            or (p["order_classification"] in {"exact_profile", "known_components_reordered"} and p["unapproved_component_count"] != 0)):
        raise LedgerError("diagnostic_path_inconsistent")
    must_inconclusive = (report["environment_fit"] == "unknown" or p["order_classification"] == "malformed"
                         or u["other_unknown_count"] > 0 or p["unapproved_component_count"] > 1)
    if (report["environment_fit"] == "pass"
            and (u["unknown_count"] != 0 or p["matched_profile"] == "none"
                 or p["order_classification"] != "exact_profile")):
        raise LedgerError("diagnostic_environment_fit_inconsistent")
    expected_det = "inconclusive" if must_inconclusive else "resolved"
    if report["determination"] != expected_det:
        raise LedgerError("diagnostic_determination_inconsistent")
    return report


def report_for_storage(report: dict, *, attempt_id: str, fingerprint: str) -> bytes:
    """Rebuild from schema allowlist; input maps/raw exceptions never reach storage."""
    validated = validate_report(report, attempt_id=attempt_id, fingerprint=fingerprint)
    return canonical_bytes({key: validated[key] for key in
                            ("schema", "attempt_id", "fingerprint", "environment_fit", "path", "unknown_keys", "determination")})


ARTIFACT_NAMES = frozenset({"stdout.txt", "stderr.txt", "answer.json", "raw.jsonl", "temporary.spool",
                            "result.json", "summary.json", "audit.json", "diagnostic.json", "public.md", "error.json"})


def artifact_bundle(*, report_bytes: bytes | None = None, error: Exception | None = None) -> dict[str, bytes]:
    """Construct complete output set solely from fixed schema or stable error enum."""
    if (report_bytes is None) == (error is None):
        raise LedgerError("artifact_bundle_input_invalid")
    bundle = {name: b"" for name in ARTIFACT_NAMES}
    if report_bytes is not None:
        report = strict_json(report_bytes)
        safe = report_for_storage(report, attempt_id=report.get("attempt_id"), fingerprint=report.get("fingerprint"))
        bundle["result.json"] = safe
        bundle["summary.json"] = safe
        bundle["audit.json"] = safe
        bundle["diagnostic.json"] = safe
        item = strict_json(safe)
        bundle["public.md"] = ("# P5 diagnostic\n\n"
                               f"Environment fit: {item['environment_fit']}\n\n"
                               f"Determination: {item['determination']}\n\n"
                               f"PATH classification: {item['path']['order_classification']}\n\n"
                               f"Unknown-key classification: {item['unknown_keys']['classification']}\n").encode()
    else:
        code = fixed_error(error)
        bundle["error.json"] = canonical_bytes({"error": code})
        bundle["stderr.txt"] = (code + "\n").encode("ascii")
    return bundle


def save_artifact_bundle(directory: Path, bundle: dict[str, bytes]):
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise LedgerError("artifact_directory_identity_invalid")
    if type(bundle) is not dict or set(bundle) != ARTIFACT_NAMES or any(type(v) is not bytes for v in bundle.values()):
        raise LedgerError("artifact_bundle_schema_invalid")
    for name, data in bundle.items():
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def formal_start_eligible(records: list[dict]) -> bool:
    """Gate formal start on fixed history, exactly one resolved diagnostic and one PASS final."""
    if type(records) is not list or len(records) != 4 or any(type(r) is not dict for r in records):
        return False
    expected_history = [dict(x, type="historical_attempt") for x in HISTORICAL]
    if records[:2] != expected_history:
        return False
    diagnostic = [r for r in records[2:] if r.get("role") == "diagnostic"]
    final = [r for r in records[2:] if r.get("role") == "final_probe"]
    return (len(diagnostic) == 1 and diagnostic[0].get("state") == "completed_diagnostic"
            and diagnostic[0].get("determination") == "resolved" and len(final) == 1
            and re.fullmatch(r"[0-9a-f]{64}", diagnostic[0].get("report_sha256", ""))
            and final[0].get("state") == "final_pass"
            and re.fullmatch(r"[0-9a-f]{64}", final[0].get("gate_evidence_sha256", ""))
            and all(r.get("role") in {"diagnostic", "final_probe", "formal_run"} for r in records[2:]))


def formal_complete(records: list[dict]) -> bool:
    if (type(records) is not list or len(records) != HARD_CAP or any(type(r) is not dict for r in records)
            or not formal_start_eligible(records[:4])):
        return False
    formal = records[4:]
    expected_runs = [f"C{case}-{side}-{repeat}" for case in range(1, 7) for side in ("A", "B") for repeat in (1, 2)]
    return (len(formal) == 24 and [r.get("run_id") for r in formal] == expected_runs
            and len({r.get("id") for r in records[2:]}) == 26
            and all(r.get("role") == "formal_run" and r.get("state") == "formal_run_pass"
                    and re.fullmatch(r"[0-9a-f]{64}", r.get("gate_evidence_sha256", "")) for r in formal))


def validate_record_chain(records):
    expected_history = [dict(x, type="historical_attempt") for x in HISTORICAL]
    if type(records) is not list or len(records) > HARD_CAP or records[:2] != expected_history:
        raise LedgerError("historical_reference_mismatch")
    seen = set()
    for index, record in enumerate(records[2:], 3):
        required = {"sequence", "id", "role", "fingerprint", "root_identity", "spec_sha256", "command_sha256",
                    "pid", "pgid", "owner_uid", "started_epoch", "deadline_epoch", "state"}
        optional = {"run_id", "determination", "report_sha256", "gate_evidence_sha256", "ended_epoch"}
        if type(record) is not dict or not required <= set(record) or not set(record) <= required | optional:
            raise LedgerError("ledger_record_schema_invalid")
        if (type(record["sequence"]) is not int or record["sequence"] != index
                or type(record["id"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", record["id"])
                or record["id"] in seen or type(record["role"]) is not str or record["role"] not in {"diagnostic", "final_probe", "formal_run"}
                or type(record["fingerprint"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", record["fingerprint"])
                or type(record["spec_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", record["spec_sha256"])
                or type(record["command_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", record["command_sha256"])):
            raise LedgerError("ledger_record_value_invalid")
        seen.add(record["id"])
        root = record["root_identity"]
        if (type(root) is not dict or set(root) != {"realpath_sha256", "device", "inode"}
                or type(root["realpath_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", root["realpath_sha256"])
                or type(root["device"]) is not int or root["device"] < 0
                or type(root["inode"]) is not int or root["inode"] <= 0):
            raise LedgerError("ledger_record_value_invalid")
        for key in ("pid", "pgid"):
            if type(record[key]) is not int or record[key] <= 0:
                raise LedgerError("ledger_record_value_invalid")
        if type(record["owner_uid"]) is not int or record["owner_uid"] < 0:
            raise LedgerError("ledger_record_value_invalid")
        if (type(record["started_epoch"]) not in (int, float) or type(record["started_epoch"]) is bool
                or type(record["deadline_epoch"]) not in (int, float) or type(record["deadline_epoch"]) is bool
                or record["deadline_epoch"] <= record["started_epoch"]):
            raise LedgerError("ledger_record_value_invalid")
        if type(record["state"]) is not str or record["state"] not in STATES:
            raise LedgerError("ledger_record_value_invalid")
        expected_duration = 240 if record["role"] == "formal_run" else 600
        if record["deadline_epoch"] - record["started_epoch"] != expected_duration:
            raise LedgerError("ledger_record_value_invalid")
        if (record["state"] in {"reserved", "running"}) == ("ended_epoch" in record):
            raise LedgerError("ledger_record_value_invalid")
        if "ended_epoch" in record and (type(record["ended_epoch"]) not in (int, float)
                                        or type(record["ended_epoch"]) is bool
                                        or record["ended_epoch"] < record["started_epoch"]):
            raise LedgerError("ledger_record_value_invalid")
        if "determination" in record and (type(record["determination"]) is not str or record["determination"] not in DETERMINATIONS):
            raise LedgerError("ledger_record_value_invalid")
        if record["role"] == "diagnostic":
            if "run_id" in record or (record["state"] == "completed_diagnostic" and
                    (record.get("determination") != "resolved" or not re.fullmatch(r"[0-9a-f]{64}", record.get("report_sha256", "")))):
                raise LedgerError("ledger_record_value_invalid")
            if record["state"] == "diagnostic_inconclusive" and record.get("determination") != "inconclusive":
                raise LedgerError("ledger_record_value_invalid")
        elif record["role"] == "final_probe":
            if "determination" in record or "report_sha256" in record or "run_id" in record:
                raise LedgerError("ledger_record_value_invalid")
        else:
            if type(record.get("run_id")) is not str or record.get("run_id") not in {f"C{c}-{s}-{n}" for c in range(1, 7) for s in ("A", "B") for n in (1, 2)}:
                raise LedgerError("ledger_record_value_invalid")
        if record["state"] in {"final_pass", "formal_run_pass"}:
            if not re.fullmatch(r"[0-9a-f]{64}", record.get("gate_evidence_sha256", "")):
                raise LedgerError("ledger_record_value_invalid")
        elif "gate_evidence_sha256" in record:
            raise LedgerError("ledger_record_value_invalid")
    return records


def _atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise LedgerError("ledger_directory_mode_invalid")
    temp = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp, path)
    dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


class GlobalLedger:
    """Fingerprint-independent ledger. Remote adapter methods: head, chain, push_ff, ls_remote."""
    def __init__(self, root: Path, remote, *, clock=time.time):
        self.root, self.remote, self.cap, self.clock = Path(root), remote, HARD_CAP, clock
        self.ledger = self.root / "ledger.json"
        self.seal = self.root / "seal.json"
        self.lock = self.root / "global.lock"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_stat = self.root.lstat()
        if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.getuid() or stat.S_IMODE(root_stat.st_mode) != 0o700:
            raise LedgerError("ledger_directory_mode_invalid")

    @staticmethod
    def _read_private(path: Path):
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise LedgerError("local_ledger_file_identity_invalid")
        return strict_json(path.read_bytes())

    def _lock(self):
        fd = os.open(self.lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600 or st.st_uid != os.getuid():
            os.close(fd)
            raise LedgerError("ledger_lock_identity_invalid")
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _read_local(self):
        if not self.ledger.exists() or not self.seal.exists():
            raise LedgerError("local_ledger_or_seal_missing")
        ledger = self._read_private(self.ledger)
        seal = self._read_private(self.seal)
        if (type(ledger) is not dict or set(ledger) != {"schema", "version", "records", "remote_head"}
                or type(ledger["schema"]) is not int or ledger["schema"] != 1
                or type(ledger["version"]) is not int or ledger["version"] != VERSION
                or type(ledger["remote_head"]) is not str or not re.fullmatch(r"[0-9a-f]{40,64}", ledger["remote_head"])
                or type(ledger["records"]) is not list
                or type(seal) is not dict or set(seal) != {"sequence", "chain_sha256", "remote_head"}):
            raise LedgerError("local_ledger_schema_invalid")
        if (type(seal["sequence"]) is not int or type(seal["chain_sha256"]) is not str
                or type(seal["remote_head"]) is not str):
            raise LedgerError("local_ledger_schema_invalid")
        validate_record_chain(ledger["records"])
        digest = sha256(canonical_bytes(ledger["records"]))
        if seal != {"sequence": len(ledger["records"]), "chain_sha256": digest, "remote_head": ledger["remote_head"]}:
            raise LedgerError("local_seal_mismatch")
        return ledger

    def _verify_remote(self, ledger):
        head = self.remote.head()
        if type(head) is not str or not re.fullmatch(r"[0-9a-f]{40,64}", head):
            raise LedgerError("remote_head_missing_or_invalid")
        if self.remote.ls_remote() != head or ledger["remote_head"] != head:
            raise LedgerError("remote_local_head_mismatch")
        chain = self.remote.chain(head)
        validate_record_chain(chain)
        if chain != ledger["records"]:
            raise LedgerError("remote_local_chain_mismatch")
        return head, chain

    def bootstrap(self, seed_payload: bytes):
        fd = self._lock()
        try:
            # A local deletion must never silently become a new bootstrap.
            if (os.path.lexists(self.ledger) or os.path.lexists(self.seal) or self.remote.head() is not None
                    or getattr(self.remote, "seed_commit_pin", None) is not None):
                raise LedgerError("rebootstrap_forbidden")
            parsed, _ = validate_seed_payload(seed_payload)
            records = []
            for src in parsed["records"]:
                records.append({"id": src["id"], "version": src["version"], "fingerprint": src["fingerprint"],
                                "result_sha256": src["result_sha256"], "state": src["state"],
                                "elapsed_seconds": src["elapsed_seconds"], "type": src["type"]})
            payload = canonical_bytes({"schema": 1, "records": records})
            commit = self.remote.push_ff(None, payload)
            if self.remote.ls_remote() != commit:
                raise LedgerError("bootstrap_remote_confirmation_failed")
            self._write_local(records, commit)
            return commit
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _write_local(self, records, head):
        ledger = {"schema": 1, "version": VERSION, "records": records, "remote_head": head}
        _atomic(self.ledger, canonical_bytes(ledger))
        _atomic(self.seal, canonical_bytes({"sequence": len(records), "chain_sha256": sha256(canonical_bytes(records)), "remote_head": head}))

    def reserve(self, *, role: str, fingerprint: str, root_identity: dict, spec_sha256: str, command_sha256: str, run_id: str | None = None):
        if (role not in {"diagnostic", "final_probe", "formal_run"} or type(fingerprint) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                or type(spec_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", spec_sha256)
                or type(command_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", command_sha256)
                or type(root_identity) is not dict or set(root_identity) != {"realpath_sha256", "device", "inode"}
                or type(root_identity["realpath_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", root_identity["realpath_sha256"])
                or type(root_identity["device"]) is not int or root_identity["device"] < 0
                or type(root_identity["inode"]) is not int or root_identity["inode"] <= 0):
            raise LedgerError("reservation_binding_invalid")
        fd = self._lock()
        try:
            ledger = self._read_local()
            head, records = self._verify_remote(ledger)
            if len(records) >= self.cap:
                raise LedgerError("global_budget_exhausted")
            if any(r.get("state") in {"reserved", "running", "unknown", "timeout", "crash", "diagnostic_inconclusive", "final_fail", "formal_run_fail"} for r in records[2:]):
                raise LedgerError("prior_attempt_not_final")
            if records[:2] != [dict(x, type="historical_attempt") for x in HISTORICAL]:
                raise LedgerError("historical_reference_mismatch")
            phase_records = records[2:]
            if role == "diagnostic" and any(r.get("role") == "diagnostic" for r in phase_records):
                raise LedgerError("duplicate_diagnostic_role")
            if role == "final_probe" and (not any(r.get("role") == "diagnostic" and r.get("state") == "completed_diagnostic"
                                                   and r.get("determination") == "resolved" for r in phase_records)
                                           or any(r.get("role") == "final_probe" for r in phase_records)):
                raise LedgerError("final_probe_gate_not_satisfied")
            if role == "formal_run":
                valid_ids = {f"C{c}-{s}-{n}" for c in range(1, 7) for s in ("A", "B") for n in (1, 2)}
                existing_runs = {r.get("run_id") for r in phase_records if r.get("role") == "formal_run"}
                run_order = [f"C{c}-{s}-{n}" for c in range(1, 7) for s in ("A", "B") for n in (1, 2)]
                prior_formal = [r for r in phase_records if r.get("role") == "formal_run"]
                if (run_id not in valid_ids or not formal_start_eligible(records[:4])
                        or any(r.get("role") == "formal_run" and r.get("state") != "formal_run_pass" for r in phase_records)
                        or run_id in existing_runs or len(prior_formal) != run_order.index(run_id)):
                    raise LedgerError("formal_gate_not_satisfied")
            elif run_id is not None:
                raise LedgerError("reservation_binding_invalid")
            now = self.clock()
            formal_entries = [r for r in records[2:] if r.get("role") == "formal_run"]
            if role == "formal_run" and formal_entries and now - formal_entries[0].get("started_epoch", now) >= FORMAL_SECONDS:
                raise LedgerError("formal_wall_budget_exhausted")
            record = {"sequence": len(records) + 1, "id": uuid.uuid4().hex, "role": role,
                      "fingerprint": fingerprint, "root_identity": root_identity,
                      "spec_sha256": spec_sha256, "command_sha256": command_sha256,
                      "pid": os.getpid(), "pgid": os.getpgrp(), "owner_uid": os.getuid(),
                      "started_epoch": now, "deadline_epoch": now + (600 if role in {"diagnostic", "final_probe"} else 240),
                      "state": "reserved"}
            if run_id is not None:
                record["run_id"] = run_id
            commit = self.remote.push_ff(head, canonical_bytes({"schema": 1, "version": VERSION, "records": records + [record]}))
            if self.remote.ls_remote() != commit:
                raise LedgerError("remote_reservation_confirmation_failed")
            # The remote reservation consumes the slot even if this local write fails.
            self._write_local(records + [record], commit)
            return record
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def complete(self, attempt_id: str, state: str, *, determination: str | None = None,
                 run_id: str | None = None, diagnostic_report: bytes | None = None,
                 gate_evidence: dict | None = None):
        if state not in STATES - {"reserved", "running"}:
            raise LedgerError("attempt_state_invalid")
        fd = self._lock()
        try:
            ledger = self._read_local()
            head, records = self._verify_remote(ledger)
            matches = [r for r in records[2:] if r.get("id") == attempt_id]
            if len(matches) != 1 or matches[0].get("state") not in {"reserved", "running"}:
                raise LedgerError("attempt_transition_invalid")
            record = matches[0]
            role_state = {"diagnostic": {"completed_diagnostic", "diagnostic_inconclusive", "unknown", "timeout", "crash"},
                          "final_probe": {"final_pass", "final_fail", "unknown", "timeout", "crash"},
                          "formal_run": {"formal_run_pass", "formal_run_fail", "unknown", "timeout", "crash"}}
            if state not in role_state.get(record.get("role"), set()):
                raise LedgerError("attempt_transition_invalid")
            if record["role"] == "diagnostic" and state == "completed_diagnostic":
                if type(diagnostic_report) is not bytes:
                    raise LedgerError("diagnostic_report_required")
                parsed = strict_json(diagnostic_report)
                validate_report(parsed, attempt_id=attempt_id, fingerprint=record["fingerprint"])
                if parsed["determination"] != "resolved":
                    raise LedgerError("attempt_transition_invalid")
                record["report_sha256"] = sha256(diagnostic_report)
                determination = parsed["determination"]
            elif diagnostic_report is not None:
                raise LedgerError("attempt_transition_invalid")
            if state == "diagnostic_inconclusive" and determination != "inconclusive":
                raise LedgerError("attempt_transition_invalid")
            if state in {"final_pass", "formal_run_pass"}:
                expected_gates = {"env", "runtime", "binding", "event", "scope", "residual", "cli"}
                if (type(gate_evidence) is not dict or set(gate_evidence) != expected_gates
                        or any(type(value) is not bool or value is not True for value in gate_evidence.values())):
                    raise LedgerError("pass_gate_evidence_invalid")
                record["gate_evidence_sha256"] = sha256(canonical_bytes(gate_evidence))
            elif gate_evidence is not None:
                raise LedgerError("attempt_transition_invalid")
            record["state"] = state
            if determination is not None:
                if determination not in DETERMINATIONS or record.get("role") != "diagnostic":
                    raise LedgerError("attempt_transition_invalid")
                record["determination"] = determination
            if run_id is not None:
                if record.get("role") != "formal_run" or run_id not in {f"C{c}-{s}-{n}" for c in range(1, 7) for s in ("A", "B") for n in (1, 2)}:
                    raise LedgerError("attempt_transition_invalid")
                record["run_id"] = run_id
            ended = self.clock()
            if ended > record["deadline_epoch"]:
                state = "timeout"
            record["state"] = state
            record["ended_epoch"] = ended
            payload = canonical_bytes({"schema": 1, "version": VERSION, "records": records})
            commit = self.remote.push_ff(head, payload)
            if self.remote.ls_remote() != commit:
                raise LedgerError("remote_reservation_confirmation_failed")
            self._write_local(records, commit)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def formal_gate(self, expected_fingerprint: str):
        ledger = self._read_local()
        self._verify_remote(ledger)
        if not formal_start_eligible(ledger["records"]) or ledger["records"][3].get("fingerprint") != expected_fingerprint:
            raise LedgerError("formal_gate_not_satisfied")
        return True


class GitRemote:
    """Append-only Git remote adapter. Never force-pushes, deletes, or resets the ref."""
    def __init__(self, repo: Path, *, remote="origin", ref=REMOTE_REF, seed_commit_pin: str | None = None):
        if seed_commit_pin is not None and not re.fullmatch(r"[0-9a-f]{40,64}", seed_commit_pin):
            raise LedgerError("seed_commit_pin_invalid")
        if ref != REMOTE_REF or remote != "origin":
            raise LedgerError("remote_target_not_fixed")
        self.repo, self.remote, self.ref = Path(repo), remote, ref
        self.seed_commit_pin = seed_commit_pin

    def _git(self, args, *, data=None, check=True):
        try:
            result = subprocess.run(["git", "-C", str(self.repo), *args], input=data,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise LedgerError("remote_git_operation_failed") from None
        if check and result.returncode != 0:
            raise LedgerError("remote_git_operation_failed")
        return result

    def ls_remote(self):
        result = self._git(["ls-remote", "--refs", self.remote, self.ref])
        lines = result.stdout.decode("ascii", "strict").splitlines()
        if result.stderr or len(lines) > 1:
            raise LedgerError("remote_ls_remote_invalid")
        if not lines:
            return None
        fields = lines[0].split("\t")
        if len(fields) != 2 or fields[1] != self.ref or not re.fullmatch(r"[0-9a-f]{40,64}", fields[0]):
            raise LedgerError("remote_ls_remote_invalid")
        return fields[0]

    def head(self):
        return self.ls_remote()

    def chain(self, head):
        if self.seed_commit_pin is None:
            raise LedgerError("seed_commit_pin_missing")
        if self.ls_remote() != head:
            raise LedgerError("remote_head_changed")
        self._git(["fetch", "--no-tags", self.remote, self.ref])
        result = self._git(["show", f"{head}:ledger.json"])
        parsed = strict_json(result.stdout)
        if type(parsed) is not dict or set(parsed) not in ({"schema", "records"}, {"schema", "version", "records"}):
            raise LedgerError("remote_chain_schema_invalid")
        if (type(parsed["schema"]) is not int or parsed["schema"] != 1
                or ("version" in parsed and parsed["version"] != VERSION) or type(parsed["records"]) is not list):
            raise LedgerError("remote_chain_schema_invalid")
        validate_record_chain(parsed["records"])
        self._git(["merge-base", "--is-ancestor", self.seed_commit_pin, head])
        return parsed["records"]

    def push_ff(self, parent, payload):
        if (parent is None and self.seed_commit_pin is not None) or (parent is not None and self.seed_commit_pin is None):
            raise LedgerError("seed_commit_pin_missing" if parent is not None else "rebootstrap_forbidden")
        current = self.ls_remote()
        if current != parent:
            raise LedgerError("remote_head_changed")
        if parent is not None:
            self._git(["merge-base", "--is-ancestor", self.seed_commit_pin, parent])
        parsed = strict_json(payload)
        valid_seed = (parent is None and type(parsed) is dict and set(parsed) == {"schema", "records"}
                      and type(parsed.get("schema")) is int and parsed.get("schema") == 1)
        valid_next = (type(parsed) is dict and set(parsed) == {"schema", "version", "records"}
                      and type(parsed.get("schema")) is int and parsed.get("schema") == 1
                      and type(parsed.get("version")) is int and parsed.get("version") == VERSION)
        if not (valid_seed or valid_next) or type(parsed.get("records")) is not list:
            raise LedgerError("remote_chain_schema_invalid")
        validate_record_chain(parsed["records"])
        blob = self._git(["hash-object", "-w", "--stdin"], data=canonical_bytes(parsed)).stdout.decode("ascii").strip()
        tree_in = f"100644 blob {blob}\tledger.json\n".encode("ascii")
        tree = self._git(["mktree"], data=tree_in).stdout.decode("ascii").strip()
        args = ["commit-tree", tree]
        if parent is not None:
            args += ["-p", parent]
        commit = self._git(args + ["-m", "P5 budget reservation metadata"]).stdout.decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise LedgerError("remote_commit_creation_failed")
        # Ordinary fast-forward push only. Never force, delete, retry, or rebase.
        self._git(["push", self.remote, f"{commit}:{self.ref}"])
        if self.ls_remote() != commit:
            raise LedgerError("remote_push_confirmation_failed")
        return commit


def fixed_error(error: Exception) -> str:
    """Map any exception to an allowlisted code; never persist exception text."""
    code = str(error) if isinstance(error, LedgerError) else "internal_error"
    allowed = {"duplicate_json_key", "invalid_json_number", "invalid_json", "seed_digest_mismatch",
               "seed_schema_invalid", "seed_history_mismatch", "diagnostic_schema_invalid", "diagnostic_binding_mismatch",
               "diagnostic_enum_invalid", "diagnostic_path_schema_invalid", "diagnostic_path_value_invalid",
               "diagnostic_unknown_schema_invalid", "diagnostic_unknown_value_invalid", "diagnostic_unknown_count_inconsistent",
               "diagnostic_unknown_class_inconsistent", "diagnostic_path_inconsistent", "diagnostic_determination_inconsistent",
               "remote_head_missing_or_invalid", "remote_local_head_mismatch", "remote_local_chain_mismatch",
               "local_ledger_or_seal_missing", "local_ledger_schema_invalid", "local_seal_mismatch", "rebootstrap_forbidden",
               "global_budget_exhausted", "prior_attempt_not_final", "historical_reference_mismatch", "formal_gate_not_satisfied",
               "remote_reservation_confirmation_failed", "bootstrap_remote_confirmation_failed", "reservation_binding_invalid",
               "ledger_directory_mode_invalid", "ledger_lock_identity_invalid", "unknown_key_inventory_invalid",
               "diagnostic_inconclusive", "attempt_state_invalid", "attempt_transition_invalid", "duplicate_diagnostic_role",
               "final_probe_gate_not_satisfied", "diagnostic_report_required", "pass_gate_evidence_invalid",
               "local_ledger_file_identity_invalid", "remote_chain_schema_invalid", "remote_commit_creation_failed",
               "remote_git_operation_failed", "remote_head_changed", "remote_ls_remote_invalid", "remote_push_confirmation_failed",
               "remote_target_not_fixed", "seed_commit_pin_invalid", "seed_commit_pin_missing",
               "attempt_state_invalid", "attempt_transition_invalid", "diagnostic_report_required",
               "pass_gate_evidence_invalid", "formal_wall_budget_exhausted", "remote_ls_remote_invalid",
               "remote_head_changed", "remote_push_confirmation_failed", "diagnostic_schema_invalid",
               "diagnostic_path_value_invalid", "diagnostic_unknown_value_invalid", "diagnostic_report_required",
               "invocation_timeout", "artifact_bundle_input_invalid", "artifact_bundle_schema_invalid",
               "artifact_directory_identity_invalid", "ledger_record_schema_invalid", "ledger_record_value_invalid",
               "diagnostic_environment_fit_inconsistent"}
    return code if code in allowed else "internal_error"
