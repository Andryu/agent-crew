"""10-subagent-tokens holdout（加点）: サーバ WS 経由で "personas" が配信されること。

aiohttp が無い環境では skip される（採点上は加点対象外として扱う）。
pytest-asyncio 等のプラグインに依存しないよう、asyncio.run で自前実行する。
"""
import importlib.util
import json
import os
import random
import sys
from pathlib import Path

import pytest

WORK = Path(os.environ["BENCH_WORK_DIR"])
SEED = int(os.environ.get("BENCH_SEED", "12345"))
rng = random.Random(SEED)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(WORK / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_ws_init_and_tokens_include_personas(tmp_path):
    pytest.importorskip("aiohttp")
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer

    server_module = _load("bench_server", "dashboard/server/server.py")

    s_in = rng.randint(10, 500)
    s_out = rng.randint(10, 500)

    # 疑似 projects ツリー（実時刻 mtime のままなのでアクティブ扱いになる）
    projects_root = tmp_path / "claude-projects"
    proj = projects_root / "-Users-benchuser-agent-crew"
    proj.mkdir(parents=True)
    real_cwd = tmp_path / "agent-crew"
    real_cwd.mkdir()

    (proj / "sess-1.jsonl").write_text(
        json.dumps({"cwd": str(real_cwd)}) + "\n", encoding="utf-8")
    subdir = proj / "sess-1" / "subagents"
    subdir.mkdir(parents=True)
    (subdir / "agent-abc.jsonl").write_text(
        json.dumps({
            "message": {
                "role": "assistant",
                "id": "msg_sub",
                "usage": {"input_tokens": s_in, "output_tokens": s_out,
                          "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0},
            },
            "timestamp": "2026-08-02T00:00:00.000Z",
        }) + "\n", encoding="utf-8")
    (subdir / "agent-abc.meta.json").write_text(
        json.dumps({"agentType": "engineer-go"}), encoding="utf-8")

    server_module.PROJECTS_ROOT = projects_root

    async def run():
        app = server_module.build_app(tmp_path / "data")
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            ws = await client.ws_connect("/ws")
            # 初期メッセージに personas キーがあること
            init_msg = await asyncio.wait_for(ws.receive_json(), timeout=10)
            assert init_msg["type"] == "init"
            assert "personas" in init_msg

            # 背景ポーリングが discovery→集計するまで personas の中身を待つ
            personas = init_msg["personas"]
            deadline = asyncio.get_event_loop().time() + 12
            while "riku" not in personas:
                if asyncio.get_event_loop().time() > deadline:
                    raise AssertionError("personas に riku が現れない: %r" % personas)
                try:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=5)
                except asyncio.TimeoutError:
                    continue
                if isinstance(msg, dict) and "personas" in msg:
                    personas = msg["personas"]
            assert personas["riku"]["input"] == s_in
            assert personas["riku"]["output"] == s_out
            await ws.close()
        finally:
            await client.close()

    asyncio.run(run())
