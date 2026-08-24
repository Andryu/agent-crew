"""10-subagent-tokens holdout: discovery / tokens の純ロジックの振る舞いテスト。

- BENCH_WORK_DIR の解答済みリポジトリから discovery.py / tokens.py を import する。
- トークン数・ID・時刻は BENCH_SEED から乱数生成し、期待値はテスト側で独立計算する。
- 疑似 projects ツリーを tmp_path に組み立て、mtime は os.utime と now 引数で制御する。
"""
import importlib.util
import json
import os
import random
import sys
from pathlib import Path

WORK = Path(os.environ["BENCH_WORK_DIR"])
SEED = int(os.environ.get("BENCH_SEED", "12345"))
rng = random.Random(SEED)

NOW = 1_800_000_000.0 + rng.randint(0, 10 ** 6)
WINDOW = 600.0
CWD = "/Users/benchuser{}/Workspace/agent-crew".format(rng.randint(0, 9999))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(WORK / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses 等がモジュールを参照できるよう登録する
    spec.loader.exec_module(mod)
    return mod


discovery = _load("bench_discovery", "dashboard/server/discovery.py")
tokens = _load("bench_tokens", "dashboard/server/tokens.py")


# ---------- 疑似 projects ツリー構築ヘルパー ----------

def make_root(tmp_path):
    root = tmp_path / "projects"
    proj = root / "-Users-benchuser-Workspace-agent-crew"
    proj.mkdir(parents=True)
    return root, proj


def asst_line(message_id, inp, out, cache, ts):
    return json.dumps({
        "message": {
            "role": "assistant",
            "id": message_id,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_creation_input_tokens": cache,
                "cache_read_input_tokens": 0,
            },
        },
        "timestamp": ts,
    }) + "\n"


def write_main(proj, session_id, cwd=CWD, age=10.0):
    p = proj / (session_id + ".jsonl")
    p.write_text(json.dumps({"cwd": cwd}) + "\n", encoding="utf-8")
    os.utime(p, (NOW - age, NOW - age))
    return p


def write_subagent(proj, session_id, agent_id, meta_text="__default__",
                   age=10.0, body=None):
    """meta_text: "__default__"=正常な meta / None=meta無し / それ以外=その内容で書く"""
    d = proj / session_id / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("agent-" + agent_id + ".jsonl")
    p.write_text(body or asst_line("msg_" + agent_id, 1, 1, 0,
                                   "2026-08-02T00:00:00.000Z"), encoding="utf-8")
    if meta_text == "__default__":
        meta_text = json.dumps({"agentType": "qa", "name": "n"})
    if meta_text is not None:
        (d / ("agent-" + agent_id + ".meta.json")).write_text(meta_text, encoding="utf-8")
    os.utime(p, (NOW - age, NOW - age))
    return p


def find(root):
    return discovery.find_active_sessions(root, WINDOW, now=NOW)


# ---------- 回帰: 親時点の挙動が壊れていないこと ----------

def test_regression_main_session_discovery(tmp_path):
    """メインセッションの発見・ウィンドウ・cwd 無しの除外は今まで通りであること。"""
    root, proj = make_root(tmp_path)
    write_main(proj, "sess-fresh", age=10.0)
    write_main(proj, "sess-old", age=WINDOW + 100.0)
    stale = proj / "sess-nocwd.jsonl"
    stale.write_text(json.dumps({"foo": "bar"}) + "\n", encoding="utf-8")
    os.utime(stale, (NOW - 5.0, NOW - 5.0))

    sessions = find(root)
    ids = sorted(s.session_id for s in sessions)
    assert ids == ["sess-fresh"]
    (only,) = sessions
    assert only.cwd == CWD
    assert only.dept == "product"
    assert only.transcript_path.endswith("sess-fresh.jsonl")


def test_regression_aggregator_backcompat(tmp_path):
    """register 2引数・totals() の形・message.id 重複排除は今まで通りであること。"""
    inp = rng.randint(10, 500)
    out = rng.randint(10, 500)
    cache = rng.randint(10, 500)
    t1 = tmp_path / "t1.jsonl"
    t1.write_text(
        # 同一 message.id の2行（後の行ほど新しく値が大きい）→ 最新の行だけ採用
        asst_line("msg_dup", 1, 1, 1, "2026-08-02T00:00:00.000Z")
        + asst_line("msg_dup", inp, out, cache, "2026-08-02T00:00:05.000Z"),
        encoding="utf-8",
    )

    agg = tokens.TranscriptAggregator()
    agg.register(str(t1), "product")  # 従来どおり2引数で呼べること
    assert agg.poll() is True
    totals = agg.totals()
    assert totals["product"] == {
        "input": inp, "output": out, "cache": cache,
        "total": inp + out + cache,
    }
    # 再ポーリングしても二重計上しない
    agg.poll()
    assert agg.totals()["product"]["total"] == inp + out + cache


# ---------- (a) サブエージェント発見とペルソナ解決 ----------

def test_subagent_discovery_with_persona(tmp_path):
    root, proj = make_root(tmp_path)
    write_main(proj, "sess-1")
    write_subagent(proj, "sess-1", "aaa",
                   meta_text=json.dumps({"agentType": "qa"}))
    write_subagent(proj, "sess-1", "bbb",
                   meta_text=json.dumps({"agentType": "engineer-go"}))

    sessions = find(root)
    by_path = {s.transcript_path: s for s in sessions}
    main = next(s for s in sessions if s.session_id == "sess-1")
    subs = [s for s in sessions if s.session_id != "sess-1"]

    assert main.persona is None  # メインセッションは常に None
    assert len(subs) == 2
    personas = sorted(s.persona for s in subs)
    assert personas == ["riku", "sora"]  # engineer-go / qa の解決結果
    for s in subs:
        assert s.cwd == CWD  # 親の cwd を引き継ぐ
        assert s.dept == "product"  # 親の部門を引き継ぐ
        assert "sess-1" in s.session_id and s.session_id != "sess-1"
        assert "subagents" in s.transcript_path
    assert len(by_path) == 3  # 3セッションすべて別 transcript


# ---------- (b) meta.json 欠落・壊れ・非文字列でも persona=None で登録 ----------

def test_meta_missing_or_broken_persona_none(tmp_path):
    root, proj = make_root(tmp_path)
    write_main(proj, "sess-1")
    write_subagent(proj, "sess-1", "nometa", meta_text=None)
    write_subagent(proj, "sess-1", "broken", meta_text="not json {{{")
    write_subagent(proj, "sess-1", "nonstr",
                   meta_text=json.dumps({"agentType": 42}))
    write_subagent(proj, "sess-1", "nondict", meta_text=json.dumps([1, 2]))

    sessions = find(root)
    subs = [s for s in sessions if s.session_id != "sess-1"]
    assert len(subs) == 4  # 4件とも落とさず発見される
    assert all(s.persona is None for s in subs)


# ---------- (c) サブエージェント自身の mtime 窓 ----------

def test_subagent_mtime_window(tmp_path):
    root, proj = make_root(tmp_path)
    write_main(proj, "sess-1", age=10.0)
    write_subagent(proj, "sess-1", "fresh", age=10.0)
    write_subagent(proj, "sess-1", "stale", age=WINDOW + 100.0)

    sessions = find(root)
    ids = sorted(s.session_id for s in sessions)
    # 前提確認: 新しいサブエージェントは発見される（機能が存在すること）
    assert any("fresh" in i for i in ids), "サブエージェント発見が実装されていない"
    # 本題: 古いサブエージェントは親がアクティブでも発見されない
    assert not any("stale" in i for i in ids)
    assert "sess-1" in ids


# ---------- (d) persona_totals は None を除外 ----------

def test_persona_totals_excludes_none(tmp_path):
    m_in = rng.randint(10, 500)
    m_out = rng.randint(10, 500)
    s_in = rng.randint(10, 500)
    s_out = rng.randint(10, 500)

    main_t = tmp_path / "main.jsonl"
    main_t.write_text(asst_line("msg_main", m_in, m_out, 0,
                                "2026-08-02T00:00:00.000Z"), encoding="utf-8")
    sub_t = tmp_path / "sub.jsonl"
    sub_t.write_text(asst_line("msg_sub", s_in, s_out, 0,
                               "2026-08-02T00:00:00.000Z"), encoding="utf-8")

    agg = tokens.TranscriptAggregator()
    agg.register(str(main_t), "product")            # persona 未解決（メイン）
    agg.register(str(sub_t), "product", "riku")     # persona あり（サブ）
    agg.poll()

    personas = agg.persona_totals()
    assert sorted(personas.keys()) == ["riku"]  # None 分は載らない
    assert personas["riku"] == {
        "input": s_in, "output": s_out, "cache": 0, "total": s_in + s_out,
    }
    # 部門別 totals には両方が入る（後方互換）
    assert agg.totals()["product"]["total"] == m_in + m_out + s_in + s_out


# ---------- (g) 同一 message.id はペルソナ集計でも二重計上しない ----------

def test_dedupe_across_polls_with_persona(tmp_path):
    first_in = rng.randint(10, 200)
    final_in = first_in + rng.randint(10, 200)
    final_out = rng.randint(10, 200)

    sub_t = tmp_path / "sub.jsonl"
    sub_t.write_text(asst_line("msg_x", first_in, 1, 0,
                               "2026-08-02T00:00:00.000Z"), encoding="utf-8")

    agg = tokens.TranscriptAggregator()
    agg.register(str(sub_t), "product", "sora")
    agg.poll()

    # 同じ message.id のより新しい行が追記される（ストリーミング途中経過の続き）
    with open(sub_t, "a", encoding="utf-8") as fh:
        fh.write(asst_line("msg_x", final_in, final_out, 0,
                           "2026-08-02T00:00:10.000Z"))
    agg.poll()

    assert agg.persona_totals()["sora"] == {
        "input": final_in, "output": final_out, "cache": 0,
        "total": final_in + final_out,
    }
