#!/usr/bin/env python3
"""開発用許可設定を、既存設定を保持して導入する（既定は変更しない）。"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
START = "# BEGIN wealth-advisor developer permissions\n"
END = "# END wealth-advisor developer permissions\n"


def remove_managed(text):
    while START in text:
        before, rest = text.split(START, 1)
        if END not in rest:
            raise ValueError("管理ブロックが壊れています")
        _, after = rest.split(END, 1)
        text = before + after
    return text


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, tmp = tempfile.mkstemp(prefix=".permissions-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    home = Path.home() / ".codex"
    config = home / "config.toml"
    original = config.read_text()
    unmanaged = remove_managed(original)
    existing = tomllib.loads(unmanaged)
    for key in ["approval_policy", "approvals_reviewer", "default_permissions", "sandbox_mode", "sandbox_workspace_write"]:
        if key in existing:
            raise ValueError(f"既存の {key} と競合します。上書きせず停止しました")
    if "developer" in existing.get("permissions", {}):
        raise ValueError("既存developerプロファイルと競合します")
    source = (ROOT / "config/codex/developer.toml").read_text()
    top, tables = source.split("[permissions.developer]", 1)
    combined = START + top + END + unmanaged.rstrip() + "\n\n" + START + "[permissions.developer]" + tables + END
    parsed = tomllib.loads(combined)
    # 管理対象以外の意味が変わっていないことを検査する。
    expected = tomllib.loads(source)
    for key, value in existing.items():
        if key == "permissions":
            assert all(parsed[key][k] == v for k, v in value.items())
        else:
            assert parsed[key] == value
    assert parsed["permissions"]["developer"] == expected["permissions"]["developer"]
    files = {
        config: combined,
        home / "rules/developer.rules": (ROOT / "config/codex/developer.rules").read_text(),
        ROOT / ".codex/config.toml": (ROOT / "config/codex/project.toml").read_text(),
    }
    for path, content in files.items():
        if path != config and path.exists() and path.read_text() != content:
            raise ValueError(f"既存ファイルと競合します: {path}")
    changed = {path: text for path, text in files.items() if not path.exists() or path.read_text() != text}
    print(json.dumps({"mode": "apply" if args.apply else "preview", "changed_files": [str(p) for p in changed], "profile": "developer", "approval_policy": "on-request", "network": True}, ensure_ascii=False, indent=2))
    if not args.apply or not changed:
        return
    snapshots = {p: p.read_bytes() if p.exists() else None for p in changed}
    if config.read_text() != original:
        raise ValueError("設定が同時更新されたため停止しました")
    backup = home / "backups" / ("permissions-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    backup.mkdir(parents=True, mode=0o700)
    manifest = []
    for i, (path, old) in enumerate(snapshots.items()):
        record = {"path": str(path), "existed": old is not None, "backup": str(i)}
        if old is not None:
            target = backup / str(i)
            target.write_bytes(old)
            target.chmod(0o600)
        manifest.append(record)
    (backup / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (backup / "manifest.json").chmod(0o600)
    for path, content in changed.items():
        current = path.read_bytes() if path.exists() else None
        if current != snapshots[path]:
            raise ValueError(f"同時更新を検出。バックアップは {backup}")
        atomic_write(path, content)
    print(json.dumps({"backup": str(backup), "installed": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
