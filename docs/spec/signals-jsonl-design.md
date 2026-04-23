# _signals.jsonl 設計書

作成日: 2026-04-24
Issue: #23
Phase: 1（スキーマ定義のみ）

---

## 目的

エージェントチームの活動シグナル（タスク完了、QA結果、リトライ、ブロック等）を構造化されたイベントログとして記録し、将来の自己改善ループ（Phase-2以降）で分析・フィードバックに活用する。

## ファイル配置

```
.claude/_signals.jsonl
```

- 1行1イベント（JSON Lines形式）
- append-only（既存行の編集・削除は禁止）
- git 管理対象（レトロスペクティブの素材として履歴を残す）

## スキーマ定義（v1）

```jsonc
{
  // 必須フィールド
  "ts":       "2026-04-24T12:00:00+0000",  // ISO 8601（UTC）
  "type":     "task.done",                  // イベント種別（下表参照）
  "sprint":   "sprint-07",                  // スプリント識別子
  "slug":     "bash-quality-fix",           // タスクslug（該当する場合）

  // オプションフィールド
  "agent":    "Riku",                       // 実行エージェント
  "detail":   {},                           // イベント種別ごとの追加データ
  "meta":     {}                            // 自由形式メタデータ
}
```

## イベント種別一覧

| type | 発生タイミング | detail の内容 |
|------|--------------|--------------|
| `task.start` | `queue.sh start` 実行時 | `{}` |
| `task.done` | `queue.sh done` 実行時 | `{"summary": "完了サマリー"}` |
| `task.handoff` | `queue.sh handoff` 実行時 | `{"to_agent": "Sora", "next_slug": "..."}` |
| `qa.approved` | `queue.sh qa APPROVED` | `{"reviewer": "Sora", "notes": "..."}` |
| `qa.changes_requested` | `queue.sh qa CHANGES_REQUESTED` | `{"reviewer": "Sora", "reason": "..."}` |
| `task.retry` | `queue.sh retry` 実行時 | `{"retry_count": 1}` |
| `task.blocked` | `queue.sh block` 実行時 | `{"reason": "..."}` |
| `sprint.start` | スプリント計画完了時 | `{"task_count": 5}` |
| `sprint.done` | 全タスクDONE+QA APPROVED | `{"duration_days": 2}` |
| `lesson.recorded` | lessons.sh 記録時 | `{"lesson_id": "L-xxx", "category": "..."}` |

## 記録方法

`scripts/queue.sh` の各コマンド内で、状態遷移の直後に `_signals.jsonl` へ1行 append する。

```bash
_emit_signal() {
  local type="$1" slug="$2" agent="$3" detail="${4:-{}}"
  local sprint
  sprint=$(jq -r '.sprint // "unknown"' "$QUEUE_FILE" 2>/dev/null || echo "unknown")
  printf '{"ts":"%s","type":"%s","sprint":"%s","slug":"%s","agent":"%s","detail":%s}\n' \
    "$(date -u +"%Y-%m-%dT%H:%M:%S+0000")" "$type" "$sprint" "$slug" "$agent" "$detail" \
    >> "${QUEUE_DIR}/_signals.jsonl"
}
```

## 将来の接続点（Phase-2以降、本スプリントではスコープ外）

1. **レトロスペクティブ自動生成**: `_signals.jsonl` を集計してスプリントメトリクスを自動計算
   - タスクあたり平均所要時間
   - リトライ率
   - QA差し戻し率
2. **自己改善ループ**: 高リトライ率のパターンを検出し、lessons.json に自動提案
3. **ダッシュボード**: Mermaid グラフでスプリント進捗を可視化

## 設計判断

| 判断 | 理由 |
|------|------|
| JSONL（not SQLite/CSV） | append-only・行指向・jq で即座に集計可能・git diff が読みやすい |
| `queue.sh` 内で emit | 既存の状態遷移ロジックに最小限の追加で済む |
| UTC 固定 | Sprint-07 の `date -u` 統一方針と一致 |
| v1 は最小フィールド | Phase-1 はスキーマ合意が目的、過度な構造化は避ける |
