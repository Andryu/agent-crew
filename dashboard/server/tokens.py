#!/usr/bin/env python3
"""
tokens.py — 実行中セッションの transcript JSONL から部門別トークン使用量を集計する

scripts/token-report.py と同一の重複排除規則（同一 message.id は複数行に分かれて
出現するため、最新タイムスタンプの行だけを採用する）を、サーバのポーリングに合わせて
増分読み対応させたもの。ライブラリ依存なし・副作用は transcript ファイルの読み込みのみ。

## 重複排除規則（token-report.py と同一・忘れると2〜5倍水増しする既知の罠）
1つの assistant API 呼び出しは、thinking/tool_use などの content ブロックごとに
複数行へ分割されて記録され、同一の message.id を持つ。usage はストリーミング途中経過
のため行ごとに値が異なる（後の行ほど値が大きい）。そのため message.id ごとに
「最も新しいタイムスタンプの行」だけを採用する。

## 増分読み（tail）
transcript ごとにバイトオフセットを保持し、次回 poll() では前回オフセット以降だけを
読む。読み込んだチャンクの末尾が改行で終わっていない場合、その最後の行は書き込み途中
（不完全行）とみなしてオフセットを進めず、次回の poll() でチャンクの続きと結合して
再度読み直す。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_DEPARTMENT = "other"


def _log(message: str) -> None:
    print(f"[stonefish] {message}", file=sys.stderr)


def parse_timestamp(raw: str) -> Optional[datetime]:
    """ISO8601（末尾Z、小数秒1〜6桁あり/なし）を aware datetime (UTC) に変換する。失敗時は None。"""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _usage_totals(usage: dict) -> tuple[int, int, int]:
    """usage dict から (input, output, cache) の3値を取り出す。cache は creation+read の合算。"""
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cache_tokens = int(usage.get("cache_creation_input_tokens") or 0) + int(
        usage.get("cache_read_input_tokens") or 0
    )
    return input_tokens, output_tokens, cache_tokens


class TranscriptAggregator:
    """複数 transcript JSONL を監視し、部門別トークン使用量を増分集計する。"""

    def __init__(self) -> None:
        self._depts: dict[str, str] = {}  # transcript_path -> dept
        self._offsets: dict[str, int] = {}  # transcript_path -> 次回読み出し開始バイト位置
        # message.id -> (最新timestamp, (input, output, cache), dept)
        # dept は「その message.id を記録した時点の transcript の所属部門」を保持する。
        self._entries: dict[str, tuple[datetime, tuple[int, int, int], str]] = {}

    def register(self, transcript_path: str, dept: str) -> None:
        """監視対象の transcript を追加する。既知の path は dept のみ更新する（オフセットは維持）。"""
        self._depts[transcript_path] = dept
        self._offsets.setdefault(transcript_path, 0)

    def poll(self) -> bool:
        """登録済みの全 transcript を増分読みする。1件でも新規/更新 usage があれば True。"""
        changed = False
        for transcript_path in list(self._offsets.keys()):
            if self._poll_one(transcript_path):
                changed = True
        return changed

    def _poll_one(self, transcript_path: str) -> bool:
        offset = self._offsets[transcript_path]
        dept = self._depts.get(transcript_path, DEFAULT_DEPARTMENT)

        try:
            with open(transcript_path, "rb") as fh:
                fh.seek(offset)
                chunk = fh.read()
        except OSError as e:
            _log(f"transcript 読み込み失敗（次回リトライ）: {transcript_path}: {e}")
            return False

        if not chunk:
            return False

        # バイト単位で改行分割し、末尾が不完全行なら消費バイト数から除外して次回に持ち越す。
        parts = chunk.split(b"\n")
        if chunk.endswith(b"\n"):
            complete_parts = parts[:-1]
            consumed = len(chunk)
        else:
            complete_parts = parts[:-1]
            consumed = len(chunk) - len(parts[-1])

        changed = False
        for raw_line in complete_parts:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            message = record.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue

            message_id = message.get("id")
            ts_raw = record.get("timestamp")
            ts = parse_timestamp(ts_raw) if isinstance(ts_raw, str) else None
            if not message_id or ts is None:
                continue

            totals = _usage_totals(usage)
            existing = self._entries.get(message_id)
            if existing is None or ts > existing[0]:
                self._entries[message_id] = (ts, totals, dept)
                changed = True

        self._offsets[transcript_path] = offset + consumed
        return changed

    def totals(self) -> dict:
        """id→(ts, totals, dept) の全エントリから部門別合計を再計算して返す。

        {"product": {"input": N, "output": N, "cache": N, "total": N}, ...}
        """
        result: dict[str, dict[str, int]] = {}
        for _ts, (input_tokens, output_tokens, cache_tokens), dept in self._entries.values():
            bucket = result.setdefault(dept, {"input": 0, "output": 0, "cache": 0, "total": 0})
            bucket["input"] += input_tokens
            bucket["output"] += output_tokens
            bucket["cache"] += cache_tokens
            bucket["total"] += input_tokens + output_tokens + cache_tokens
        return result
