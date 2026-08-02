"""
tests/test_dashboard_enrich.py — dashboard/server/enrich.py ユニットテスト

部門マッピング（DEPARTMENTS と同一規則）・ペルソナマッピングの規則を検証する。
純粋関数のみで構成されるため、モック不要。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard" / "server"))

from enrich import department_for, enrich, persona_for  # noqa: E402

# ---------- department_for ----------


def test_department_for_agent_crew():
    assert department_for("/Users/andryu/Workspace/agent-crew") == "product"


def test_department_for_alpha_predict():
    assert department_for("/Users/andryu/Workspace/alpha-predict-jp") == "invest"


def test_department_for_other():
    assert department_for("/Users/andryu/Workspace/bookmark-api") == "other"


def test_department_for_order_first_match_wins():
    """両方のパターンを含むパスは、DEPARTMENTS の先頭（agent-crew）が優先される"""
    assert department_for("/Users/andryu/Workspace/agent-crew/alpha-predict-sub") == "product"


def test_department_for_empty_cwd():
    assert department_for("") == "other"


# ---------- persona_for ----------


def test_persona_for_pm():
    assert persona_for({"agent_type": "pm"}) == "yuki"


def test_persona_for_coo():
    assert persona_for({"agent_type": "coo"}) == "yuki"


def test_persona_for_engineer_go_prefix():
    assert persona_for({"agent_type": "engineer-go"}) == "riku"


def test_persona_for_engineer_next_prefix():
    assert persona_for({"agent_type": "engineer-next"}) == "riku"


def test_persona_for_subagent_type_field():
    assert persona_for({"subagent_type": "qa"}) == "sora"


def test_persona_for_tool_input_subagent_type():
    """agent_type/subagent_type が無く、tool_input.subagent_type から拾えるケース"""
    payload = {"tool_input": {"subagent_type": "architect"}}
    assert persona_for(payload) == "alex"


def test_persona_for_priority_agent_type_over_tool_input():
    """agent_type がある場合はそちらを優先する"""
    payload = {"agent_type": "security", "tool_input": {"subagent_type": "qa"}}
    assert persona_for(payload) == "kai"


def test_persona_for_unknown_type_returns_none():
    assert persona_for({"agent_type": "unknown-role"}) is None


def test_persona_for_no_type_returns_none():
    assert persona_for({}) is None


def test_persona_for_all_mapped_roles():
    expected = {
        "retro": "miyu",
        "security": "kai",
        "ux-designer": "mina",
        "devops": "tomo",
        "doc-reviewer": "hana",
        "data-analyst": "ren",
    }
    for role, persona in expected.items():
        assert persona_for({"agent_type": role}) == persona


# ---------- persona_for: "<ペルソナ>-<タスク識別子>" 形式（実データで発覚した不具合の再発防止） ----------
# team-lead（オーケストレーション側）はタスク単位でサブエージェントに動的な agent_type
# （例: "riku-m2a"）を付けることがあり、これが _PERSONA_EXACT / _PERSONA_PREFIX の
# どちらにも一致せず persona が常に None になっていた（2026-08-02、実データ接続時に発覚）。


def test_persona_for_dynamic_task_suffix_riku():
    assert persona_for({"agent_type": "riku-m2a"}) == "riku"
    assert persona_for({"agent_type": "riku-m2b"}) == "riku"


def test_persona_for_dynamic_task_suffix_other_personas():
    assert persona_for({"agent_type": "tomo-m3"}) == "tomo"
    assert persona_for({"agent_type": "alex-sprint26"}) == "alex"
    assert persona_for({"agent_type": "miyu-sprint26"}) == "miyu"
    assert persona_for({"agent_type": "yuki-sprint26"}) == "yuki"
    assert persona_for({"agent_type": "sora-qa1"}) == "sora"
    assert persona_for({"agent_type": "kai-audit"}) == "kai"
    assert persona_for({"agent_type": "mina-ux1"}) == "mina"
    assert persona_for({"agent_type": "hana-review"}) == "hana"
    assert persona_for({"agent_type": "ren-data1"}) == "ren"


def test_persona_for_bare_persona_id_without_suffix():
    """ハイフン無しでペルソナidそのものが渡された場合も一致する。"""
    assert persona_for({"agent_type": "riku"}) == "riku"


def test_persona_for_similar_but_unrelated_name_does_not_false_match():
    """ペルソナidを含むが単語境界が異なる無関係な名前には誤マッチしない
    （ハイフン必須の前方一致のため）。"""
    assert persona_for({"agent_type": "kaiser-x"}) is None
    assert persona_for({"agent_type": "renewal-task"}) is None


def test_persona_for_dynamic_suffix_priority_after_exact_and_prefix():
    """_PERSONA_EXACT・_PERSONA_PREFIX の既存規則が先に評価されることに影響しない
    （engineer- 前方一致は引き続き riku にマッピングされる）。"""
    assert persona_for({"agent_type": "engineer-go"}) == "riku"
    assert persona_for({"agent_type": "qa"}) == "sora"


# ---------- enrich ----------


def test_enrich_adds_dept_and_persona():
    envelope = {
        "schema": 1,
        "ts": "2026-08-02T00:00:00.000000Z",
        "hook_event": "SubagentStart",
        "session_id": "abc",
        "cwd": "/Users/andryu/Workspace/agent-crew",
        "payload": {"agent_type": "engineer-go"},
    }
    result = enrich(envelope)
    assert result["dept"] == "product"
    assert result["persona"] == "riku"
    # 元のフィールドは保持される
    assert result["hook_event"] == "SubagentStart"


def test_enrich_does_not_mutate_input():
    envelope = {"cwd": "/Users/andryu/Workspace/agent-crew", "payload": {}}
    enrich(envelope)
    assert "dept" not in envelope


def test_enrich_missing_cwd_defaults_to_other():
    envelope = {"payload": {}}
    result = enrich(envelope)
    assert result["dept"] == "other"
    assert result["persona"] is None
