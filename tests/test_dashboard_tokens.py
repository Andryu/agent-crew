"""
tests/test_dashboard_tokens.py — dashboard/server/tokens.py ユニットテスト

TranscriptAggregator の重複排除（message.id ごとに最新timestampの行のみ採用）・
増分読み（バイトオフセット・不完全行の持ち越し）・部門別集計を検証する。

末尾の実データ検証テストのみ、~/.claude/projects/ 配下の実際の transcript を対象に
する（Sprint-24 教訓: ストリーミングJSONLは実データ確認が必須）。個人のホームディレクトリ
パスをテストコードに直書きしないよう、実行時に Path.home() から動的に解決する。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard" / "server"))

from tokens import TranscriptAggregator  # noqa: E402


def _usage_line(message_id: str, ts: str, input_tokens: int, output_tokens: int,
                 cache_creation: int = 0, cache_read: int = 0) -> str:
    return json.dumps({
        "message": {
            "role": "assistant",
            "id": message_id,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            },
        },
        "timestamp": ts,
    })


# ---------- 重複排除 ----------


def test_duplicate_message_id_keeps_latest_timestamp_only(tmp_path):
    """同一 message.id が複数行（ストリーミング途中経過）に分かれていても、
    最新timestampの行の値のみが採用され、合算で水増しされないこと。"""
    transcript = tmp_path / "session.jsonl"
    lines = [
        _usage_line("msg_1", "2026-08-01T10:00:00.000Z", input_tokens=5, output_tokens=1),
        _usage_line("msg_1", "2026-08-01T10:00:01.000Z", input_tokens=5, output_tokens=3),
        _usage_line("msg_1", "2026-08-01T10:00:02.000Z", input_tokens=5, output_tokens=8),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    agg = TranscriptAggregator()
    agg.register(str(transcript), "product")
    assert agg.poll() is True

    totals = agg.totals()
    # 3行合算なら output=12になってしまう。最新行(output=8)のみが採用されるべき。
    assert totals["product"]["output"] == 8
    assert totals["product"]["input"] == 5
    assert totals["product"]["total"] == 13


def test_out_of_order_lines_still_keep_latest_by_timestamp(tmp_path):
    """行の出現順ではなく timestamp の新しさで判定すること。"""
    transcript = tmp_path / "session.jsonl"
    lines = [
        _usage_line("msg_1", "2026-08-01T10:00:05.000Z", input_tokens=5, output_tokens=99),
        _usage_line("msg_1", "2026-08-01T10:00:01.000Z", input_tokens=5, output_tokens=1),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    agg = TranscriptAggregator()
    agg.register(str(transcript), "product")
    agg.poll()

    assert agg.totals()["product"]["output"] == 99


def test_non_assistant_and_missing_usage_lines_are_ignored(tmp_path):
    transcript = tmp_path / "session.jsonl"
    lines = [
        json.dumps({"message": {"role": "user", "id": "msg_u", "usage": {"input_tokens": 999}},
                    "timestamp": "2026-08-01T10:00:00.000Z"}),
        json.dumps({"message": {"role": "assistant", "id": "msg_no_usage"},
                    "timestamp": "2026-08-01T10:00:00.000Z"}),
        json.dumps({"not_a_message_record": True}),
        "",  # 空行
        _usage_line("msg_ok", "2026-08-01T10:00:00.000Z", input_tokens=7, output_tokens=2),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    agg = TranscriptAggregator()
    agg.register(str(transcript), "other")
    agg.poll()

    totals = agg.totals()
    assert totals["other"]["input"] == 7
    assert totals["other"]["output"] == 2


def test_malformed_json_line_is_skipped_not_fatal(tmp_path):
    transcript = tmp_path / "session.jsonl"
    lines = [
        "{not valid json",
        _usage_line("msg_ok", "2026-08-01T10:00:00.000Z", input_tokens=1, output_tokens=1),
    ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    agg = TranscriptAggregator()
    agg.register(str(transcript), "other")
    assert agg.poll() is True
    assert agg.totals()["other"]["total"] == 2


# ---------- 増分読み（tail） ----------


def test_poll_only_reads_new_bytes_on_second_call(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        _usage_line("msg_1", "2026-08-01T10:00:00.000Z", input_tokens=10, output_tokens=1) + "\n",
        encoding="utf-8",
    )

    agg = TranscriptAggregator()
    agg.register(str(transcript), "product")
    assert agg.poll() is True
    assert agg.totals()["product"]["total"] == 11

    # 2回目の poll は差分なしなので False
    assert agg.poll() is False

    # 追記後は差分ありとして新規 message.id 分だけ加算される
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write(_usage_line("msg_2", "2026-08-01T10:00:01.000Z", input_tokens=20, output_tokens=2) + "\n")

    assert agg.poll() is True
    totals = agg.totals()
    assert totals["product"]["input"] == 30
    assert totals["product"]["output"] == 3


def test_incomplete_trailing_line_is_carried_over(tmp_path):
    """改行で終わっていない末尾行（書き込み途中）は、その回の poll ではカウントされず、
    オフセットも進めず、続きが書き込まれてから正しく合算されること。"""
    transcript = tmp_path / "session.jsonl"
    full_line = _usage_line("msg_1", "2026-08-01T10:00:00.000Z", input_tokens=5, output_tokens=4)
    # 末尾の数文字を欠いた不完全な行として書き込む（改行なし）
    incomplete = full_line[:-5]
    transcript.write_text(incomplete, encoding="utf-8")

    agg = TranscriptAggregator()
    agg.register(str(transcript), "product")
    assert agg.poll() is False  # 不完全行なのでまだ何も採用されない
    assert agg.totals() == {}

    # 欠けていた末尾5文字 + 改行を追記して行を完成させる
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write(full_line[-5:] + "\n")

    assert agg.poll() is True
    assert agg.totals()["product"]["input"] == 5
    assert agg.totals()["product"]["output"] == 4


def test_io_error_on_missing_file_logs_warning_and_continues(tmp_path, capsys):
    """未作成/削除済みの transcript でも例外を投げず、stderr に警告を出して False を返す。"""
    missing = tmp_path / "does-not-exist.jsonl"
    agg = TranscriptAggregator()
    agg.register(str(missing), "other")

    assert agg.poll() is False
    assert agg.totals() == {}
    captured = capsys.readouterr()
    assert "stonefish" in captured.err


# ---------- 部門別集計 ----------


def test_totals_split_by_department_across_multiple_transcripts(tmp_path):
    t_product = tmp_path / "product.jsonl"
    t_invest = tmp_path / "invest.jsonl"
    t_product.write_text(
        _usage_line("msg_p1", "2026-08-01T10:00:00.000Z", input_tokens=10, output_tokens=1) + "\n",
        encoding="utf-8",
    )
    t_invest.write_text(
        _usage_line("msg_i1", "2026-08-01T10:00:00.000Z", input_tokens=100, output_tokens=9) + "\n",
        encoding="utf-8",
    )

    agg = TranscriptAggregator()
    agg.register(str(t_product), "product")
    agg.register(str(t_invest), "invest")
    agg.poll()

    totals = agg.totals()
    assert totals["product"]["total"] == 11
    assert totals["invest"]["total"] == 109
    assert set(totals.keys()) == {"product", "invest"}


def test_register_is_idempotent_and_does_not_reset_offset(tmp_path):
    """同じ transcript を2回 register しても、既に読み進めたオフセットは維持される
    （再登録のたびに全件読み直して水増しされないこと）。"""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        _usage_line("msg_1", "2026-08-01T10:00:00.000Z", input_tokens=10, output_tokens=1) + "\n",
        encoding="utf-8",
    )

    agg = TranscriptAggregator()
    agg.register(str(transcript), "product")
    agg.poll()
    agg.register(str(transcript), "product")  # 再登録（dept 更新のみ想定）
    assert agg.poll() is False  # 差分がないので False のまま


def test_cache_tokens_combine_creation_and_read(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        _usage_line("msg_1", "2026-08-01T10:00:00.000Z", input_tokens=1, output_tokens=1,
                     cache_creation=100, cache_read=50) + "\n",
        encoding="utf-8",
    )
    agg = TranscriptAggregator()
    agg.register(str(transcript), "product")
    agg.poll()
    assert agg.totals()["product"]["cache"] == 150


# ---------- 実データ検証（Sprint-24 教訓: ストリーミングJSONLは実データ確認必須） ----------


def _find_a_real_transcript() -> Path | None:
    """このリポジトリの実セッション transcript を ~/.claude/projects/ から動的に探す。

    ディレクトリ名はリポジトリパスの "/"・"_"・"." をすべて "-" に置換したもの
    （Claude Code の実際のエンコード規則。実データで確認済み）。個人のユーザー名を
    直書きしないよう、実行時に Path.home() とこのリポジトリの実パスから逆算する。
    """
    projects_root = Path.home() / ".claude" / "projects"
    if not projects_root.exists():
        return None

    repo_root = Path(__file__).resolve().parent.parent
    encoded = str(repo_root).replace("/", "-").replace("_", "-").replace(".", "-")
    candidate_dir = projects_root / encoded
    if not candidate_dir.is_dir():
        return None

    jsonl_files = sorted(candidate_dir.glob("*.jsonl"), key=lambda p: p.stat().st_size, reverse=True)
    return jsonl_files[0] if jsonl_files else None


def test_real_transcript_aggregates_without_exception():
    """実際の transcript JSONL（このリポジトリの実セッション）を集計し、例外なく
    非負整数の妥当な集計値が得られることを確認する。実行環境に該当ファイルが無い場合は skip。
    """
    real_transcript = _find_a_real_transcript()
    if real_transcript is None:
        pytest.skip("実 transcript が見つからない環境のため skip（CI等）")

    agg = TranscriptAggregator()
    agg.register(str(real_transcript), "product")
    agg.poll()  # 例外が飛ばないことそのものが主な検証対象

    totals = agg.totals()
    assert isinstance(totals, dict)
    for dept, bucket in totals.items():
        assert isinstance(dept, str)
        for key in ("input", "output", "cache", "total"):
            assert bucket[key] >= 0
        assert bucket["total"] == bucket["input"] + bucket["output"] + bucket["cache"]

    print(f"[実データ検証] {real_transcript.name}: {totals}")
