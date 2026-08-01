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
