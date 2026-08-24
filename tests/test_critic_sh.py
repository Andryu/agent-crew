"""
tests/test_critic_sh.py — scripts/critic.sh（従量 API critic ラッパ、ADR-018）の結合テスト

本物の API は叩かない。--dry-run でリクエスト JSON の形を検証し、
ローカルの偽 SSE サーバに CRITIC_API_URL を向けて成果物 md の生成を検証する。
API キーはダミー文字列のみ使い、~/.config や リポジトリの .env は CRITIC_NO_ENV_FILES=1 で読ませない。
"""
import json
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).parent.parent
CRITIC_SH = REPO_DIR / "scripts" / "critic.sh"


def _base_env(tmp_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["HOME"] = str(tmp_path)  # ~/.config/agent-crew/critic.env を読ませない
    env["CRITIC_NO_ENV_FILES"] = "1"
    return env


def _run(args, env, cwd=REPO_DIR):
    return subprocess.run(
        ["bash", str(CRITIC_SH), *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=60
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------- dry-run ----------

def test_dry_run_emits_request_json_without_key(tmp_path):
    target = tmp_path / "plan.md"
    target.write_text("# ミニADR\n決定: X を採用\n", encoding="utf-8")
    ctx = tmp_path / "ctx.md"
    ctx.write_text("関連ファイルの中身", encoding="utf-8")

    r = _run(["--target", str(target), "--ctx", str(ctx), "--dry-run"], _base_env(tmp_path))
    assert r.returncode == 0, r.stderr
    req = json.loads(r.stdout)
    assert req["model"] == "claude-opus-5"
    assert req["stream"] is True
    assert req["thinking"] == {"type": "adaptive"}
    assert req["output_config"]["effort"] == "xhigh"
    assert "budget_tokens" not in json.dumps(req)
    assert "temperature" not in req
    # critic.md の本文が system に流用され、frontmatter は除去されている
    assert "Kagami" in req["system"]
    assert "name: critic" not in req["system"]
    assert "従量 API から呼ばれている" in req["system"]
    # 対象と添付が user メッセージに含まれる
    user = req["messages"][0]["content"]
    assert "決定: X を採用" in user
    assert "関連ファイルの中身" in user
    assert str(ctx) in user
    # dry-run では成果物を書かない
    assert not (REPO_DIR / "docs" / "plans" / "plan-critic.md").exists()


def test_dry_run_respects_model_effort_overrides(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("x", encoding="utf-8")
    env = _base_env(tmp_path)
    env["CRITIC_MODEL"] = "claude-sonnet-5"
    env["CRITIC_EFFORT"] = "high"
    env["CRITIC_FALLBACK"] = "1"
    r = _run(["--target", str(target), "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    req = json.loads(r.stdout)
    assert req["model"] == "claude-sonnet-5"
    assert req["output_config"]["effort"] == "high"
    assert req["fallbacks"] == "default"


# ---------- エラー系 ----------

def test_missing_key_exits_1_with_guidance(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("x", encoding="utf-8")
    r = _run(["--target", str(target)], _base_env(tmp_path))
    assert r.returncode == 1
    assert "ANTHROPIC_API_KEY" in r.stderr
    assert "export しない" in r.stderr


def test_ctx_size_limit_blocks_before_sending(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("a" * 500, encoding="utf-8")
    env = _base_env(tmp_path)
    env["CRITIC_MAX_CTX_BYTES"] = "100"
    r = _run(["--target", str(target), "--dry-run"], env)
    assert r.returncode == 1
    assert "上限" in r.stderr


def test_missing_target_exits_1(tmp_path):
    r = _run(["--target", str(tmp_path / "nope.md")], _base_env(tmp_path))
    assert r.returncode == 1


# ---------- 偽 SSE サーバで成果物生成を検証 ----------

SSE_EVENTS = [
    {"type": "message_start", "message": {"model": "claude-opus-5", "usage": {"input_tokens": 1234, "cache_read_input_tokens": 0}}},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "### 反証レビュー対象\n決定X\n\n### 反証命題\n"}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "1. 前提が壊れる — 強さ: 強(CRITICAL)\n   根拠: 未確認（添付なし）\n"}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "2. 小さな穴 — 強さ: 弱(MINOR)\n\n### 総合判定\n条件付き差し戻し（条件: 前提を明記）\n"}},
    {"type": "content_block_stop", "index": 0},
    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 321}},
    {"type": "message_stop"},
]


class _Handler(BaseHTTPRequestHandler):
    received = {}

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        _Handler.received["body"] = json.loads(body)
        _Handler.received["headers"] = {k.lower(): v for k, v in self.headers.items()}
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for ev in SSE_EVENTS:
            self.wfile.write(f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def log_message(self, *args):  # 静かに
        pass


@pytest.fixture
def fake_api():
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}/v1/messages"
    finally:
        server.shutdown()


def test_generates_critic_md_from_sse(tmp_path, fake_api):
    target = tmp_path / "2026-08-17-sample.md"
    target.write_text("# plan\n決定X\n", encoding="utf-8")
    out = tmp_path / "out" / "sample-critic.md"
    env = _base_env(tmp_path)
    env["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    env["CRITIC_API_URL"] = fake_api

    r = _run(["--target", str(target), "--slug", "sample", "--out", str(out)], env)
    assert r.returncode == 0, r.stderr + r.stdout
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "# critic: sample" in text
    assert "claude-opus-5" in text
    assert "input=1234" in text and "output=321" in text
    assert "CRITICAL 件数（近似・要目視）**: 1" in text
    assert "条件付き差し戻し" in text
    assert "強さ: 強(CRITICAL)" in text  # 本文がそのまま残る
    # 鍵はヘッダでのみ送られ、本文には含まれない
    assert _Handler.received["headers"]["x-api-key"] == "sk-ant-dummy"
    assert "sk-ant-dummy" not in json.dumps(_Handler.received["body"])
    assert "anthropic-beta" not in _Handler.received["headers"]  # 既定ではフォールバック beta を送らない
    # 成果物のパスが標準出力に出る
    assert str(out) in r.stdout


def test_default_out_path_uses_docs_plans_and_does_not_overwrite(tmp_path, fake_api):
    # 出力先の既定は <repo>/docs/plans/<slug>-critic.md。既存なら -2 を付ける。
    # リポジトリを汚さないよう一時 git リポジトリの中で実行する（critic.sh は git rev-parse で root を決める）。
    repo = tmp_path / "repo"
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / "docs" / "plans").mkdir(parents=True)
    (repo / ".claude" / "agents" / "critic.md").write_text(
        (REPO_DIR / ".claude" / "agents" / "critic.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    target = repo / "docs" / "plans" / "2026-08-17-x.md"
    target.write_text("# plan x\n", encoding="utf-8")
    env = _base_env(tmp_path)
    env["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    env["CRITIC_API_URL"] = fake_api

    r1 = _run(["--target", str(target)], env, cwd=repo)
    assert r1.returncode == 0, r1.stderr
    first = repo / "docs" / "plans" / "2026-08-17-x-critic.md"
    assert first.exists()
    first_content = first.read_text(encoding="utf-8")
    r2 = _run(["--target", str(target)], env, cwd=repo)
    assert r2.returncode == 0, r2.stderr
    assert (repo / "docs" / "plans" / "2026-08-17-x-critic-2.md").exists()
    assert first.read_text(encoding="utf-8") == first_content  # 1回目の成果物は上書きされていない


def test_auto_attach_referenced_paths_and_skip_over_limit(tmp_path):
    # 対象 md 内で参照されるリポジトリ内パスは自動添付され、上限を超える分は見送って dry-run 出力に件数が出る
    repo = tmp_path / "repo"
    (repo / ".claude" / "agents").mkdir(parents=True)
    (repo / ".claude" / "agents" / "critic.md").write_text(
        (REPO_DIR / ".claude" / "agents" / "critic.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "small.md").write_text("small-content", encoding="utf-8")
    (repo / "big.md").write_text("B" * 5000, encoding="utf-8")
    target = repo / "plan.md"
    target.write_text("参照: `small.md` と [big](big.md) と `missing.md`\n", encoding="utf-8")
    env = _base_env(tmp_path)
    env["CRITIC_MAX_CTX_BYTES"] = "4000"  # big.md は入らない
    r = _run(["--target", str(target), "--dry-run"], env, cwd=repo)
    assert r.returncode == 0, r.stderr
    req = json.loads(r.stdout)
    user = req["messages"][0]["content"]
    assert "small-content" in user
    assert "BBBB" not in user
    assert "添付 1 件（自動 1 件）、見送り 1 件" in r.stderr
    # --no-auto-ctx で無効化
    r2 = _run(["--target", str(target), "--dry-run", "--no-auto-ctx"], env, cwd=repo)
    assert "small-content" not in json.loads(r2.stdout)["messages"][0]["content"]
