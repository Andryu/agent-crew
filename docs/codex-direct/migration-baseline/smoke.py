#!/usr/bin/env python3
"""比較課題の実在とC6の非資産・非LLM手順を確認する。"""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    tick = time.monotonic()
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    comparison = json.loads((HERE / "comparison.json").read_text(encoding="utf-8"))
    index = json.loads((HERE / "snapshot-index.json").read_text(encoding="utf-8"))
    publication = json.loads((HERE.parent / "pr-publication-manifest.json").read_text(encoding="utf-8"))
    copy_path = HERE.parent / "pr-copy-manifest.json"
    assert digest(copy_path) == publication["copy_manifest_sha256"]
    copied = {item["target"]: item for item in json.loads(copy_path.read_text(encoding="utf-8"))["files"]}
    transforms = {item["path"]: item for item in publication["transforms"]}
    assert len(transforms) == len(publication["transforms"])
    for path, item in transforms.items():
        saved = ROOT / path
        assert saved.is_file() and not saved.is_symlink() and saved.resolve().is_relative_to(ROOT)
        assert copied[path]["sha256"] == item["original_sha256"]
        assert digest(saved) == item["published_sha256"]
        assert item["original_sha256"] != item["published_sha256"]
    assert index["publication"]["kind"] == "public_derivative"
    assert index["publication"]["original_index_sha256"] == copied["docs/codex-direct/migration-baseline/snapshot-index.json"]["sha256"]
    assert index["publication"]["transformation_manifest"] == "../pr-publication-manifest.json"
    assert "docs/codex-direct/migration-baseline/snapshot-index.json" in transforms
    assert manifest["schema"] == comparison["schema"] == 1
    assert index["schema"] == 1
    assert len(comparison["tasks"]) == 6
    assert set(manifest["global_codex"]["allowed_config_values"]) <= {
        "model", "model_reasoning_effort", "approval_policy", "approvals_reviewer",
        "default_permissions", "model_provider",
    }
    assert "/Users/" not in json.dumps(manifest, ensure_ascii=False)

    copies = {(entry["repo"], entry["source"]): entry for entry in index["entries"]}
    assert len(copies) == len(index["entries"])
    assert set(comparison["A_instruction_snapshot"]) <= {entry["snapshot"] for entry in index["entries"]}
    for entry in index["entries"]:
        name = entry["source"]
        assert name.endswith((".py", ".md")) or name in ("scripts/crew", "config/crew-hooks.json")
        saved = HERE / entry["snapshot"]
        assert saved.is_file() and not saved.is_symlink() and saved.resolve().is_relative_to(HERE)
        assert digest(saved) == entry["sha256"]
        repo = manifest[entry["repo"]]
        recorded = {item["path"]: item for item in repo["files"]}
        source = str(Path(repo["root"]).expanduser() / name).replace(str(Path.home()), "~", 1)
        original_sha = recorded[source]["sha256"]
        if original_sha != entry["sha256"]:
            transformed = transforms["docs/codex-direct/migration-baseline/" + entry["snapshot"]]
            assert transformed["original_sha256"] == original_sha
            assert transformed["published_sha256"] == entry["sha256"]
        else:
            assert original_sha == entry["sha256"]

    count = 0
    for task in comparison["tasks"]:
        for name in task["input"] + task["fixture"]:
            assert (task["repo"], name) in copies, name
            count += 1

    synthetic = index["synthetic_fixture"]
    fixture_source = HERE / synthetic["path"]
    assert fixture_source.is_file() and digest(fixture_source) == synthetic["sha256"]
    assert comparison["tasks"][-1]["extra_fixture"] == synthetic["path"]

    program = HERE / copies[("agent_crew", "migration-progress/progress.py")]["snapshot"]
    live_state = ROOT / "migration-progress/state.json"
    before = digest(live_state)
    with tempfile.TemporaryDirectory(prefix="migration-comparison-smoke-") as folder:
        fixture = Path(folder)
        shutil.copy2(program, fixture / "progress.py")
        shutil.copy2(fixture_source, fixture / "state.json")
        command = ["python3.12", "-B", str(fixture / "progress.py")]
        subprocess.run(command + ["set", "--task", "P0", "--status", "検証中",
                                  "--current", "比較smoke", "--next", "採点", "--blocker", "なし"],
                       capture_output=True, text=True, check=True)
        env = dict(os.environ, COLUMNS="96", LINES="22")
        shown = subprocess.run(command + ["--once"], env=env, capture_output=True, text=True, check=True).stdout
        assert "P0 [検証中]" in shown and "現在: 比較smoke" in shown
        assert "queue正本ではありません" in shown and len(shown.splitlines()) <= 22
    assert digest(live_state) == before

    seconds = round(time.monotonic() - tick, 3)
    result = {
        "task_id": "C6", "condition": "procedure-smoke（A/B比較ではない）",
        "started_at": started,
        "ended_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "validation_results": ["6課題の入力・fixtureとsnapshot/manifest hash一致", "C6のCLI更新/読込成功", "実state.json不変"],
        "validated_path_references": count,
        "wall_seconds": seconds,
        "approval_count": 0, "approval_wait_seconds": 0,
        "llm_seconds": "unknown", "tool_seconds": seconds,
        "input_tokens": "unknown", "output_tokens": "unknown", "cost_usd": "unknown",
        "rework_count": 0, "review_findings": "not_reviewed", "scope_violations": 0,
        "handoff_success": True,
        "note": "追加LLM呼出し・資産入力・A/Bの24run比較は実施していない",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
