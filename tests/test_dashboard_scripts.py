"""
tests/test_dashboard_scripts.py — dashboard/start.sh・stop.sh・restart.sh の結合テスト

オーナー要望（毎回手動でプロセスをkillするのが面倒）に応えて追加した運用スクリプトを、
実際にサブプロセスとしてサーバを起動・停止させて検証する。本物の ~/.claude/stonefish や
本番ポート8787には一切触れず、空きポート・tmp_path のデータディレクトリを都度使う。
"""
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).parent.parent
START_SH = REPO_DIR / "dashboard" / "start.sh"
STOP_SH = REPO_DIR / "dashboard" / "stop.sh"
RESTART_SH = REPO_DIR / "dashboard" / "restart.sh"


def _free_port() -> int:
    """OSに空きポートを1つ割ってもらい、すぐ解放して番号だけ返す（テスト間の競合を避ける）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _health(port: int, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return None


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    return predicate()


def _run_script(script: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30, env=env)


@pytest.fixture
def script_env(tmp_path, monkeypatch):
    """空きポート・専用データディレクトリを使う環境変数セットを用意し、
    テスト終了時は生死を問わず必ず stop.sh で後始末する。"""
    port = _free_port()
    data_dir = tmp_path / "data"
    env = dict(os.environ)
    env["STONEFISH_PORT"] = str(port)
    env["STONEFISH_DATA_DIR"] = str(data_dir)

    yield {"port": port, "data_dir": data_dir, "env": env}

    # テストが失敗して停止できていなくても、後続テストにプロセスを残さない
    subprocess.run(["bash", str(STOP_SH)], capture_output=True, text=True, timeout=30, env=env)


def test_scripts_are_executable():
    for script in (START_SH, STOP_SH, RESTART_SH):
        assert script.is_file()
        assert os.access(script, os.X_OK), f"{script} に実行権限が無い"


def test_bash_syntax_check():
    for script in (START_SH, STOP_SH, RESTART_SH):
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, f"{script}: {result.stderr}"


def test_start_then_health_ok_then_pid_file_written(script_env):
    result = _run_script(START_SH, script_env["env"])
    assert result.returncode == 0, result.stderr

    health = _wait_until(lambda: _health(script_env["port"]))
    assert health is not None, "start.sh後にサーバが応答しない"
    assert health["ok"] is True

    pid_file = script_env["data_dir"] / "server.pid"
    assert pid_file.is_file()
    pid = int(pid_file.read_text().strip())
    os.kill(pid, 0)  # 例外が出なければ生存確認OK


def test_start_twice_does_not_spawn_second_process(script_env):
    first = _run_script(START_SH, script_env["env"])
    assert first.returncode == 0
    _wait_until(lambda: _health(script_env["port"]))
    pid_after_first = int((script_env["data_dir"] / "server.pid").read_text().strip())

    second = _run_script(START_SH, script_env["env"])
    assert second.returncode == 0
    assert "既に" in second.stderr or "already" in second.stderr.lower()

    pid_after_second = int((script_env["data_dir"] / "server.pid").read_text().strip())
    assert pid_after_first == pid_after_second


def test_stop_terminates_process_and_removes_pid_file(script_env):
    _run_script(START_SH, script_env["env"])
    _wait_until(lambda: _health(script_env["port"]))
    pid = int((script_env["data_dir"] / "server.pid").read_text().strip())

    result = _run_script(STOP_SH, script_env["env"])
    assert result.returncode == 0, result.stderr

    assert _wait_until(lambda: _health(script_env["port"]) is None, timeout=5.0) is True
    assert not (script_env["data_dir"] / "server.pid").exists()

    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_stop_when_nothing_running_is_a_safe_noop(script_env):
    result = _run_script(STOP_SH, script_env["env"])
    assert result.returncode == 0
    assert "見つかりませんでした" in result.stderr or "not found" in result.stderr.lower()


def test_stop_falls_back_to_port_lookup_when_pid_file_missing(script_env):
    """PIDファイルが失われても（削除・破損など）、ポート検索で確実に止められること。"""
    _run_script(START_SH, script_env["env"])
    _wait_until(lambda: _health(script_env["port"]))

    (script_env["data_dir"] / "server.pid").unlink()

    result = _run_script(STOP_SH, script_env["env"])
    assert result.returncode == 0
    assert _wait_until(lambda: _health(script_env["port"]) is None, timeout=5.0) is True


def test_restart_starts_fresh_server_when_none_running(script_env):
    result = _run_script(RESTART_SH, script_env["env"])
    assert result.returncode == 0, result.stderr
    health = _wait_until(lambda: _health(script_env["port"]))
    assert health is not None


def test_restart_replaces_running_process_with_new_pid(script_env):
    _run_script(START_SH, script_env["env"])
    _wait_until(lambda: _health(script_env["port"]))
    old_pid = int((script_env["data_dir"] / "server.pid").read_text().strip())

    result = _run_script(RESTART_SH, script_env["env"])
    assert result.returncode == 0, result.stderr

    health = _wait_until(lambda: _health(script_env["port"]))
    assert health is not None

    new_pid = int((script_env["data_dir"] / "server.pid").read_text().strip())
    assert new_pid != old_pid
    with pytest.raises(ProcessLookupError):
        os.kill(old_pid, 0)


def test_stop_sends_sigterm_not_sigkill_first(script_env, monkeypatch):
    """安全な停止（SIGTERM優先）であることをプロセス側の受信シグナルで確認する。

    aiohttpのweb.run_appはSIGTERM/SIGINTでgraceful shutdownするため、通常は
    SIGTERMだけで即座に終了する。ここでは stop.sh がまず SIGTERM を送っている
    ことをソースの記述で保証する（実行時にシグナル種別を外部から判別するのは
    困難なため、スクリプト本文にSIGKILLへのフォールバックが「待機後」に限定
    されていることを確認する静的チェックで代替する）。
    """
    content = STOP_SH.read_text(encoding="utf-8")
    assert "kill -9" in content  # フォールバックとして存在する
    # kill -9 より先に（後述しない箇所で）通常の kill が呼ばれていること
    assert content.index('kill "$pid"') < content.index("kill -9")
