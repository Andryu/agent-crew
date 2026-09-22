#!/usr/bin/env python3
"""セッションを作らずCodexの有効hook・通知設定を読み取る。"""

import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
from codex_hook_state import launch_overrides


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="ローカルのsnapshot保存先")
    parser.add_argument("--use-local-state", action="store_true", help="共通入口と同じ起動時設定で確認")
    args = parser.parse_args()
    root = args.root.resolve()
    overrides = launch_overrides(root) if args.use_local_state else []
    proc = subprocess.Popen(["codex", *overrides, "app-server", "--stdio"], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    buffer = b""

    def request(identifier, method, params):
        nonlocal buffer
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}) + "\n").encode())
        proc.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line)
                if message.get("id") == identifier:
                    if "error" in message:
                        raise RuntimeError("Codex APIが読取り要求を拒否しました")
                    return message
                continue
            if selector.select(1):
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("Codex APIが終了しました")
                buffer += chunk
        raise TimeoutError("Codex API読取りtimeout")

    try:
        request(1, "initialize", {"clientInfo": {"name": "crew-hook-inspect", "version": "1"}, "capabilities": {"experimentalApi": True}})
        hooks = request(2, "hooks/list", {"cwds": [str(root)]})
        response = request(3, "config/read", {"cwd": str(root), "includeLayers": True})["result"]
        config = response["config"]
        args.output.write_text(json.dumps(hooks, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"snapshot": str(args.output), "notify": config.get("notify"), "hooks_feature": config.get("features", {}).get("hooks"), "hooks": [
            {k: h.get(k) for k in ("source", "eventName", "enabled", "trustStatus")}
            for entry in hooks["result"]["data"] for h in entry["hooks"]
        ]}, ensure_ascii=False, indent=2))
    finally:
        selector.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    main()
