#!/usr/bin/env python3
"""
enrich.py — イベント封筒への部門・ペルソナ付与（純粋関数のみ）

STONEFISH ダッシュボードが受信する hook イベント（emit_event.py が送る封筒）に、
どの部門（product/invest/other）・どのペルソナ（Yuki/Alex/Riku...）に紐づくかを
付与するための変換ロジックをまとめる。M1（受信サーバ）・M2（SPA実データ化）双方から
再利用するため、標準ライブラリのみで完結させ、副作用（I/O・ネットワーク）を持たない。

部門マッピングは scripts/token-report.py の DEPARTMENTS と同一規則
（プロジェクトディレクトリ名／cwd への部分一致・上から順に最初に一致したものを採用）を踏襲する。
"""
from __future__ import annotations

# cwd への部分一致 → 部門名。上から順に最初に一致したものを採用する。
# どれにも一致しない場合は DEFAULT_DEPARTMENT に分類する。
# scripts/token-report.py の DEPARTMENTS と同一規則（QA Sprint-24 指摘: 汎用語の
# 部分一致は誤マッチしやすいため、部門追加時はリポジトリ名など固有の文字列を使うこと）。
DEPARTMENTS: list[tuple[str, str]] = [
    ("agent-crew", "product"),
    ("alpha-predict", "invest"),
]
DEFAULT_DEPARTMENT = "other"

# subagent type（前方一致含む） → プロトタイプのペルソナ id。
# 上から順に最初に一致したものを採用する。
# 注: 参謀長（coo）と PM（pm）はプロトタイプ上で Yuki に統合されている。
_PERSONA_EXACT: dict[str, str] = {
    "pm": "yuki",
    "coo": "yuki",
    "architect": "alex",
    "qa": "sora",
    "retro": "miyu",
    "security": "kai",
    "ux-designer": "mina",
    "devops": "tomo",
    "doc-reviewer": "hana",
    "data-analyst": "ren",
}
_PERSONA_PREFIX: list[tuple[str, str]] = [
    ("engineer-", "riku"),
]


def department_for(cwd: str) -> str:
    """cwd（プロジェクトディレクトリパス）から部門名を判定する。"""
    for pattern, dept in DEPARTMENTS:
        if pattern in cwd:
            return dept
    return DEFAULT_DEPARTMENT


def _extract_subagent_type(payload: dict) -> str | None:
    """payload から subagent type を探す。

    優先順位: agent_type → subagent_type → tool_input.subagent_type
    """
    value = payload.get("agent_type")
    if isinstance(value, str) and value:
        return value

    value = payload.get("subagent_type")
    if isinstance(value, str) and value:
        return value

    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        value = tool_input.get("subagent_type")
        if isinstance(value, str) and value:
            return value

    return None


def persona_for(payload: dict) -> str | None:
    """payload から subagent type を取り出し、対応するペルソナ id を返す。

    一致しない・type が見つからない場合は None。
    """
    subagent_type = _extract_subagent_type(payload)
    if subagent_type is None:
        return None

    if subagent_type in _PERSONA_EXACT:
        return _PERSONA_EXACT[subagent_type]

    for prefix, persona in _PERSONA_PREFIX:
        if subagent_type.startswith(prefix):
            return persona

    return None


def enrich(envelope: dict) -> dict:
    """封筒に dept（cwd から）と persona を追加して返す。

    envelope 自体は変更せず、新しい dict を返す。
    """
    result = dict(envelope)
    cwd = envelope.get("cwd") or ""
    result["dept"] = department_for(cwd)
    result["persona"] = persona_for(envelope.get("payload") or {})
    return result
