# Yuki 自己改善提案モード設計

作成日: 2026-04-21
ステータス: Accepted
対応 Issue: #20
依存設計:
- docs/spec/lessons-json-schema.md（タスク2）
- docs/spec/evidence-gate-design.md（タスク3）
- docs/spec/miyukichi-yuki-flow-design.md（タスク4）

---

## 概要

Yuki（pm.md）が `_lessons.json` に蓄積された教訓を分析し、
自分自身（および他エージェント）のプロセス改善提案を生成するモード。

みゆきちが「スプリント単位で観察を記録する」のに対し、
自己改善モードは「複数スプリントにまたがるパターンを検出して改善提案を生成する」役割を担う。

---

## 1. トリガー条件

### 1-A. 明示的な指示トリガー（優先）

オーナーが以下のような発言をした場合に起動する：

```
「自己改善して」
「改善提案して」
「今まで学んだことを踏まえて改善して」
「lesson から改善策を出して」
「_lessons.json を分析して」
```

このモードでは Yuki がその場でフル分析を実行し、提案リストをオーナーへ提示する。

### 1-B. スプリント完了後の自動提案（条件付き）

みゆきちの完了報告を受け取った後、以下の条件を**すべて満たす**場合に
自動的に簡易提案（要約版）を追加する：

```
① 過去の _lessons.json に priority_score >= 4 の未対処 lesson が 3 件以上ある
② 同じ category で 2 件以上の lesson が重複している（パターン検出）
③ 前回の自己改善提案から 2 スプリント以上経過している
   （last_improvement_sprint フィールドで管理 — 後述）
```

条件を満たさない場合は提案をスキップし、スプリント完了報告のみを出力する。

### トリガー判定フロー

```
スプリント完了 or「自己改善して」
         │
         ▼
  明示的指示か？
  YES → フル分析モードへ（条件チェックなし）
  NO  ↓
         ▼
  自動提案条件チェック（①②③）
  全て満たす → 簡易提案モードへ
  満たさない → スキップ（提案なし）
```

---

## 2. `_lessons.json` からの分析ロジック

### 2-1. データ取得クエリ

```bash
# 全 lesson を取得（最新エントリのみ）
ALL_LESSONS=$(jq '[
  .lessons[] |
  select(.issue_url != null or .priority_score >= 1)
]' ~/.claude/_lessons.json)

# 未対処かつ priority_score >= 4 の lesson
OPEN_HIGH=$(jq '[
  .lessons[] |
  select(
    .issue_url == null and
    .priority_score >= 4
  )
]' ~/.claude/_lessons.json)

# カテゴリ別集計
CATEGORY_COUNTS=$(jq '[
  .lessons[] |
  .category
] | group_by(.) | map({category: .[0], count: length})' ~/.claude/_lessons.json)
```

### 2-2. パターン検出ロジック

以下の3種類のパターンを検出する：

#### パターン A: カテゴリ集中（同カテゴリで3件以上）

```bash
CONCENTRATED=$(jq '[
  .lessons[] |
  .category
] | group_by(.) |
map({category: .[0], count: length}) |
.[] | select(.count >= 3)' ~/.claude/_lessons.json)
```

→ 同一カテゴリで問題が集中している場合、そのカテゴリのプロセスに構造的な問題がある可能性が高い。

#### パターン B: 繰り返し発生（frequency_score >= 2 のエントリが複数）

```bash
RECURRING=$(jq '[
  .lessons[] |
  select(.frequency_score >= 2)
] | length' ~/.claude/_lessons.json)
```

→ frequency_score >= 2 が複数件ある場合、改善アクションが実行されていない。

#### パターン C: 高優先度の放置（priority_score >= 6 かつ issue_url == null）

```bash
NEGLECTED=$(jq '[
  .lessons[] |
  select(.priority_score >= 6 and .issue_url == null)
]' ~/.claude/_lessons.json)
```

→ High/Critical な problem が Issue 化もされずに放置されている。

#### パターン D: action の重複（同種のアクションが複数 lesson に登場）

これは Yuki がテキスト分析で判断する（jq による完全自動化は不要）。
複数の lesson の `action` フィールドを読み、類似するアクションをグルーピングして
「この改善策は複数の問題を解決できる」と提案する。

### 2-3. 分析結果の構造化

```json
{
  "analysis_date": "2026-04-21",
  "total_lessons": 12,
  "open_high_priority": 4,
  "patterns": [
    {
      "pattern_type": "category_concentration",
      "category": "qa",
      "count": 5,
      "severity": "high",
      "representative_lessons": ["agent-crew-sprint-02-qa-001", "..."]
    },
    {
      "pattern_type": "recurring",
      "count": 3,
      "severity": "medium"
    }
  ],
  "proposals": [
    {
      "id": "proposal-001",
      "title": "QA差し戻しパターンへの対処",
      "target_lessons": ["agent-crew-sprint-02-qa-001", "..."],
      "action": "Soraのレビューチェックリストに...",
      "priority": "high"
    }
  ]
}
```

---

## 3. 出力フォーマット

### フル分析モードの出力

```
## 自己改善提案 — [分析日]

### 分析サマリー
- 総 lesson 数: [n] 件
- 未対処 high 以上: [n] 件（priority_score >= 4）
- 検出パターン: [n] 種

### 検出パターン

#### [パターン名]（例: QA カテゴリに集中）
- 該当 lesson: [n] 件
- 代表的な問題:
  - [lesson-id]: [description]
  - [lesson-id]: [description]
- 影響: [パターンが示す根本原因の説明]

### 改善提案

> 以下の提案を確認してください。
> Issue 化する提案の番号を教えてください（「全部」「1,3」など）。

| # | 提案タイトル | 優先度 | 対象 lesson 件数 |
|---|------------|--------|-----------------|
| 1 | [タイトル] | High | [n] |
| 2 | [タイトル] | Medium | [n] |
| 3 | [タイトル] | Low | [n] |

---

各提案の詳細:

**提案1: [タイトル]**
- 根拠: [対象 lesson の要約]
- 改善策: [具体的なアクション]
- 期待効果: [改善後の状態]
- 実装コスト: S / M / L

（以下、提案2、3と続く）

---

Issue 化する提案を指定してください（「全部」「1,3」など、「なし」でスキップ）:
```

### 簡易提案モード（スプリント完了後の自動提案）の出力

スプリント完了報告の末尾に以下を追加する：

```
### 自己改善提案（自動検出）

以下のパターンが繰り返し検出されています：
- [パターン説明]（[n] スプリント連続）

改善提案 Issue を作成しますか？（「はい」または「スキップ」）
```

---

## 4. オーナー確認 → Issue 化の手順

### ステップ 1: 提案リストをオーナーへ提示

上記の出力フォーマットで提案を表示し、番号の指定を待つ。

### ステップ 2: 指定された提案の Issue 化

```bash
# オーナーから「1,3」と指定された場合
for PROPOSAL_NUM in $SELECTED; do
  PROPOSAL=$(get_proposal "$PROPOSAL_NUM")

  gh issue create \
    --title "[improvement] ${PROPOSAL_TITLE}" \
    --body "${ISSUE_BODY}" \
    --label "self-improvement" \
    --label "process" \
    --label "${PRIORITY_LABEL}"
done
```

### ステップ 3: 対象 lesson の `issue_url` を書き戻し

Issue 化した提案に関連する lesson エントリに `issue_url` を書き戻す（flock 経由）：

```bash
(
  flock -x -w 10 200 || { echo "ERROR: lock timeout" >&2; exit 1; }

  UPDATED=$(cat ~/.claude/_lessons.json | jq \
    --arg lesson_id "$LESSON_ID" \
    --arg url "$ISSUE_URL" \
    '.lessons |= map(if .id == $lesson_id then .issue_url = $url else . end)')

  tmp=$(mktemp ~/.claude/_lessons.json.tmp.XXXXXX)
  echo "$UPDATED" > "$tmp"
  mv "$tmp" ~/.claude/_lessons.json

) 200>~/.claude/_lessons.json.lock
```

### ステップ 4: Slack 通知

```bash
curl -s -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-type: application/json' \
  -d "{\"text\": \"自己改善提案 [n]件 Issue 化しました: [urls]\"}"
```

---

## 5. `gh issue create` テンプレート

```bash
# 自己改善提案の Issue 作成テンプレート
create_improvement_issue() {
  local title="$1"
  local description="$2"
  local root_cause="$3"
  local action="$4"
  local expected_outcome="$5"
  local cost="$6"
  local lesson_ids="$7"
  local priority_label="$8"

  local body=$(cat <<EOF
## 改善の背景

${description}

## 根本原因

${root_cause}

## 推奨アクション

${action}

## 期待効果

${expected_outcome}

## 実装コスト

${cost}（S=単一ファイル / M=複数ファイル / L=アーキテクチャ変更）

## 関連 lesson

${lesson_ids}

---

*このIssueは Yuki の自己改善モードが _lessons.json のパターン分析から生成しました。*
*分析日: $(date -u +%Y-%m-%dT%H:%M:%S+0000)*
EOF
)

  gh issue create \
    --title "[improvement] ${title}" \
    --body "${body}" \
    --label "${priority_label}" \
    --label "self-improvement" \
    --label "process"
}
```

### ラベルマッピング

| 提案優先度 | GitHub ラベル |
|-----------|-------------|
| High（pattern A + B の組み合わせ） | `priority-high` |
| Medium（単一パターン） | `priority-medium` |
| Low（観察のみ） | `priority-low` |

---

## 6. pm.md に追記すべきセクション

以下のセクションを `pm.md` の「みゆきち連携」セクションの後に追加する。

---

```markdown
## 自己改善提案モード

### 起動条件

以下のいずれかで起動する：

**明示的指示（優先）:**
- オーナーが「自己改善して」「改善提案して」「lesson を分析して」などと発言した場合
- 条件チェックなしで即座にフル分析を実行する

**スプリント完了後の自動提案（条件付き）:**
- みゆきちの完了報告を受け取り、以下を全て満たす場合に簡易提案を追加する
  - priority_score >= 4 の未対処 lesson が 3 件以上
  - 同一カテゴリで 2 件以上の lesson が存在する
  - 前回提案から 2 スプリント以上経過している

### 分析手順

`~/.claude/_lessons.json` を読み込み、以下の4パターンを検出する：

| パターン | 検出条件 | 意味 |
|---------|---------|------|
| カテゴリ集中 | 同カテゴリで 3 件以上 | プロセスに構造的問題がある |
| 繰り返し発生 | frequency_score >= 2 が複数 | 改善が実行されていない |
| 高優先度放置 | priority_score >= 6 かつ issue_url == null | Critical/High 問題が未対処 |
| アクション重複 | 複数 lesson に類似する action | 1 つの改善策で複数問題を解決できる |

### 提案フォーマット

パターン検出結果を以下の形式でオーナーへ提示し、Issue 化する提案の番号を確認する：

```
## 自己改善提案 — [分析日]

| # | 提案タイトル | 優先度 | 対象 lesson 件数 |
|---|------------|--------|-----------------|
| 1 | ...        | High   | n               |

Issue 化する提案を指定してください（「全部」「1,3」など、「なし」でスキップ）:
```

### Issue 化後の処理

1. `gh issue create` を実行（ラベル: `self-improvement`, `process`, `priority-*`）
2. 対象 lesson の `issue_url` を `_lessons.json` に書き戻す（flock 経由）
3. Slack 通知を送る

### 自動提案スキップの記録

スプリント完了後の自動提案をスキップした場合は、スプリント完了報告に以下を追加：

```
> 自己改善提案: スキップ（条件未達 — 未対処lesson [n]件、パターン検出なし）
```
```

---

## 設計トレードオフ

### Yuki が分析 vs みゆきちが分析

Yuki（pm.md）が自己改善分析を行う設計を採用した理由：
- みゆきちはスプリント単位の観察に特化し、複数スプリントをまたぐパターン分析は Yuki の責務
- Yuki はプロジェクト全体のコンテキスト（タスク計画・依存関係・スプリント履歴）を持つため、根本原因分析の精度が高い
- みゆきちと Yuki の役割が明確に分離される（ Single Responsibility）

### フル自動 Issue 化 vs オーナー確認

オーナー確認を必須とした理由：
- 自己改善提案は pm.md や retro.md 自体の変更を伴う可能性があり、機械判断だけで進めるリスクが高い
- みゆきちのエビデンスゲート（自動 Issue 化）と対比して、より重要な改善提案ほど人間の確認が必要
- 「全部」と答えれば一括 Issue 化できるため、確認のオーバーヘッドは最小限

### `last_improvement_sprint` フィールド（スキップ条件③）の実装

このフィールドは `_lessons.json` ではなく `.claude/_meta.json`（または pm.md のコメント）に保持する。
スコープが別ファイルになるが、`_lessons.json` の schema を汚染しないためのトレードオフ。
実装タスクでは `.claude/_meta.json` に `last_improvement_sprint: "sprint-02"` を追記する方式とする。

### 簡易提案モードの条件（③: 2スプリント以上）

1スプリントごとに提案すると、提案だらけになってオーナーが疲弊するリスクがある。
2スプリント間隔を最低条件とし、明示的指示では条件を無視する設計とした。
この間隔は将来の運用経験に応じて調整可能。
