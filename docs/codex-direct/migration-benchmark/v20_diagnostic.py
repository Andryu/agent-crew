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
import signal
import stat
import subprocess
import tempfile
import time
import uuid
import shutil
import shlex
import pwd
import sys

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
SEED_SHA256 = _hex("f5cb", "2275", "c0b4", "c397", "e76d", "ea47", "3809", "c8e5", "6da7", "a3f0", "f7ac", "eb1c", "0cdf", "e277", "cdd9", "79c8")
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


# The profile grants broad reads/process execution, but file writes only below the
# per-attempt private directory. Outbound networking is needed by the fixed
# OpenAI-direct CLI; the nested Codex tool sandbox remains read-only.
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
SANDBOX_PROFILE_TEMPLATE = '(version 1)\n(deny default)\n(allow process*)\n(allow file-read*)\n(allow sysctl-read)\n(allow network-outbound)\n(allow file-write* (subpath "{directory}"))\n'
SANDBOX_PROFILE_SHA256 = sha256(SANDBOX_PROFILE_TEMPLATE.encode("utf-8"))
BINDING_SPEC_SHA256 = sha256(b"P5-v20-phase-binding-v1:manifest-config-source-command-preflight-root")
_BINDING_VERIFIED_ARTIFACT = None


def sandboxed_argv(argv, sandbox_directory: Path):
    """Build an OS-enforced command; absence/profile drift is a pre-launch failure."""
    executable = Path(SANDBOX_EXEC)
    try:
        info = executable.lstat()
        if (not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111
                or executable.resolve(strict=True) != executable):
            raise LedgerError("host_containment_unavailable")
        sandbox = Path(sandbox_directory).resolve(strict=True)
        if not sandbox.is_dir() or sandbox.stat().st_uid != os.getuid():
            raise LedgerError("host_containment_unavailable")
        if '"' in str(sandbox):
            raise LedgerError("host_containment_profile_mismatch")
        rendered = SANDBOX_PROFILE_TEMPLATE.format(directory=str(sandbox))
        # Refuse profile drift and non-absolute child commands before creating a process.
        if sha256(SANDBOX_PROFILE_TEMPLATE.encode("utf-8")) != SANDBOX_PROFILE_SHA256:
            raise LedgerError("host_containment_profile_mismatch")
        if type(argv) not in (tuple, list) or not argv or not os.path.isabs(argv[0]):
            raise LedgerError("fixed_cli_binding_invalid")
        # sandbox-exec can exist yet be disabled by the host's outer sandbox.
        # The exact profile is an argv value (-p), not an unbound temporary file.
        # Check the profile with a harmless fixed utility before any target starts.
        probe = subprocess.run([SANDBOX_EXEC, "-p", rendered, "/usr/bin/true"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=5, close_fds=True)
        if probe.returncode != 0 or probe.stdout or probe.stderr:
            raise LedgerError("host_containment_unavailable")
        return [SANDBOX_EXEC, "-p", rendered, *argv]
    except LedgerError:
        raise
    except Exception:
        raise LedgerError("host_containment_unavailable") from None


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
    records = parsed["records"]
    record_fields = {"elapsed_seconds", "fingerprint", "id", "result_sha256", "state", "type", "version"}
    if (type(records) is not list or len(records) != 2
            or any(type(record) is not dict or set(record) != record_fields for record in records)
            or any(type(record["elapsed_seconds"]) is not float or type(record["version"]) is not int for record in records)
            or records != expected or [record["id"] for record in records] != sorted(record["id"] for record in records)
            or payload != canonical_bytes(parsed)):
        raise LedgerError("seed_history_mismatch")
    return {"schema": 1, "records": expected}, digest


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
    if (type(report["attempt_id"]) is not str or not re.fullmatch(r"[0-9a-f]{32}", report["attempt_id"])
            or type(report["fingerprint"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", report["fingerprint"])
            or type(attempt_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", attempt_id)
            or type(fingerprint) is not str or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
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
    if p["unapproved_component_count"] > p["component_count"]:
        raise LedgerError("diagnostic_inconclusive")
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


def report_for_storage(report: dict, *, attempt_id: str, fingerprint: str, binding_sha256: str) -> bytes:
    """Rebuild from schema allowlist; input maps/raw exceptions never reach storage."""
    if type(binding_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", binding_sha256):
        raise LedgerError("diagnostic_binding_mismatch")
    validated = validate_report(report, attempt_id=attempt_id, fingerprint=fingerprint)
    return canonical_bytes({key: validated[key] for key in
                            ("schema", "attempt_id", "fingerprint", "environment_fit", "path", "unknown_keys", "determination")})


ARTIFACT_NAMES = frozenset({"stdout.txt", "stderr.txt", "answer.json", "raw.jsonl", "temporary.spool",
                            "result.json", "summary.json", "audit.json", "diagnostic.json", "public.md", "error.json"})


def artifact_bundle(*, trusted_attempt_id: str, trusted_fingerprint: str, trusted_binding_sha256: str,
                    report_bytes: bytes | None = None, error: Exception | None = None) -> dict[str, bytes]:
    """Construct complete output set solely from fixed schema or stable error enum."""
    if (report_bytes is None) == (error is None):
        raise LedgerError("artifact_bundle_input_invalid")
    if (type(trusted_attempt_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", trusted_attempt_id)
            or type(trusted_fingerprint) is not str or not re.fullmatch(r"[0-9a-f]{64}", trusted_fingerprint)
            or type(trusted_binding_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", trusted_binding_sha256)):
        raise LedgerError("artifact_trusted_binding_invalid")
    bundle = {name: b"" for name in ARTIFACT_NAMES}
    if report_bytes is not None:
        report = strict_json(report_bytes)
        safe = report_for_storage(report, attempt_id=trusted_attempt_id, fingerprint=trusted_fingerprint,
                                  binding_sha256=trusted_binding_sha256)
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


def save_artifact_bundle(directory: Path, bundle: dict[str, bytes], *, trusted_attempt_id: str,
                         trusted_fingerprint: str, trusted_binding_sha256: str):
    directory = Path(directory)
    if type(bundle) is not dict or set(bundle) != ARTIFACT_NAMES or any(type(v) is not bytes for v in bundle.values()):
        raise LedgerError("artifact_bundle_schema_invalid")
    if bundle["result.json"]:
        expected = artifact_bundle(report_bytes=bundle["result.json"], trusted_attempt_id=trusted_attempt_id,
                                   trusted_fingerprint=trusted_fingerprint, trusted_binding_sha256=trusted_binding_sha256)
        if expected != bundle:
            raise LedgerError("artifact_bundle_schema_invalid")
    elif bundle["error.json"]:
        error_obj = strict_json(bundle["error.json"])
        if type(error_obj) is not dict or set(error_obj) != {"error"} or type(error_obj["error"]) is not str:
            raise LedgerError("artifact_bundle_schema_invalid")
        expected = artifact_bundle(error=LedgerError(error_obj["error"]), trusted_attempt_id=trusted_attempt_id,
                                   trusted_fingerprint=trusted_fingerprint, trusted_binding_sha256=trusted_binding_sha256)
        if expected != bundle:
            raise LedgerError("artifact_bundle_schema_invalid")
    else:
        raise LedgerError("artifact_bundle_schema_invalid")
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise LedgerError("artifact_directory_identity_invalid")
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


EVIDENCE_SCHEMA = 1
GATE_NAMES = frozenset({"env", "runtime", "binding", "event", "scope", "residual", "cli"})


def _private_file_identity(path: Path):
    path = Path(path)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600):
        raise LedgerError("artifact_identity_invalid")
    data = path.read_bytes(); after = path.lstat()
    attrs = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_uid")
    if len(data) != before.st_size or any(getattr(before, x) != getattr(after, x) for x in attrs):
        raise LedgerError("artifact_identity_invalid")
    return {"absolute_path": str(path.absolute()), "realpath": str(path.resolve(strict=True)),
            "device": before.st_dev, "inode": before.st_ino, "owner": before.st_uid,
            "mode": stat.S_IMODE(before.st_mode), "size": before.st_size, "sha256": sha256(data)}, data


def save_verified_result(directory: Path, *, attempt_id: str, role: str, run_id: str | None,
                         binding: dict, result_bytes: bytes):
    """Persist only strict allowlisted result bytes and trusted reservation metadata."""
    binding = validate_binding(binding)
    if (type(attempt_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", attempt_id)
            or role not in {"diagnostic", "final_probe", "formal_run"}
            or (role == "formal_run") != (run_id is not None)):
        raise LedgerError("artifact_trusted_binding_invalid")
    parsed = strict_json(result_bytes)
    if role == "diagnostic":
        validate_report(parsed, attempt_id=attempt_id, fingerprint=binding["fingerprint"])
        safe = report_for_storage(parsed, attempt_id=attempt_id, fingerprint=binding["fingerprint"],
                                  binding_sha256=binding_digest(binding))
        gates = {}
    else:
        fields = {"schema", "attempt_id", "role", "run_id", "fingerprint", "gates"}
        if (type(parsed) is not dict or set(parsed) != fields or type(parsed["schema"]) is not int
                or parsed["schema"] != EVIDENCE_SCHEMA or parsed["attempt_id"] != attempt_id
                or parsed["role"] != role or parsed["run_id"] != run_id
                or parsed["fingerprint"] != binding["fingerprint"] or type(parsed["gates"]) is not dict
                or set(parsed["gates"]) != GATE_NAMES or any(type(x) is not bool for x in parsed["gates"].values())):
            raise LedgerError("pass_gate_evidence_invalid")
        safe, gates = canonical_bytes(parsed), parsed["gates"]
    directory = Path(directory); directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise LedgerError("artifact_directory_identity_invalid")
    result_path = directory / "result.json"
    fd = os.open(result_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(safe); stream.flush(); os.fsync(stream.fileno())
    artifact_identity, _ = _private_file_identity(result_path)
    evidence = {"schema": EVIDENCE_SCHEMA, "attempt_id": attempt_id, "role": role, "run_id": run_id,
                "binding_sha256": binding_digest(binding), "fingerprint": binding["fingerprint"],
                "artifact": artifact_identity, "gate_schema": EVIDENCE_SCHEMA, "gate_results": gates}
    sidecar_path = directory / "evidence.json"
    fd = os.open(sidecar_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical_bytes(evidence)); stream.flush(); os.fsync(stream.fileno())
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return result_path, sidecar_path


def verify_saved_result(result_path: Path, sidecar_path: Path, *, record: dict, binding: dict):
    artifact, data = _private_file_identity(result_path)
    _, sidebytes = _private_file_identity(sidecar_path)
    side = strict_json(sidebytes)
    fields = {"schema", "attempt_id", "role", "run_id", "binding_sha256", "fingerprint",
              "artifact", "gate_schema", "gate_results"}
    if (type(side) is not dict or set(side) != fields or type(side["schema"]) is not int
            or side["schema"] != EVIDENCE_SCHEMA or type(side["gate_schema"]) is not int
            or side["gate_schema"] != EVIDENCE_SCHEMA or side["artifact"] != artifact
            or side["attempt_id"] != record["id"] or side["role"] != record["role"]
            or side["run_id"] != record.get("run_id") or side["fingerprint"] != record["fingerprint"]
            or side["binding_sha256"] != record["binding_sha256"]
            or side["binding_sha256"] != binding_digest(binding)):
        raise LedgerError("pass_gate_evidence_invalid")
    result = strict_json(data)
    if record["role"] == "diagnostic":
        validate_report(result, attempt_id=record["id"], fingerprint=record["fingerprint"])
        return sha256(data), result["determination"], {}
    if (type(result) is not dict or set(result) != {"schema", "attempt_id", "role", "run_id", "fingerprint", "gates"}
            or type(result["schema"]) is not int or result["schema"] != EVIDENCE_SCHEMA
            or result["attempt_id"] != record["id"] or result["role"] != record["role"]
            or result["run_id"] != record.get("run_id") or result["fingerprint"] != record["fingerprint"]
            or type(result["gates"]) is not dict or set(result["gates"]) != GATE_NAMES
            or side["gate_results"] != result["gates"]
            or any(type(x) is not bool for x in result["gates"].values())):
        raise LedgerError("pass_gate_evidence_invalid")
    return sha256(data), None, result["gates"]


def formal_start_eligible(records: list[dict]) -> bool:
    """Gate formal start on fixed history, exactly one resolved diagnostic and one PASS final."""
    if type(records) is not list or len(records) != 4 or any(type(r) is not dict for r in records):
        return False
    try:
        validate_record_chain(records)
    except LedgerError:
        return False
    expected_history = [dict(x, type="historical_attempt") for x in HISTORICAL]
    if records[:2] != expected_history:
        return False
    diagnostic = [r for r in records[2:] if r.get("role") == "diagnostic"]
    final = [r for r in records[2:] if r.get("role") == "final_probe"]
    if len(diagnostic) != 1 or len(final) != 1:
        return False
    try:
        diagnostic_next = validate_binding(diagnostic[0].get("expected_next_binding"))
        final_next = validate_binding(final[0].get("expected_next_binding"))
    except LedgerError:
        return False
    expected_run_set = sha256(canonical_bytes([f"C{c}-{side}-{n}" for c in range(1, 7)
                                                for side in ("A", "B") for n in (1, 2)]))
    return (diagnostic[0].get("expected_next_role") == "final_probe"
            and diagnostic[0].get("expected_next_binding_sha256") == binding_digest(diagnostic_next)
            and diagnostic_next == final[0].get("binding")
            and final[0].get("expected_next_role") == "formal_run"
            and final[0].get("expected_next_binding_sha256") == binding_digest(final_next)
            and final[0].get("expected_next_run_set_sha256") == expected_run_set
            and diagnostic[0].get("state") == "completed_diagnostic"
            and diagnostic[0].get("determination") == "resolved"
            and re.fullmatch(r"[0-9a-f]{64}", diagnostic[0].get("report_sha256", ""))
            and final[0].get("state") == "final_pass"
            and re.fullmatch(r"[0-9a-f]{64}", final[0].get("gate_evidence_sha256", ""))
            and all(r.get("role") in {"diagnostic", "final_probe", "formal_run"} for r in records[2:]))


def formal_complete(records: list[dict]) -> bool:
    if (type(records) is not list or len(records) != HARD_CAP or any(type(r) is not dict for r in records)
            or not formal_start_eligible(records[:4])):
        return False
    try:
        validate_record_chain(records)
    except LedgerError:
        return False
    formal = records[4:]
    expected_runs = [f"C{case}-{side}-{repeat}" for case in range(1, 7) for side in ("A", "B") for repeat in (1, 2)]
    return (len(formal) == 24 and [r.get("run_id") for r in formal] == expected_runs
            and len({r.get("id") for r in records[2:]}) == 26
            and all(r.get("role") == "formal_run" and r.get("state") == "formal_run_pass"
                    and re.fullmatch(r"[0-9a-f]{64}", r.get("gate_evidence_sha256", "")) for r in formal))


def validate_binding(binding):
    fields = {"fingerprint", "root_identity", "artifact_root", "preflight_path", "manifest_identity",
              "spec_sha256", "command_sha256", "preflight_sha256", "manifest_sha256"}
    if type(binding) is not dict or set(binding) != fields:
        raise LedgerError("reservation_binding_invalid")
    if (type(binding["fingerprint"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", binding["fingerprint"])
            or type(binding["artifact_root"]) is not str or not os.path.isabs(binding["artifact_root"])
            or os.path.realpath(binding["artifact_root"]) != binding["artifact_root"]
            or type(binding["preflight_path"]) is not str or not os.path.isabs(binding["preflight_path"])
            or os.path.realpath(binding["preflight_path"]) != binding["preflight_path"]
            or any(type(binding[k]) is not str or not re.fullmatch(r"[0-9a-f]{64}", binding[k])
                   for k in ("spec_sha256", "command_sha256", "preflight_sha256", "manifest_sha256"))):
        raise LedgerError("reservation_binding_invalid")
    root = binding["root_identity"]
    if (type(root) is not dict or set(root) != {"realpath", "device", "inode"}
            or type(root["realpath"]) is not str or not os.path.isabs(root["realpath"])
            or os.path.realpath(root["realpath"]) != root["realpath"]
            or type(root["device"]) is not int or root["device"] < 0
            or type(root["inode"]) is not int or root["inode"] <= 0):
        raise LedgerError("reservation_binding_invalid")
    try:
        run_root = Path(root["realpath"])
        run_info = run_root.lstat()
        if (not stat.S_ISDIR(run_info.st_mode) or run_info.st_uid != os.getuid()
                or run_info.st_dev != root["device"] or run_info.st_ino != root["inode"]
                or run_root.resolve(strict=True) != run_root):
            raise LedgerError("reservation_binding_invalid")
        preflight_path = Path(binding["preflight_path"])
        if preflight_path.parent != run_root:
            raise LedgerError("reservation_binding_invalid")
        preflight_info = preflight_path.lstat(); preflight_bytes = preflight_path.read_bytes()
        if (not stat.S_ISREG(preflight_info.st_mode) or preflight_info.st_uid != os.getuid()
                or stat.S_IMODE(preflight_info.st_mode) != 0o400
                or sha256(preflight_bytes) != binding["preflight_sha256"]):
            raise LedgerError("reservation_binding_invalid")
        artifact_root = Path(binding["artifact_root"])
        artifact_info = artifact_root.lstat()
        if (not stat.S_ISDIR(artifact_info.st_mode) or artifact_info.st_uid != os.getuid()
                or stat.S_IMODE(artifact_info.st_mode) != 0o500 or artifact_root.resolve(strict=True) != artifact_root):
            raise LedgerError("reservation_binding_invalid")
        # This path is the immutable source currently executing. Its driver validates
        # all nested identities, source/config hashes and the bundle fingerprint.
        if artifact_root != Path(__file__).resolve(strict=True).parent:
            raise LedgerError("reservation_binding_invalid")
        if str(artifact_root) not in __import__("sys").path:
            __import__("sys").path.insert(0, str(artifact_root))
        import v20_driver
        global _BINDING_VERIFIED_ARTIFACT
        if _BINDING_VERIFIED_ARTIFACT is None:
            _BINDING_VERIFIED_ARTIFACT = v20_driver.load_manifest(verify_cli=False)
        verified_root, verified_manifest = _BINDING_VERIFIED_ARTIFACT
        if verified_root != artifact_root:
            raise LedgerError("reservation_binding_invalid")
        for name, expected in verified_manifest["files"].items():
            if v20_driver.file_binding(artifact_root / name) != expected:
                raise LedgerError("reservation_binding_invalid")
        manifest_path = artifact_root / "manifest.json"
        manifest_before = manifest_path.lstat()
        manifest_bytes = manifest_path.read_bytes()
        manifest_info = manifest_path.lstat()
        stable_attrs = ("st_dev", "st_ino", "st_uid", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (len(manifest_bytes) != manifest_before.st_size
                or any(getattr(manifest_before, name) != getattr(manifest_info, name) for name in stable_attrs)):
            raise LedgerError("reservation_binding_invalid")
        expected_manifest_identity = {"absolute_path": str(manifest_path.absolute()),
            "realpath": str(manifest_path.resolve(strict=True)), "device": manifest_info.st_dev,
            "inode": manifest_info.st_ino, "owner": manifest_info.st_uid,
            "mode": stat.S_IMODE(manifest_info.st_mode)}
        expected_keys = set(expected_manifest_identity)
        if (type(binding["manifest_identity"]) is not dict or set(binding["manifest_identity"]) != expected_keys
                or binding["manifest_identity"] != expected_manifest_identity
                or not stat.S_ISREG(manifest_info.st_mode) or manifest_info.st_nlink != 1
                or manifest_info.st_uid != os.getuid() or stat.S_IMODE(manifest_info.st_mode) != 0o400):
            raise LedgerError("reservation_binding_invalid")
        if sha256(manifest_bytes) != binding["manifest_sha256"]:
            raise LedgerError("reservation_binding_invalid")
        manifest = strict_json(manifest_bytes)
        config = strict_json((artifact_root / "config.json").read_bytes())
        if (type(config) is not dict or config.get("binding_spec_sha256") != binding["spec_sha256"]
                or config.get("command_sha256") != binding["command_sha256"]):
            raise LedgerError("reservation_binding_invalid")
        preflight = strict_json(preflight_bytes)
        preflight_fields = {"schema", "version", "fingerprint", "manifest_sha256", "files", "runtime_bindings",
                            "selftest_counts", "model_calls", "probe_attempts", "formal_runs", "result"}
        if (type(preflight) is not dict or set(preflight) != preflight_fields
                or type(preflight["schema"]) is not int or preflight["schema"] != 1
                or type(preflight["version"]) is not int or preflight["version"] != VERSION
                or preflight["fingerprint"] != manifest["fingerprint"]
                or preflight["manifest_sha256"] != binding["manifest_sha256"]
                or preflight["files"] != manifest["files"]
                or type(preflight["runtime_bindings"]) is not dict
                or type(preflight["selftest_counts"]) is not dict
                or any(type(preflight[k]) is not int or preflight[k] != 0 for k in ("model_calls", "probe_attempts", "formal_runs"))
                or preflight["result"] != "pass"):
            raise LedgerError("reservation_binding_invalid")
        phase_fp = sha256(canonical_bytes({"artifact_fingerprint": manifest["fingerprint"],
            "root_identity": root, "spec_sha256": binding["spec_sha256"],
            "command_sha256": binding["command_sha256"], "preflight_sha256": binding["preflight_sha256"]}))
        if binding["fingerprint"] != phase_fp:
            raise LedgerError("reservation_binding_invalid")
    except LedgerError:
        raise
    except Exception:
        raise LedgerError("reservation_binding_invalid") from None
    return binding


def binding_digest(binding):
    return sha256(canonical_bytes(validate_binding(binding)))


def gate_evidence_digest(*, attempt_id, binding_sha256, result_artifact_sha256, evidence, run_id=None):
    if (type(attempt_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", attempt_id)
            or type(binding_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", binding_sha256)
            or type(result_artifact_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", result_artifact_sha256)
            or type(evidence) is not dict):
        raise LedgerError("pass_gate_evidence_invalid")
    payload = {"attempt_id": attempt_id, "binding_sha256": binding_sha256,
               "result_artifact_sha256": result_artifact_sha256, "gate_schema": 1, "evidence": evidence}
    if run_id is not None:
        payload["run_id"] = run_id
    return sha256(canonical_bytes(payload))


def validate_record_chain(records):
    expected_history = [dict(x, type="historical_attempt") for x in HISTORICAL]
    if type(records) is not list or len(records) > HARD_CAP or records[:2] != expected_history:
        raise LedgerError("historical_reference_mismatch")
    seen = set()
    for index, record in enumerate(records[2:], 3):
        required = {"sequence", "id", "role", "fingerprint", "root_identity", "spec_sha256", "command_sha256",
                    "preflight_sha256", "manifest_sha256", "binding", "binding_sha256",
                    "pid", "pgid", "owner_uid", "started_epoch", "deadline_epoch", "state"}
        optional = {"run_id", "determination", "report_sha256", "gate_evidence_sha256", "ended_epoch",
                    "result_artifact_sha256", "gate_schema", "run_set_sha256", "gate_evidence",
                    "expected_next_role", "expected_next_binding", "expected_next_binding_sha256",
                    "expected_next_run_set_sha256"}
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
        binding = validate_binding(record["binding"])
        digest = binding_digest(binding)
        if (binding["fingerprint"] != record["fingerprint"] or root != binding["root_identity"]
                or record["spec_sha256"] != binding["spec_sha256"]
                or record["command_sha256"] != binding["command_sha256"]
                or record["preflight_sha256"] != binding["preflight_sha256"]
                or record["manifest_sha256"] != binding["manifest_sha256"]
                or record["binding_sha256"] != digest):
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
                    (record.get("determination") != "resolved" or not re.fullmatch(r"[0-9a-f]{64}", record.get("report_sha256", ""))
                     or record.get("report_sha256") != record.get("result_artifact_sha256"))):
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
            evidence = record.get("gate_evidence")
            expected_gate_fields = {"env", "runtime", "binding", "event", "scope", "residual", "cli"}
            if (not re.fullmatch(r"[0-9a-f]{64}", record.get("gate_evidence_sha256", ""))
                    or not re.fullmatch(r"[0-9a-f]{64}", record.get("result_artifact_sha256", ""))
                    or type(record.get("gate_schema")) is not int or record["gate_schema"] != 1
                    or type(evidence) is not dict or set(evidence) != expected_gate_fields
                    or any(type(v) is not bool or v is not True for v in evidence.values())
                    or record["gate_evidence_sha256"] != gate_evidence_digest(
                        attempt_id=record["id"], binding_sha256=record["binding_sha256"],
                        result_artifact_sha256=record["result_artifact_sha256"], evidence=evidence,
                        run_id=record.get("run_id"))):
                raise LedgerError("ledger_record_value_invalid")
        elif any(k in record for k in ("gate_evidence_sha256", "gate_schema", "gate_evidence")) or (
                "result_artifact_sha256" in record and not (record["role"] == "diagnostic"
                and record["state"] == "completed_diagnostic" and record.get("report_sha256") == record["result_artifact_sha256"])):
            raise LedgerError("ledger_record_value_invalid")
        if record["role"] == "formal_run" and (type(record.get("run_set_sha256")) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", record["run_set_sha256"])):
            raise LedgerError("ledger_record_value_invalid")
        if record["role"] != "formal_run" and "run_set_sha256" in record:
            raise LedgerError("ledger_record_value_invalid")
        expected_next = any(k in record for k in ("expected_next_role", "expected_next_binding",
                                                    "expected_next_binding_sha256", "expected_next_run_set_sha256"))
        if record["role"] == "diagnostic" and record["state"] == "completed_diagnostic":
            next_binding = validate_binding(record.get("expected_next_binding"))
            if (record.get("expected_next_role") != "final_probe"
                    or record.get("expected_next_binding_sha256") != binding_digest(next_binding)
                    or next_binding["fingerprint"] == record["fingerprint"]):
                raise LedgerError("ledger_expected_binding_invalid")
        elif record["role"] == "final_probe" and record["state"] == "final_pass":
            next_binding = validate_binding(record.get("expected_next_binding"))
            expected_runs = [f"C{c}-{side}-{n}" for c in range(1, 7) for side in ("A", "B") for n in (1, 2)]
            if (record.get("expected_next_role") != "formal_run"
                    or record.get("expected_next_binding_sha256") != binding_digest(next_binding)
                    or record.get("expected_next_run_set_sha256") != sha256(canonical_bytes(expected_runs))
                    or next_binding["fingerprint"] == record["fingerprint"]):
                raise LedgerError("ledger_expected_binding_invalid")
        elif expected_next:
            raise LedgerError("ledger_expected_binding_invalid")
    phases = records[2:]
    diagnostics = [r for r in phases if r["role"] == "diagnostic"]
    finals = [r for r in phases if r["role"] == "final_probe"]
    formals = [r for r in phases if r["role"] == "formal_run"]
    if len(diagnostics) > 1 or len(finals) > 1:
        raise LedgerError("ledger_role_binding_duplicate")
    if phases:
        if phases[0]["role"] != "diagnostic":
            raise LedgerError("ledger_phase_order_invalid")
        if finals and (len(phases) < 2 or phases[1]["role"] != "final_probe"
                       or phases[0]["state"] != "completed_diagnostic"):
            raise LedgerError("ledger_phase_order_invalid")
        formal_offset = 2 if finals else len(phases)
        if any(r["role"] != "formal_run" for r in phases[formal_offset:]):
            raise LedgerError("ledger_phase_order_invalid")
        if phases[0]["state"] not in {"completed_diagnostic"} and len(phases) > 1:
            raise LedgerError("ledger_phase_order_invalid")
        if finals and phases[1]["state"] != "final_pass" and len(phases) > 2:
            raise LedgerError("ledger_phase_order_invalid")
        expected_run_ids = [f"C{c}-{side}-{n}" for c in range(1, 7) for side in ("A", "B") for n in (1, 2)]
        if finals and [r["run_id"] for r in phases[2:]] != expected_run_ids[:len(phases[2:])]:
            raise LedgerError("ledger_phase_order_invalid")
        formal_records = phases[2:] if finals else []
        if any(r["state"] != "formal_run_pass" for r in formal_records[:-1]):
            raise LedgerError("ledger_phase_order_invalid")
    if diagnostics and finals and (diagnostics[0]["binding_sha256"] == finals[0]["binding_sha256"]
            or diagnostics[0].get("expected_next_binding") != finals[0]["binding"]):
        raise LedgerError("ledger_phase_binding_reused")
    if formals:
        if (not finals or len({r["binding_sha256"] for r in formals}) != 1
                or len({r["run_set_sha256"] for r in formals}) != 1
                or any(r["binding_sha256"] == finals[0]["binding_sha256"] for r in formals)
                or finals[0].get("expected_next_binding") != formals[0]["binding"]
                or finals[0].get("expected_next_run_set_sha256") != formals[0]["run_set_sha256"]):
            raise LedgerError("ledger_formal_binding_changed")
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

    def reserve(self, *, role: str, binding: dict, run_id: str | None = None):
        if role not in {"diagnostic", "final_probe", "formal_run"}:
            raise LedgerError("reservation_binding_invalid")
        binding = validate_binding(binding)
        fingerprint = binding["fingerprint"]
        root_identity = binding["root_identity"]
        spec_sha256 = binding["spec_sha256"]
        command_sha256 = binding["command_sha256"]
        digest = binding_digest(binding)
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
                                           or any(r.get("role") == "final_probe" for r in phase_records)
                                           or any(r.get("role") == "diagnostic" and
                                                  (r.get("binding_sha256") == digest or r.get("expected_next_binding") != binding)
                                                  for r in phase_records)):
                raise LedgerError("final_probe_gate_not_satisfied")
            if role == "formal_run":
                valid_ids = {f"C{c}-{s}-{n}" for c in range(1, 7) for s in ("A", "B") for n in (1, 2)}
                existing_runs = {r.get("run_id") for r in phase_records if r.get("role") == "formal_run"}
                run_order = [f"C{c}-{s}-{n}" for c in range(1, 7) for s in ("A", "B") for n in (1, 2)]
                prior_formal = [r for r in phase_records if r.get("role") == "formal_run"]
                if (run_id not in valid_ids or not formal_start_eligible(records[:4])
                        or any(r.get("role") == "final_probe" and r.get("binding_sha256") == digest for r in phase_records)
                        or not any(r.get("role") == "final_probe" and r.get("state") == "final_pass"
                                   and r.get("expected_next_binding") == binding
                                   and r.get("expected_next_run_set_sha256") == sha256(canonical_bytes(run_order))
                                   for r in phase_records)
                        or any(r.get("binding_sha256") != digest for r in prior_formal)
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
                      "preflight_sha256": binding["preflight_sha256"], "manifest_sha256": binding["manifest_sha256"],
                      "binding": binding, "binding_sha256": digest,
                      "pid": os.getpid(), "pgid": os.getpgrp(), "owner_uid": os.getuid(),
                      "started_epoch": now, "deadline_epoch": now + (600 if role in {"diagnostic", "final_probe"} else 240),
                      "state": "reserved"}
            if run_id is not None:
                record["run_id"] = run_id
            if role == "formal_run":
                record["run_set_sha256"] = sha256(canonical_bytes(run_order))
            commit = self.remote.push_ff(head, canonical_bytes({"schema": 1, "version": VERSION, "records": records + [record]}))
            if self.remote.ls_remote() != commit:
                raise LedgerError("remote_reservation_confirmation_failed")
            # The remote reservation consumes the slot even if this local write fails.
            self._write_local(records + [record], commit)
            return record
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def mark_running(self, attempt_id: str, *, binding: dict):
        binding = validate_binding(binding)
        fd = self._lock()
        try:
            ledger = self._read_local(); head, records = self._verify_remote(ledger)
            matches = [r for r in records[2:] if r.get("id") == attempt_id]
            if len(matches) != 1 or matches[0].get("state") != "reserved" or matches[0].get("binding") != binding:
                raise LedgerError("attempt_transition_invalid")
            matches[0]["state"] = "running"
            commit = self.remote.push_ff(head, canonical_bytes({"schema": 1, "version": VERSION, "records": records}))
            if self.remote.ls_remote() != commit:
                raise LedgerError("remote_reservation_confirmation_failed")
            self._write_local(records, commit)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)

    def complete(self, attempt_id: str, state: str, *, binding: dict, determination: str | None = None,
                 run_id: str | None = None, result_artifact_path: Path | None = None,
                 evidence_sidecar_path: Path | None = None, next_binding: dict | None = None,
                 diagnostic_report: bytes | None = None, gate_evidence: dict | None = None,
                 result_artifact_sha256: str | None = None):
        if state not in STATES - {"reserved", "running"}:
            raise LedgerError("attempt_state_invalid")
        binding = validate_binding(binding)
        if next_binding is not None:
            next_binding = validate_binding(next_binding)
        # Legacy caller-asserted evidence inputs are intentionally rejected.
        if diagnostic_report is not None or gate_evidence is not None or result_artifact_sha256 is not None:
            raise LedgerError("attempt_transition_invalid")
        if (result_artifact_path is None) != (evidence_sidecar_path is None):
            raise LedgerError("pass_gate_evidence_invalid")
        fd = self._lock()
        try:
            ledger = self._read_local()
            head, records = self._verify_remote(ledger)
            matches = [r for r in records[2:] if r.get("id") == attempt_id]
            if len(matches) != 1 or matches[0].get("state") not in {"reserved", "running"}:
                raise LedgerError("attempt_transition_invalid")
            record = matches[0]
            if record["binding"] != binding or record["binding_sha256"] != binding_digest(binding):
                raise LedgerError("attempt_transition_invalid")
            role_state = {"diagnostic": {"completed_diagnostic", "diagnostic_inconclusive", "unknown", "timeout", "crash"},
                          "final_probe": {"final_pass", "final_fail", "unknown", "timeout", "crash"},
                          "formal_run": {"formal_run_pass", "formal_run_fail", "unknown", "timeout", "crash"}}
            if state not in role_state.get(record.get("role"), set()):
                raise LedgerError("attempt_transition_invalid")
            if record["role"] == "diagnostic" and state == "completed_diagnostic":
                if result_artifact_path is None or next_binding is None or next_binding["fingerprint"] == binding["fingerprint"]:
                    raise LedgerError("diagnostic_report_required")
                artifact_hash, artifact_determination, _ = verify_saved_result(
                    result_artifact_path, evidence_sidecar_path, record=record, binding=binding)
                if artifact_determination != "resolved":
                    raise LedgerError("attempt_transition_invalid")
                record["report_sha256"] = artifact_hash
                record["result_artifact_sha256"] = artifact_hash
                record.update({"expected_next_role": "final_probe", "expected_next_binding": next_binding,
                               "expected_next_binding_sha256": binding_digest(next_binding)})
                determination = artifact_determination
            elif record["role"] == "diagnostic" and result_artifact_path is not None:
                raise LedgerError("attempt_transition_invalid")
            if state == "diagnostic_inconclusive" and determination != "inconclusive":
                raise LedgerError("attempt_transition_invalid")
            if state in {"final_pass", "formal_run_pass"}:
                expected_gates = {"env", "runtime", "binding", "event", "scope", "residual", "cli"}
                if result_artifact_path is None:
                    raise LedgerError("pass_gate_evidence_invalid")
                artifact_hash, _, gate_evidence = verify_saved_result(
                    result_artifact_path, evidence_sidecar_path, record=record, binding=binding)
                if (set(gate_evidence) != expected_gates
                        or any(value is not True for value in gate_evidence.values())):
                    raise LedgerError("pass_gate_evidence_invalid")
                record["result_artifact_sha256"] = artifact_hash
                record["gate_schema"] = 1
                record["gate_evidence"] = dict(gate_evidence)
                record["gate_evidence_sha256"] = gate_evidence_digest(
                    attempt_id=record["id"], binding_sha256=record["binding_sha256"],
                    result_artifact_sha256=artifact_hash, evidence=gate_evidence,
                    run_id=record.get("run_id"))
                if state == "final_pass":
                    if next_binding is None or next_binding["fingerprint"] == binding["fingerprint"]:
                        raise LedgerError("ledger_expected_binding_invalid")
                    expected_runs = [f"C{c}-{side}-{n}" for c in range(1, 7) for side in ("A", "B") for n in (1, 2)]
                    record.update({"expected_next_role": "formal_run", "expected_next_binding": next_binding,
                                   "expected_next_binding_sha256": binding_digest(next_binding),
                                   "expected_next_run_set_sha256": sha256(canonical_bytes(expected_runs))})
            elif result_artifact_path is not None and record["role"] != "diagnostic":
                raise LedgerError("attempt_transition_invalid")
            if next_binding is not None and not (record["role"] == "diagnostic" and state == "completed_diagnostic"
                    or record["role"] == "final_probe" and state == "final_pass"):
                raise LedgerError("attempt_transition_invalid")
            record["state"] = state
            if determination is not None:
                if determination not in DETERMINATIONS or record.get("role") != "diagnostic":
                    raise LedgerError("attempt_transition_invalid")
                record["determination"] = determination
            if record.get("role") == "formal_run":
                if run_id != record.get("run_id"):
                    raise LedgerError("attempt_transition_invalid")
            elif run_id is not None:
                raise LedgerError("attempt_transition_invalid")
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

    def formal_gate(self, expected_binding: dict):
        expected_binding = validate_binding(expected_binding)
        ledger = self._read_local()
        self._verify_remote(ledger)
        if (not formal_start_eligible(ledger["records"])
                or ledger["records"][3].get("expected_next_binding") != expected_binding
                or ledger["records"][3].get("expected_next_binding_sha256") != binding_digest(expected_binding)):
            raise LedgerError("formal_gate_not_satisfied")
        return True


class _AdapterSealMeta(type):
    def __setattr__(cls, name, value):
        if getattr(cls, "_class_sealed", False):
            raise LedgerError("fixed_cli_binding_invalid")
        super().__setattr__(name, value)


class FixedOpenAIDirectCodexAdapter(metaclass=_AdapterSealMeta):
    """A sealed route descriptor; readiness is separate from the global disabled-call gate."""
    __slots__ = ("_argv", "_binding_bytes", "_command_sha256", "_profile_sha256", "_root_bytes")
    actual_enabled = True
    transport = "OpenAI direct"
    fixed_arguments = ("exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                       "--skip-git-repo-check", "--sandbox", "read-only", "--json",
                       "--model", "gpt-6-astra", "-c", 'model_provider="openai"',
                       "-c", "features.hooks=false", "-c", 'default_permissions="p5_fixture"',
                       "-c", 'shell_environment_policy.inherit="all"', "-")
    _class_sealed = False

    def __init__(self, argv, *, command_sha256, binding, residual_scanner):
        validated = validate_binding(binding)
        args = tuple(argv)
        if (not args or not os.path.isabs(args[0]) or os.path.realpath(args[0]) != args[0]
                or Path(args[0]).name != "codex" or args[1:] != self.fixed_arguments
                or command_sha256 != validated["command_sha256"]
                or command_sha256 != runner_command_sha256(args[0])
                or residual_scanner is not _production_residual_scanner):
            raise LedgerError("fixed_cli_binding_invalid")
        object.__setattr__(self, "_argv", args)
        object.__setattr__(self, "_binding_bytes", canonical_bytes(validated))
        object.__setattr__(self, "_command_sha256", command_sha256)
        object.__setattr__(self, "_profile_sha256", SANDBOX_PROFILE_SHA256)
        object.__setattr__(self, "_root_bytes", canonical_bytes(validated["root_identity"]))

    def __setattr__(self, name, value):
        raise LedgerError("fixed_cli_binding_invalid")

    @property
    def argv(self):
        return self._argv

    @property
    def binding(self):
        return strict_json(self._binding_bytes)

    @property
    def profile_sha256(self):
        return self._profile_sha256

    def invoke(self, deadline_epoch, *, attempt_id, binding, sandbox_directory, actual_enabled=False):
        if (binding != self.binding or type(attempt_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", attempt_id)):
            raise LedgerError("fixed_cli_binding_invalid")
        # The adapter can be structurally ready while actual model execution is globally disabled.
        if actual_enabled is not True or not ACTUAL_INVOCATIONS_ENABLED:
            raise LedgerError("actual_invocation_disabled")
        result, report = _invoke_diagnostic_cli(self.argv, deadline_epoch=deadline_epoch,
            attempt_id=attempt_id, binding=binding, sandbox_directory=Path(sandbox_directory))
        return {**result, "stdout": canonical_bytes(report), "answer": b"", "raw": b""}


def runner_argv_spec(codex_executable):
    """Canonical fixed argv: sandbox profile setting, then fixed Codex direct route."""
    if type(codex_executable) is not str or not os.path.isabs(codex_executable):
        raise LedgerError("fixed_cli_binding_invalid")
    return (SANDBOX_EXEC, "-p", SANDBOX_PROFILE_TEMPLATE, codex_executable,
            *FixedOpenAIDirectCodexAdapter.fixed_arguments)


def runner_command_sha256(codex_executable):
    return sha256(canonical_bytes(list(runner_argv_spec(codex_executable))))


def _production_residual_scanner(pid, pgid):
    """Fail closed unless a complete process inventory confirms both identifiers absent."""
    try:
        result = subprocess.run(("/bin/ps", "-axo", "pid=,pgid="), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3.0, check=False)
        if result.returncode != 0 or result.stderr or not result.stdout.strip():
            return False
        for row in result.stdout.decode("ascii", "strict").splitlines():
            fields = row.split()
            if len(fields) != 2 or not all(value.isdigit() for value in fields):
                return False
            if int(fields[0]) == pid or int(fields[1]) == pgid:
                return False
        return True
    except (OSError, UnicodeError, subprocess.TimeoutExpired, ValueError):
        return False


_DIAGNOSTIC_REQUIRED_KEYS = tuple(sorted(("PATH", "LANG", "LC_ALL", "HOME", "TMPDIR", "TMP", "TEMP",
    "PYTHONDONTWRITEBYTECODE", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_OPTIONAL_LOCKS", "P5_RUN_TOKEN")
    + (("__CF_USER_TEXT_ENCODING",) if sys.platform == "darwin" else ())))
_DIAGNOSTIC_RUNTIME_KEYS = frozenset(("CODEX_CI", "CODEX_PERMISSION_PROFILE", "CODEX_SANDBOX",
    "CODEX_SANDBOX_NETWORK_DISABLED", "CODEX_SESSION_ID", "CODEX_THREAD_ID", "CODEX_VERSION",
    "COLORTERM", "GH_PAGER", "GIT_PAGER", "LC_CTYPE", "LOGNAME", "NO_COLOR", "OLDPWD",
    "PAGER", "PWD", "SHLVL", "TERM", "_"))
_PATH_PROFILE_HASHES = {
    "normal_shell_login": "22c1cd8ce1b055b6ff63df7ffd1e6b9d3999216e4d10c48b02d26bcef77b8efc",
    "normal_shell_codex_host_projection": "8005165d1cd846fa8cb1971a0b8ecbbd066c2d6fb465bb8e4b4906fd9f48887c",
    "codex_host": "8283ba217254d7532bdd107b5dd947a6c6d1ec66f684b69a999975c4979b0acb"}
_DIAGNOSTIC_PROMPT = (
    "この専用fixtureで最初かつ唯一のtool操作として固定canary commandを一度だけ実行し、"
    "その終了を待って停止してください。追加tool、ファイル変更、他ファイルの閲覧、"
    "課題やA/B契約の閲覧をしないでください。\n")


def _diagnostic_canary_source():
    # This source writes only the schema allowlist. It never prints env values, names, or digests.
    return r'''import hashlib,json,os,pwd,re,sys
with open(".p5-v20-expected.json",encoding="utf-8") as f: expected=json.load(f)
env=dict(os.environ); req=expected["required_keys"]; allowed=set(req)|set(expected["runtime_keys"])
home=expected["home"]
fixed={home+suffix for suffix in ("/.volta/bin","/.pyenv/shims","/.antigravity/antigravity/bin","/.local/bin")}
fixed.update(("/opt/homebrew/bin","/opt/homebrew/sbin","/usr/local/bin","/System/Cryptexes/App/usr/bin","/usr/bin","/bin","/usr/sbin","/sbin","/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/local/bin","/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/bin","/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/appleinternal/bin","/pkg/env/global/bin"))
def project(parts):
 out=[]; unknown=0
 for part in parts:
  if part in fixed: out.append(part.replace(home,"<HOME>"))
  elif re.fullmatch(re.escape(home)+r"/\.codex/packages/app-server-daemon/releases/[0-9]+\.[0-9]+\.[0-9]+-[A-Za-z0-9_-]+/codex-path",part): out.append("<CODEX_APP_SERVER_RELEASE>/codex-path")
  elif re.fullmatch(re.escape(home)+r"/\.codex/tmp/arg0/codex-arg0[A-Za-z0-9]+",part): out.append("<CODEX_ARG0_TEMP>")
  elif re.fullmatch(r"/opt/homebrew/Caskroom/codex/[0-9]+\.[0-9]+\.[0-9]+/codex-path",part): out.append("<CODEX_CASKROOM_RELEASE>/codex-path")
  else: out.append("<UNAPPROVED>"); unknown+=1
 return hashlib.sha256(json.dumps(out,separators=(",",":")).encode()).hexdigest(),unknown
path_value=env.get("PATH"); parts=path_value.split(os.pathsep) if isinstance(path_value,str) and path_value else []
if not isinstance(path_value,str) or "\0" in path_value or len(parts)>128: raise SystemExit(2)
path_hash,unapproved=project(parts); matched=next((k for k,v in expected["path_profiles"].items() if v==path_hash),"none")
order="empty" if not parts else "exact_profile" if matched!="none" else "unapproved_component_present" if unapproved else "known_components_reordered"
unknown=set(env)-allowed; codex_home="CODEX_HOME" in unknown; other=len(unknown)-int(codex_home)
if len(unknown)>128 or other>0 or unapproved>1 or order=="malformed": raise SystemExit(2)
required_checks={k:(k in env and env.get(k)==expected["env"].get(k)) for k in req}
if any(k not in env for k in req): raise SystemExit(2)
for k in ("LANG","LC_ALL"):
 if k in env: required_checks[k]=hashlib.sha256(env[k].encode()).hexdigest()==expected["locale_sha256"]
if "PATH" in env: required_checks["PATH"]=matched!="none"
runtime={"CODEX_CI":env.get("CODEX_CI")=="1","CODEX_PERMISSION_PROFILE":env.get("CODEX_PERMISSION_PROFILE")=="p5_fixture","CODEX_SANDBOX":env.get("CODEX_SANDBOX")=="seatbelt","CODEX_SANDBOX_NETWORK_DISABLED":env.get("CODEX_SANDBOX_NETWORK_DISABLED")=="1","CODEX_SESSION_ID":re.fullmatch(expected["uuid7_pattern"],env.get("CODEX_SESSION_ID", "")) is not None,"CODEX_THREAD_ID":re.fullmatch(expected["uuid7_pattern"],env.get("CODEX_THREAD_ID", "")) is not None,"CODEX_VERSION":env.get("CODEX_VERSION")==expected["cli_version"],"COLORTERM":env.get("COLORTERM")=="","GH_PAGER":env.get("GH_PAGER")=="cat","GIT_PAGER":env.get("GIT_PAGER")=="cat","LC_CTYPE":env.get("LC_CTYPE")=="C.UTF-8","LOGNAME":env.get("LOGNAME")==pwd.getpwuid(os.getuid()).pw_name,"NO_COLOR":env.get("NO_COLOR")=="1","OLDPWD":env.get("OLDPWD")==expected["cwd"],"PAGER":env.get("PAGER")=="cat","PWD":env.get("PWD")==expected["cwd"],"SHLVL":env.get("SHLVL")=="0","TERM":env.get("TERM")=="dumb","_":env.get("_")==expected["python_executable"]}
if any(not x for x in required_checks.values()) or not all(runtime.values()) or os.getcwd()!=expected["cwd"]: fit="mismatch"
else: fit="pass" if not unknown and order=="exact_profile" else "mismatch"
if fit=="unknown" or order=="malformed" or other>0 or unapproved>1: raise SystemExit(2)
unknown_class="none" if not unknown else "codex_home_only"
report={"schema":1,"attempt_id":expected["attempt_id"],"fingerprint":expected["fingerprint"],"environment_fit":fit,"path":{"matched_profile":matched,"component_count":len(parts),"unapproved_component_count":unapproved,"order_classification":order},"unknown_keys":{"codex_home_present":codex_home,"classification":unknown_class,"unknown_count":len(unknown),"other_unknown_count":other},"determination":"resolved"}
print(json.dumps(report,sort_keys=True,separators=(",",":")))
'''


def _write_private_new(path: Path, data: bytes, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def _invoke_diagnostic_cli(argv, *, deadline_epoch, attempt_id, binding, sandbox_directory):
    if type(argv) is not tuple or argv[1:] != _FIXED_ARGUMENTS:
        raise LedgerError("fixed_cli_binding_invalid")
    if any(sandbox_directory.iterdir()):
        raise LedgerError("diagnostic_fixture_not_empty")
    home = pwd.getpwuid(os.getuid()).pw_dir
    scratch = sandbox_directory / ".benchmark-tmp"
    (scratch / "home").mkdir(parents=True, mode=0o700)
    python_executable = sys.executable
    fixed_path = os.pathsep.join(dict.fromkeys((str(Path(python_executable).parent),
        "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin")))
    env = {"PATH": fixed_path, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
           "HOME": str(scratch / "home"), "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch),
           "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_OPTIONAL_LOCKS": "0", "P5_RUN_TOKEN": uuid.uuid4().hex}
    if sys.platform == "darwin":
        env["__CF_USER_TEXT_ENCODING"] = f"0x{os.getuid():X}:0x0:0x0"
    allowed_known = {home + suffix for suffix in ("/.volta/bin", "/.pyenv/shims", "/.antigravity/antigravity/bin", "/.local/bin")}
    allowed_known.update(("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", "/System/Cryptexes/App/usr/bin",
        "/usr/bin", "/bin", "/usr/sbin", "/sbin", "/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/local/bin",
        "/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/bin", "/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/appleinternal/bin", "/pkg/env/global/bin"))
    expected = {"attempt_id": attempt_id, "fingerprint": binding["fingerprint"], "env": env,
        "required_keys": list(_DIAGNOSTIC_REQUIRED_KEYS), "runtime_keys": sorted(_DIAGNOSTIC_RUNTIME_KEYS),
        "path_profiles": _PATH_PROFILE_HASHES, "home": home,
        "locale_sha256": sha256(b"C.UTF-8"), "cli_version": "0.162.1",
        "uuid7_pattern": r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        "python_executable": python_executable, "cwd": str(sandbox_directory.resolve(strict=True)),
        "known_path_components": sorted(allowed_known)}
    script_path = sandbox_directory / ".p5-v20-env-canary.py"
    expected_path = sandbox_directory / ".p5-v20-expected.json"
    _write_private_new(expected_path, canonical_bytes(expected), 0o400)
    _write_private_new(script_path, _diagnostic_canary_source().encode("utf-8"), 0o400)
    canary_command = shlex.join(("/bin/zsh", "-lc", shlex.join((python_executable, "-I", "-B", script_path.name))))
    process_env = {**env, "CODEX_HOME": str(Path(home) / ".codex")}
    before_tree = _tree_fingerprint(sandbox_directory)
    result = run_process_group(argv, deadline_epoch=deadline_epoch,
        residual_scanner=_production_residual_scanner, cwd=sandbox_directory,
        sandbox_directory=sandbox_directory,
        stdin_data=(_DIAGNOSTIC_PROMPT + canary_command + "\n").encode("utf-8"), env=process_env)
    if (result["timed_out"] or not result["child_reaped"] or not result["residual_verified"]
            or result["returncode"] != 0 or result["stderr"] or _tree_fingerprint(sandbox_directory) != before_tree):
        raise LedgerError("diagnostic_cli_failed")
    report = _audit_diagnostic_events(result["stdout"], canary_command=canary_command,
        attempt_id=attempt_id, fingerprint=binding["fingerprint"])
    script_path.unlink(); expected_path.unlink(); shutil.rmtree(scratch)
    return result, report


def _audit_diagnostic_events(raw: bytes, *, canary_command: str, attempt_id: str, fingerprint: str):
    if type(raw) is not bytes or not raw or len(raw) > 4 * 1024 * 1024:
        raise LedgerError("diagnostic_event_audit_failed")
    events=[]
    for line in raw.splitlines():
        if len(line) > 1024 * 1024:
            raise LedgerError("diagnostic_event_audit_failed")
        event = strict_json(line)
        if type(event) is not dict or type(event.get("type")) is not str:
            raise LedgerError("diagnostic_event_audit_failed")
        events.append(event)
    if len(events) > 128:
        raise LedgerError("diagnostic_event_audit_failed")
    thread=turn=ended=False; tool=[]; report_bytes=None; non_tool_ids=set()
    for event in events:
        kind=event["type"]
        if kind == "thread.started":
            if thread or turn or ended or type(event.get("thread_id")) is not str: raise LedgerError("diagnostic_event_audit_failed")
            thread=True
        elif kind == "turn.started":
            if not thread or turn or ended: raise LedgerError("diagnostic_event_audit_failed")
            turn=True
        elif kind == "turn.completed":
            if not turn or ended: raise LedgerError("diagnostic_event_audit_failed")
            ended=True
        elif kind in {"error", "turn.failed"}:
            raise LedgerError("diagnostic_event_audit_failed")
        elif kind in {"item.started", "item.completed"}:
            if not turn or ended: raise LedgerError("diagnostic_event_audit_failed")
            item=event.get("item")
            if type(item) is not dict:
                raise LedgerError("diagnostic_event_audit_failed")
            if item.get("type") in {"agent_message", "reasoning", "todo_list"}:
                item_id=item.get("id")
                if type(item_id) is not str or not item_id or kind != "item.completed" or item_id in non_tool_ids:
                    raise LedgerError("diagnostic_event_audit_failed")
                non_tool_ids.add(item_id)
                continue
            if item.get("type") != "command_execution":
                raise LedgerError("diagnostic_event_audit_failed")
            if item.get("command") != canary_command:
                raise LedgerError("diagnostic_event_audit_failed")
            if kind == "item.started":
                if item.get("status") != "in_progress" or tool: raise LedgerError("diagnostic_event_audit_failed")
                tool.append(("started", item.get("id")))
            else:
                if (len(tool)!=1 or tool[0][1] != item.get("id") or item.get("status") != "completed"
                        or type(item.get("exit_code")) is not int or item["exit_code"] != 0
                        or type(item.get("aggregated_output")) is not str):
                    raise LedgerError("diagnostic_event_audit_failed")
                tool.append(("completed", item.get("id")))
                report_bytes=item["aggregated_output"].encode("utf-8")
        elif kind == "item.updated":
            raise LedgerError("diagnostic_event_audit_failed")
        elif kind not in {"reasoning", "agent_message", "todo_list"}:
            raise LedgerError("diagnostic_event_audit_failed")
    if not (thread and turn and ended and len(tool)==2 and tool[0][0]=="started" and tool[1][0]=="completed" and report_bytes):
        raise LedgerError("diagnostic_event_audit_failed")
    parsed=strict_json(report_bytes)
    return validate_report(parsed, attempt_id=attempt_id, fingerprint=fingerprint)


ACTUAL_INVOCATIONS_ENABLED = True  # Explicit, reviewable source gate; config has an independent true/false gate.
_FIXED_ADAPTER_INVOKE = FixedOpenAIDirectCodexAdapter.invoke
_ADAPTER_READY = True
_FIXED_ARGUMENTS = FixedOpenAIDirectCodexAdapter.fixed_arguments
_FIXED_TRANSPORT = "OpenAI direct"
type.__setattr__(FixedOpenAIDirectCodexAdapter, "_class_sealed", True)


def _verify_adapter_seal(adapter, binding):
    """Verify all adapter invariants outside the callback boundary and before reservation."""
    if type(adapter) is not FixedOpenAIDirectCodexAdapter:
        raise LedgerError("fixed_cli_binding_invalid")
    cls = type(adapter)
    # Inspect the class dictionary without resolving any instance attribute. A descriptor
    # replacement must be rejected before property/getattribute code can execute.
    raw_invoke = type.__getattribute__(cls, "__dict__").get("invoke")
    if raw_invoke is not _FIXED_ADAPTER_INVOKE:
        raise LedgerError("fixed_cli_binding_invalid")
    if type.__getattribute__(cls, "__dictoffset__") != 0:
        raise LedgerError("fixed_cli_binding_invalid")
    try:
        bound = object.__getattribute__(adapter, "invoke")
    except Exception:
        raise LedgerError("fixed_cli_binding_invalid") from None
    if (getattr(bound, "__func__", None) is not _FIXED_ADAPTER_INVOKE
            or cls.actual_enabled is not _ADAPTER_READY or adapter.actual_enabled is not _ADAPTER_READY
            or cls.fixed_arguments != _FIXED_ARGUMENTS or cls.transport != _FIXED_TRANSPORT
            or adapter.transport != _FIXED_TRANSPORT
            or adapter.argv[1:] != _FIXED_ARGUMENTS
            or Path(adapter.argv[0]).name != "codex"
            or adapter._command_sha256 != binding["command_sha256"]
            or runner_command_sha256(adapter.argv[0]) != adapter._command_sha256
            or adapter._profile_sha256 != SANDBOX_PROFILE_SHA256
            or adapter._root_bytes != canonical_bytes(binding["root_identity"])
            or adapter.binding != binding):
        raise LedgerError("fixed_cli_binding_invalid")


def run_process_group(argv, *, deadline_epoch, residual_scanner, cwd=None, sandbox_directory=None,
                      stdin_data=None, env=None):
    """Run one fixed command in a new process group; keep all child output in memory."""
    if type(argv) not in (tuple, list) or not argv or any(type(x) is not str for x in argv):
        raise LedgerError("fixed_cli_binding_invalid")
    if sandbox_directory is None:
        raise LedgerError("host_containment_unavailable")
    if stdin_data is not None and type(stdin_data) is not bytes:
        raise LedgerError("fixed_cli_binding_invalid")
    if env is not None and (type(env) is not dict or any(type(k) is not str or type(v) is not str for k, v in env.items())):
        raise LedgerError("fixed_cli_binding_invalid")
    contained_argv = sandboxed_argv(argv, Path(sandbox_directory))
    remaining = deadline_epoch - time.time()
    if remaining <= 0:
        return {"returncode": -1, "stdout": b"", "stderr": b"", "timed_out": True,
                "child_reaped": True, "residual_verified": False}
    try:
        child = subprocess.Popen(contained_argv, stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True, close_fds=True, cwd=cwd, env=env)
    except OSError:
        raise LedgerError("diagnostic_cli_spawn_failed") from None
    timed_out = False
    try:
        stdout, stderr = child.communicate(input=stdin_data, timeout=remaining)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = child.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = child.communicate()
    except BaseException:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = child.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate()
        if child.poll() is None:
            raise LedgerError("diagnostic_residual_unverified") from None
        try:
            if residual_scanner(child.pid, child.pid) is not True:
                raise LedgerError("diagnostic_residual_unverified") from None
        except LedgerError:
            raise
        except Exception:
            raise LedgerError("diagnostic_residual_unverified") from None
        raise LedgerError("diagnostic_cli_failed") from None
    reaped = child.poll() is not None
    try:
        residual = residual_scanner(child.pid, child.pid)
    except Exception:
        residual = False
    return {"returncode": child.returncode if reaped else -1, "stdout": stdout, "stderr": stderr,
            "timed_out": timed_out, "child_reaped": reaped, "residual_verified": residual is True}


def sandbox_boundary_preflight():
    """Model-free host check. Must run in the ordinary shell, outside an outer sandbox."""
    with tempfile.TemporaryDirectory(prefix="p5-v20-host-boundary-") as td:
        fixture = Path(td); sandbox = fixture / "sandbox"; sandbox.mkdir(mode=0o700)
        external_root = Path(tempfile.mkdtemp(prefix="p5-v20-absolute-escape-", dir="/private/tmp"))
        try:
            forbidden = (fixture.parent / f"{fixture.name}-escaped.raw", fixture / "sibling.raw",
                         external_root / "absolute.raw")
            code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('synthetic-write-sentinel')"
            for target in forbidden:
                outcome = run_process_group((os.path.realpath(os.sys.executable), "-I", "-B", "-c", code, str(target)),
                    deadline_epoch=time.time()+10, residual_scanner=lambda *_: True,
                    cwd=sandbox, sandbox_directory=sandbox)
                if (outcome["returncode"] == 0 or not outcome["child_reaped"] or not outcome["residual_verified"]
                        or target.exists()):
                    raise LedgerError("host_containment_escape_detected")
                error_code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('sentinel'); raise RuntimeError('fixture')"
                error_outcome = run_process_group((os.path.realpath(os.sys.executable), "-I", "-B", "-c", error_code, str(target)),
                    deadline_epoch=time.time()+10, residual_scanner=lambda *_: True,
                    cwd=sandbox, sandbox_directory=sandbox)
                if error_outcome["returncode"] == 0 or not error_outcome["child_reaped"] or target.exists():
                    raise LedgerError("host_containment_escape_detected")
                timeout_code = ("import pathlib,sys,time\ntry: pathlib.Path(sys.argv[1]).write_text('sentinel')\n"
                                "except OSError: pass\ntime.sleep(5)")
                timeout_outcome = run_process_group((os.path.realpath(os.sys.executable), "-I", "-B", "-c", timeout_code, str(target)),
                    deadline_epoch=time.time()+0.1, residual_scanner=lambda *_: True,
                    cwd=sandbox, sandbox_directory=sandbox)
                if (not timeout_outcome["timed_out"] or not timeout_outcome["child_reaped"]
                        or not timeout_outcome["residual_verified"] or target.exists()):
                    raise LedgerError("host_containment_timeout_cleanup_failed")
            allowed = sandbox / "allowed.raw"
            inside = run_process_group((os.path.realpath(os.sys.executable), "-I", "-B", "-c",
                "import pathlib; pathlib.Path('allowed.raw').write_text('ok')"), deadline_epoch=time.time()+10,
                residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox)
            if inside["returncode"] != 0 or not allowed.is_file() or allowed.read_text() != "ok":
                raise LedgerError("host_containment_profile_mismatch")
            allowed.unlink()
            timed = run_process_group((os.path.realpath(os.sys.executable), "-I", "-B", "-c",
                "import time; time.sleep(5)"), deadline_epoch=time.time()+0.1,
                residual_scanner=lambda *_: True, cwd=sandbox, sandbox_directory=sandbox)
            if not timed["timed_out"] or not timed["child_reaped"] or not timed["residual_verified"]:
                raise LedgerError("host_containment_timeout_cleanup_failed")
            if any(p.name != "sandbox" for p in fixture.iterdir()) or any(sandbox.iterdir()):
                raise LedgerError("host_containment_external_write_detected")
            return {"available": True, "profile_sha256": SANDBOX_PROFILE_SHA256,
                    "escape_cases": len(forbidden) * 3, "allowed_write": True, "timeout_reaped": True}
        finally:
            (fixture.parent / f"{fixture.name}-escaped.raw").unlink(missing_ok=True)
            (fixture / "sibling.raw").unlink(missing_ok=True)
            (external_root / "absolute.raw").unlink(missing_ok=True)
            if external_root.exists():
                shutil.rmtree(external_root, ignore_errors=True)


def run_diagnostic_once(ledger: GlobalLedger, *, binding: dict, adapter, artifact_directory: Path,
                       next_binding_factory, actual_enabled=False):
    """One diagnostic lifecycle. Adapter outputs remain in memory and are never copied verbatim."""
    binding = validate_binding(binding)
    _verify_adapter_seal(adapter, binding)
    if actual_enabled is not True or not ACTUAL_INVOCATIONS_ENABLED:
        raise LedgerError("actual_invocation_disabled")
    parent = Path(artifact_directory).parent
    parent_info = parent.lstat()
    if (not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.getuid()
            or stat.S_IMODE(parent_info.st_mode) != 0o700):
        raise LedgerError("artifact_directory_identity_invalid")
    record = ledger.reserve(role="diagnostic", binding=binding)
    attempt_id = record["id"]
    try:
        # reserve() returns only after remote FF push and ls-remote confirmation.
        ledger.mark_running(attempt_id, binding=binding)
        before_tree = _tree_fingerprint(parent)
        with tempfile.TemporaryDirectory(prefix="p5-v20-diagnostic-", dir=Path(artifact_directory).parent) as sandbox:
            outcome = adapter.invoke(record["deadline_epoch"], attempt_id=attempt_id, binding=binding,
                                     sandbox_directory=Path(sandbox), actual_enabled=actual_enabled)
            direct_outputs = [p for p in Path(sandbox).rglob("*") if p.is_file() or p.is_symlink()]
            if direct_outputs:
                raise LedgerError("diagnostic_direct_artifact_present")
        if _tree_fingerprint(parent) != before_tree:
            raise LedgerError("host_containment_external_write_detected")
        required = {"returncode", "stdout", "stderr", "answer", "raw", "timed_out", "child_reaped", "residual_verified"}
        if (type(outcome) is not dict or set(outcome) != required
                or any(type(outcome[k]) is not bytes for k in ("stdout", "stderr", "answer", "raw"))
                or type(outcome["returncode"]) is not int
                or any(type(outcome[k]) is not bool for k in ("timed_out", "child_reaped", "residual_verified"))):
            raise LedgerError("diagnostic_adapter_result_invalid")
        if not outcome["child_reaped"] or not outcome["residual_verified"]:
            raise LedgerError("diagnostic_residual_unverified")
        if outcome["timed_out"]:
            raise LedgerError("invocation_timeout")
        if outcome["returncode"] != 0:
            raise LedgerError("diagnostic_cli_failed")
        parsed = strict_json(outcome["stdout"])
        safe = report_for_storage(parsed, attempt_id=attempt_id, fingerprint=binding["fingerprint"],
                                  binding_sha256=binding_digest(binding))
        if not callable(next_binding_factory):
            raise LedgerError("ledger_expected_binding_invalid")
        next_binding = validate_binding(next_binding_factory(strict_json(safe)))
        result_path, sidecar_path = save_verified_result(artifact_directory, attempt_id=attempt_id,
            role="diagnostic", run_id=None, binding=binding, result_bytes=safe)
        ledger.complete(attempt_id, "completed_diagnostic", binding=binding,
                        result_artifact_path=result_path, evidence_sidecar_path=sidecar_path,
                        next_binding=next_binding)
        return record
    except Exception as exc:
        code = fixed_error(exc)
        terminal = ("timeout" if code == "invocation_timeout" else
                    "diagnostic_inconclusive" if code == "diagnostic_inconclusive" else "unknown")
        ledger.complete(attempt_id, terminal, binding=binding,
                        determination="inconclusive" if terminal == "diagnostic_inconclusive" else None)
        raise LedgerError(code) from None


def _tree_fingerprint(root: Path):
    """In-memory inventory of a dedicated fixture root; filenames and values are never persisted."""
    root = Path(root).resolve(strict=True)
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda p: str(p.relative_to(root))):
        info = path.lstat()
        rel = str(path.relative_to(root)).encode("utf-8", "strict")
        if stat.S_ISDIR(info.st_mode):
            kind, payload = b"d", b""
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            kind, payload = b"f", path.read_bytes()
        else:
            raise LedgerError("host_containment_inventory_unknown")
        digest.update(len(rel).to_bytes(4, "big") + rel + kind)
        digest.update(canonical_bytes([info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode), info.st_size,
                                       info.st_mtime_ns, info.st_ctime_ns]))
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


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
        if head == self.seed_commit_pin:
            normalized, _ = validate_seed_payload(result.stdout)
            return normalized["records"]
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
            parent_records = self.chain(parent)
        else:
            parent_records = []
        parsed = strict_json(payload)
        valid_seed = False
        if parent is None:
            validate_seed_payload(payload)
            valid_seed = True
        valid_next = (type(parsed) is dict and set(parsed) == {"schema", "version", "records"}
                      and type(parsed.get("schema")) is int and parsed.get("schema") == 1
                      and type(parsed.get("version")) is int and parsed.get("version") == VERSION)
        if not (valid_seed or valid_next) or (valid_next and type(parsed.get("records")) is not list):
            raise LedgerError("remote_chain_schema_invalid")
        validate_record_chain(parsed["records"])
        child_records = parsed["records"]
        if parent is None and valid_seed:
            pass
        elif len(child_records) == len(parent_records) + 1:
            if child_records[:-1] != parent_records or child_records[-1].get("state") != "reserved":
                raise LedgerError("remote_chain_non_monotonic")
        elif len(child_records) == len(parent_records) and parent_records:
            changed = [i for i, (old, new) in enumerate(zip(parent_records, child_records)) if old != new]
            if len(changed) != 1:
                raise LedgerError("remote_chain_non_monotonic")
            index = changed[0]; old = parent_records[index]; new = child_records[index]
            mutable = {"state", "ended_epoch", "determination", "report_sha256", "result_artifact_sha256",
                       "gate_evidence_sha256", "gate_evidence", "gate_schema", "expected_next_role",
                       "expected_next_binding", "expected_next_binding_sha256", "expected_next_run_set_sha256"}
            if ({k: v for k, v in old.items() if k not in mutable} !=
                    {k: v for k, v in new.items() if k not in mutable}
                    or (old["state"], new["state"]) not in {
                        ("reserved", "running"), ("reserved", "completed_diagnostic"),
                        ("reserved", "diagnostic_inconclusive"), ("reserved", "final_pass"),
                        ("reserved", "final_fail"), ("reserved", "formal_run_pass"),
                        ("reserved", "formal_run_fail"), ("reserved", "unknown"),
                        ("reserved", "timeout"), ("reserved", "crash"),
                        ("running", "completed_diagnostic"), ("running", "diagnostic_inconclusive"),
                        ("running", "final_pass"), ("running", "final_fail"),
                        ("running", "formal_run_pass"), ("running", "formal_run_fail"),
                        ("running", "unknown"), ("running", "timeout"), ("running", "crash")}):
                raise LedgerError("remote_chain_non_monotonic")
        else:
            raise LedgerError("remote_chain_non_monotonic")
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
