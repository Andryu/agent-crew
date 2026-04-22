# `_lessons.json` スキーマ設計

作成日: 2026-04-21
ステータス: Accepted
対応 Issue: #21

---

## 概要

`~/.claude/_lessons.json` は agent-crew の自己学習基盤の中核ファイルです。
スプリントをまたいで失敗パターン・成功パターン・改善ナレッジを蓄積し、
次スプリントの計画品質を自動的に向上させるループを支えます。

複数プロジェクト間でノウハウを共有するため、グローバルパス（`~/.claude/`）に配置します。

---

## 設計判断

### append-only 方式の採用

複数セッション（プロジェクト）から同時書き込みが発生する可能性があります。
競合対策として **append-only 方式** を採用します。

- 各 lesson エントリは独立した JSON オブジェクトで管理します
- 既存エントリの上書きは行わず、新しい `id` でエントリを追加します
- 更新が必要な場合は `supersedes` フィールドで旧 ID を参照し、新エントリを追加します
- ファイルロック（`flock`）と組み合わせてアトミックな append を保証します

この方式により:
- 並行書き込み時のデータ損失リスクが最小化されます
- 過去の観察が消えず、学習の変遷が追跡できます
- バグ時のロールバックが容易です

### severity × frequency による priority 算出

タスク3（evidence-gate-design）のエビデンスゲートと連動するため、
各 lesson に `severity_score` と `frequency_score` を持たせます。

```
priority_score = severity_score × frequency_score
```

| priority_score | 意味 | Issue 化の目安 |
|---------------|------|--------------|
| 9 以上 | Critical | 即時 Issue 化 |
| 4〜8 | High | 次スプリントで対処 |
| 2〜3 | Medium | バックログに積む |
| 1 | Low | 記録のみ |

---

## JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/agent-crew/schemas/lessons.json",
  "title": "LessonsFile",
  "description": "agent-crew の自己学習記録ファイル（~/.claude/_lessons.json）",
  "type": "object",
  "required": ["schema_version", "lessons"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {
      "type": "string",
      "description": "スキーマバージョン（セマンティックバージョニング）",
      "pattern": "^\\d+\\.\\d+\\.\\d+$",
      "examples": ["1.0.0"]
    },
    "lessons": {
      "type": "array",
      "description": "lesson エントリの配列（append-only）",
      "items": { "$ref": "#/$defs/Lesson" }
    }
  },
  "$defs": {
    "Lesson": {
      "type": "object",
      "required": [
        "id",
        "project",
        "sprint",
        "category",
        "severity_score",
        "frequency_score",
        "description",
        "action",
        "created_at"
      ],
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "string",
          "description": "一意識別子。形式: <project>-<sprint>-<category>-<連番3桁>",
          "pattern": "^[a-z0-9-]+-sprint-\\d+-[a-z]+-\\d{3}$",
          "examples": ["agent-crew-sprint-02-planning-001"]
        },
        "project": {
          "type": "string",
          "description": "プロジェクト名（リポジトリ名推奨）",
          "examples": ["agent-crew", "my-app"]
        },
        "sprint": {
          "type": "string",
          "description": "スプリント識別子",
          "pattern": "^sprint-\\d+$",
          "examples": ["sprint-01", "sprint-02"]
        },
        "category": {
          "type": "string",
          "description": "lesson のカテゴリ",
          "enum": [
            "planning",
            "implementation",
            "qa",
            "communication",
            "tooling",
            "process",
            "architecture"
          ]
        },
        "type": {
          "type": "string",
          "description": "lesson の種類。省略時は failure 扱い",
          "enum": ["failure", "success", "observation"],
          "default": "failure"
        },
        "severity_score": {
          "type": "integer",
          "description": "影響の深刻さ（1〜3）。1=軽微, 2=中程度, 3=重大",
          "minimum": 1,
          "maximum": 3
        },
        "frequency_score": {
          "type": "integer",
          "description": "発生頻度（1〜3）。1=稀, 2=時々, 3=頻繁",
          "minimum": 1,
          "maximum": 3
        },
        "priority_score": {
          "type": "integer",
          "description": "priority_score = severity_score × frequency_score（記録時に算出して付与する）",
          "minimum": 1,
          "maximum": 9
        },
        "description": {
          "type": "string",
          "description": "何が起きたか・何を学んだかの説明（1〜3文を推奨）",
          "minLength": 10
        },
        "evidence": {
          "type": "array",
          "description": "観察の根拠（タスク slug・Issue 番号・ログの断片など）",
          "items": {
            "type": "string"
          },
          "examples": [["issue-close-bug-investigation", "#34", "queue.sh の open 実行ログ"]]
        },
        "action": {
          "type": "string",
          "description": "次回取るべきアクション・改善策（1〜2文）",
          "minLength": 5
        },
        "issue_url": {
          "type": ["string", "null"],
          "description": "対応 GitHub Issue の URL（Issue 化済みの場合）",
          "format": "uri",
          "default": null,
          "examples": ["https://github.com/owner/agent-crew/issues/34"]
        },
        "supersedes": {
          "type": ["string", "null"],
          "description": "この lesson が更新・改訂する旧 lesson の id（append-only 更新時に使用）",
          "default": null
        },
        "tags": {
          "type": "array",
          "description": "自由タグ（検索・フィルタリング用）",
          "items": {
            "type": "string"
          },
          "examples": [["queue.sh", "github-actions", "issue-lifecycle"]]
        },
        "created_at": {
          "type": "string",
          "description": "エントリ作成日時（ISO 8601）",
          "format": "date-time",
          "examples": ["2026-04-21T10:00:00+0900"]
        },
        "updated_at": {
          "type": ["string", "null"],
          "description": "エントリ更新日時（append-only のため通常 null。廃止理由メモなどにのみ使用）",
          "format": "date-time",
          "default": null
        }
      }
    }
  }
}
```

---

## フィールド詳細

### カテゴリ（category）の定義

| 値 | 対象の問題領域 |
|---|------------|
| `planning` | スプリント計画・タスク分解・見積もりの失敗 |
| `implementation` | コーディング・実装パターンに関する学び |
| `qa` | レビュー・テスト・差し戻しに関する観察 |
| `communication` | エージェント間・オーナーとのコミュニケーション |
| `tooling` | scripts/・hooks/・設定ファイルの問題 |
| `process` | ワークフロー・手順・フロー定義の問題 |
| `architecture` | 設計判断・ADR に関する学び |

### severity_score の定義

| 値 | 意味 | 例 |
|---|------|---|
| 1 | 軽微（作業効率の低下程度） | ドキュメントの書き漏れ |
| 2 | 中程度（タスクのブロックや差し戻しが発生） | QA 差し戻し・依存関係の誤設定 |
| 3 | 重大（データ損失・本番影響・スプリント失敗） | Issue の繰り返し open/close バグ |

### frequency_score の定義

| 値 | 意味 | 目安 |
|---|------|-----|
| 1 | 稀（このスプリントで初めて観察） | 1回 |
| 2 | 時々（2〜3スプリントに1回程度） | 2〜3回 |
| 3 | 頻繁（毎スプリントのように発生） | 4回以上 |

### id 命名規則

```
<project>-<sprint>-<category>-<連番3桁>

例:
  agent-crew-sprint-02-planning-001
  agent-crew-sprint-02-tooling-001
  my-app-sprint-03-qa-001
```

連番はプロジェクト+スプリント+カテゴリの組み合わせ内でインクリメントします。
衝突リスクを避けるため、記録前に既存の同一プレフィックスの最大連番を確認してから採番します。

---

## 競合対策（append-only + flock）

実装時（タスク7: lessons-json-impl）は以下の手順で書き込みます。

```bash
# append 書き込みの擬似コード
(
  flock -x -w 10 200 || { echo "ERROR: lock timeout" >&2; exit 1; }

  # 1. 既存ファイルを読み込む
  existing=$(cat ~/.claude/_lessons.json)

  # 2. 新エントリを .lessons 配列末尾に追加
  updated=$(echo "$existing" | jq --argjson entry "$NEW_ENTRY" '.lessons += [$entry]')

  # 3. アトミックに書き戻す（tmpファイル経由）
  tmp=$(mktemp ~/.claude/_lessons.json.tmp.XXXXXX)
  echo "$updated" > "$tmp"
  mv "$tmp" ~/.claude/_lessons.json

) 200>~/.claude/_lessons.json.lock
```

ロックファイルは `~/.claude/_lessons.json.lock` を使用します。
ロック待機タイムアウトは 10 秒とします。

---

## 他コンポーネントとの連携

### みゆきち（retro エージェント）

スプリント完了後、みゆきちが観察した失敗パターンと改善提案を
`_lessons.json` に追記します。

- 入力: queue.json のイベント履歴、retro サマリー
- 出力: `_lessons.json` への lesson エントリ追加（flock 経由）

### エビデンスゲート（タスク3: evidence-gate-design）

`priority_score`（= severity_score × frequency_score）がゲートの閾値として使用されます。
閾値以上の lesson のみ GitHub Issue に昇格されます。

### Start hook（タスク6: start-hook-design）

セッション開始時に `_lessons.json` を読み込み、
priority_score が高い未対処 lesson のサマリーを表示します。

```bash
# Start hook でのサマリー表示イメージ
jq -r '.lessons[] | select(.issue_url == null and .priority_score >= 4) |
  "[\(.priority_score)] \(.category): \(.description)"' \
  ~/.claude/_lessons.json
```

---

## ファイル配置

| パス | 説明 |
|-----|------|
| `~/.claude/_lessons.json` | 実運用ファイル（グローバル） |
| `templates/_lessons.json` | 初期テンプレート（本リポジトリ） |
| `~/.claude/_lessons.json.lock` | flock 用ロックファイル（自動生成） |

---

## 移行・初期化

初回セットアップ時（install.sh 更新時、タスク11）に以下を実行します。

```bash
# _lessons.json が存在しない場合のみ初期ファイルを配置
if [ ! -f ~/.claude/_lessons.json ]; then
  cp "$(dirname "$0")/../templates/_lessons.json" ~/.claude/_lessons.json
fi
```

---

## 設計トレードオフ

### JSON vs JSONL

JSONL（1行1エントリ形式）はファイル末尾への追記が単純でロック不要ですが、
`jq` による集計・フィルタリングが複雑になります。
Start hook（タスク6）での `jq` クエリとの親和性を優先して JSON を採用しました。
ロック競合は `flock` + アトミック `mv` で十分に対処できます。

### フラットリスト vs ネスト構造

プロジェクト別・スプリント別にネストする案もありましたが、
`jq` でのフィルタリングを単純に保つためフラットな配列構造を採用しました。
`project` と `sprint` フィールドがフィルタキーとして機能します。
