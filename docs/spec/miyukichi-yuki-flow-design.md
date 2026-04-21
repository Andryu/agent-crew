# みゆきち ↔ Yuki 連携フロー設計

作成日: 2026-04-21
ステータス: Accepted
対応 Issue: #28
依存設計:
- docs/spec/lessons-json-schema.md（タスク2）
- docs/spec/evidence-gate-design.md（タスク3）

---

## 概要

Yuki（pm.md）がスプリント完了後にみゆきち（retro.md）を起動し、
スプリントの観察を `_lessons.json` に記録し、エビデンスゲートを経て Issue 化するまでの
エンドツーエンドのフローを定義する。

---

## 1. トリガー条件

みゆきちの起動タイミングは2種類を定義する。

### 1-A. スプリント完了時の自動起動（推奨）

以下の条件を**すべて満たしたとき**、Yuki はみゆきちを起動する：

```
① scripts/queue.sh show の結果、全タスクの status == "DONE"
② QA対象の全タスクで qa_result == "APPROVED"
③ スプリント完了報告をオーナーへ出力した直後
```

Yuki のスプリント完了報告（「スプリント完了報告 — [sprint名]」）の末尾に
以下のセクションを追加し、みゆきちへの引き継ぎを明示する：

```
--- NEXT STEP ---
次のコマンド: @retro "[sprint名]" のレトロスペクティブをして
理由: スプリント完了後の教訓収集・Issue化フローを実行する
---
```

### 1-B. オーナーからの明示的指示

オーナーが以下のような指示を出した場合にも起動する：

- 「みゆきちを呼んで」
- 「レトロスペクティブをやって」
- 「今スプリントの振り返りをして」

この場合、スプリントの全タスクが DONE でなくても起動可能とする（中間レトロ）。
ただし `_queue.json` のスプリント識別子とタスク完了率を引数としてみゆきちに渡す。

---

## 2. みゆきちが `_lessons.json` に書き込むデータフォーマット

みゆきちは `_queue.json` のイベント履歴とスプリント全体の観察を分析し、
以下の形式で `_lessons.json` に追記する。

### 書き込みフォーマット（lesson エントリ）

```json
{
  "id": "<project>-<sprint>-<category>-<連番3桁>",
  "project": "<リポジトリ名>",
  "sprint": "<sprint識別子>",
  "category": "planning | implementation | qa | communication | tooling | process | architecture",
  "type": "failure | success | observation",
  "severity_score": 1,
  "frequency_score": 1,
  "priority_score": 1,
  "description": "何が起きたか・何を学んだかの説明（1〜3文）",
  "evidence": ["タスクslug", "Issue番号", "ログの断片など"],
  "action": "次回取るべきアクション・改善策（1〜2文）",
  "issue_url": null,
  "supersedes": null,
  "tags": ["自由タグ"],
  "created_at": "2026-04-21T10:00:00+0900",
  "updated_at": null
}
```

### スコアリング判断基準（みゆきちが判断する）

| フィールド | 判断根拠 |
|-----------|---------|
| `severity_score` | 問題がスプリントに与えた影響の深刻さ（1=軽微 / 2=ブロック・差し戻し発生 / 3=スプリント失敗・データ損失） |
| `frequency_score` | 同種の問題の過去発生回数（1=今回初めて / 2=2〜3スプリントに1回 / 3=毎スプリント発生） |
| `priority_score` | severity × frequency で算出（記録時に自動計算して付与） |

### id 採番ルール

```bash
# 既存エントリの最大連番を確認してからインクリメント
LAST_SEQ=$(jq -r --arg prefix "${PROJECT}-${SPRINT}-${CATEGORY}-" '
  .lessons[] |
  select(.id | startswith($prefix)) |
  .id |
  split("-") |
  last |
  tonumber
' ~/.claude/_lessons.json | sort -n | tail -1)

NEXT_SEQ=$(printf "%03d" $(( ${LAST_SEQ:-0} + 1 )))
NEW_ID="${PROJECT}-${SPRINT}-${CATEGORY}-${NEXT_SEQ}"
```

---

## 3. Yuki 側での受け取り→ゲート判定→Issue化 手順

みゆきちから完了報告を受け取った後、Yuki は以下の手順でフローを確認する。

### ステップ 1: みゆきちの完了確認

みゆきちは以下のフォーマットで Yuki へ完了報告を返す：

```
## レトロスペクティブ完了 — [sprint名]

### 記録した lesson
- [lesson-id]: [description の冒頭30文字] (priority: [score])
- ...
合計: [n] 件

### Issue化結果
- 作成: [n] 件
  - [issue-url]: [title]
- 保留: [n] 件（priority_score < 4 または evidence 不足）

### 保留 lesson（バックログ候補）
- [lesson-id]: [理由]（例: priority_score=2, evidence不足）
```

### ステップ 2: Yuki のスプリント完了報告への統合

Yuki はみゆきちの結果を「スプリント完了報告」に統合する：

```
## スプリント完了報告 — [sprint名]

### 完了タスク
- [slug]: [一言説明]

### レトロスペクティブサマリー（みゆきち）
- 記録 lesson: [n] 件
- Issue化: [n] 件（[urls]）
- 保留: [n] 件

### 残課題・技術的負債
- [あれば記載]

### 次のスプリントの候補
- [提案があれば]
```

### ステップ 3: Slack 通知

レトロスペクティブ完了時に Slack 通知を送る：

```bash
# レトロ完了通知
curl -s -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-type: application/json' \
  -d "{\"text\": \"[sprint名] レトロ完了: lesson [n]件記録 / Issue [n]件作成\"}"
```

---

## 4. pm.md に追記すべきセクション

以下のセクションを `pm.md` の「完了報告フォーマット」セクションの後に追加する。

---

```markdown
## みゆきち連携（レトロスペクティブ）

### 起動タイミング

スプリント完了判定（全タスク DONE + 全 QA APPROVED）を確認したら、
スプリント完了報告の末尾に以下を出力してみゆきちを起動する：

\```
--- NEXT STEP ---
次のコマンド: @retro "[sprint名]" のレトロスペクティブをして
理由: スプリント完了後の教訓収集・Issue化フローを実行する
---
\```

オーナーから「みゆきちを呼んで」「振り返りをして」と指示された場合も同様に起動する。

### みゆきちへ渡す情報

起動時に以下の情報が参照できる状態にしておくこと：

| 情報 | 場所 |
|------|------|
| スプリント識別子 | `_queue.json` の `sprint` フィールド |
| タスク一覧・イベント履歴 | `_queue.json` の `tasks[].events[]` |
| リトライ回数・ブロック履歴 | `_queue.json` の `tasks[].retry_count` |
| 過去の lesson | `~/.claude/_lessons.json` |

### みゆきちからの完了報告の受け取り

みゆきちが返す完了報告を確認し、スプリント完了報告の「レトロスペクティブサマリー」
セクションに統合する。Issue化件数・保留件数をオーナーへ明示すること。

### Slack通知（レトロ完了）

```bash
curl -s -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-type: application/json' \
  -d "{\"text\": \"[sprint名] レトロ完了: lesson [n]件記録 / Issue [n]件作成\"}"
```
```

---

## 5. retro.md に追記すべきセクション

以下のセクションを `retro.md` に追加する。

---

```markdown
## Yuki からの起動プロトコル

みゆきちは以下のいずれかで起動される：

1. **スプリント完了時の自動起動**: Yuki がスプリント完了報告の末尾で `@retro` を呼ぶ
2. **オーナーの明示的指示**: 「みゆきちを呼んで」「振り返りをして」等

### 起動時に確認するファイル

| ファイル | 目的 |
|---------|------|
| `.claude/_queue.json` | タスク一覧・イベント履歴・リトライ回数 |
| `~/.claude/_lessons.json` | 過去 lesson（frequency_score 判断の参考） |

---

## スプリント完了後フロー（標準手順）

### ステップ 1: 観察の収集

`_queue.json` の以下の観点から失敗パターン・成功パターンを収集する：

- リトライが発生したタスク（`retry_count >= 1`）
- BLOCKED になったタスク（`events[]` に block イベントがある）
- 計画より時間がかかったタスク（events の start→done 間隔）
- 全タスクが DONE になった流れ（成功パターン）

### ステップ 2: `_lessons.json` への記録（flock 経由）

収集した観察を lesson エントリとして `_lessons.json` に追記する。

書き込み手順：

```bash
(
  flock -x -w 10 200 || { echo "ERROR: lock timeout" >&2; exit 1; }

  existing=$(cat ~/.claude/_lessons.json)
  updated=$(echo "$existing" | jq --argjson entry "$NEW_ENTRY" '.lessons += [$entry]')

  tmp=$(mktemp ~/.claude/_lessons.json.tmp.XXXXXX)
  echo "$updated" > "$tmp"
  mv "$tmp" ~/.claude/_lessons.json

) 200>~/.claude/_lessons.json.lock
```

### ステップ 3: エビデンスゲートの実行

記録した lesson のうち、以下の条件をすべて満たすものを Issue 化候補とする：

```bash
jq '.lessons[] | select(
  (.issue_url == null) and
  (.priority_score >= 4) and
  ((.evidence // []) | length >= 1)
)' ~/.claude/_lessons.json
```

### ステップ 4: gh issue create の実行

ゲート通過エントリごとに以下を実行する：

```bash
LABEL=$(assign_label "$PRIORITY_SCORE")

gh issue create \
  --title "[lesson] ${TITLE}" \
  --body "## 観察された問題\n\n${DESCRIPTION}\n\n## 根拠（エビデンス）\n\n${EVIDENCE_LIST}\n\n## 推奨アクション\n\n${ACTION}\n\n---\n\n*このIssueは みゆきち（retro エージェント）がエビデンスゲートを通過した lesson から自動生成しました。*\n*lesson ID: ${ID} / priority_score: ${PRIORITY_SCORE} / sprint: ${SPRINT}*" \
  --label "${LABEL}" \
  --label "retro" \
  --label "lessons-learned"
```

Issue 作成後、`issue_url` を lesson エントリに書き戻す（flock 経由）。

### ステップ 5: Yuki への完了報告

以下のフォーマットで完了報告を返す：

```
## レトロスペクティブ完了 — [sprint名]

### 記録した lesson
- [lesson-id]: [description の冒頭30文字] (priority: [score])
合計: [n] 件

### Issue化結果
- 作成: [n] 件
  - [issue-url]: [title]
- 保留: [n] 件（priority_score < 4 または evidence 不足）

### 保留 lesson（バックログ候補）
- [lesson-id]: [理由]
```
```

---

## フロー全体図

```
Yuki
  │
  ├─ 全タスク DONE + QA APPROVED を確認
  │
  ├─ スプリント完了報告をオーナーへ出力
  │
  └─ @retro 起動（NEXT STEP 出力）
         │
         ▼
      みゆきち
         │
         ├─ _queue.json のイベント履歴を分析
         │
         ├─ 観察を lesson エントリに変換
         │   └─ severity × frequency → priority_score を計算
         │
         ├─ _lessons.json に flock 経由で追記
         │
         ├─ エビデンスゲート判定
         │   ├─ priority_score >= 4 AND evidence >= 1 AND issue_url == null
         │   │    → gh issue create
         │   └─ 条件不満足 → 保留（バックログ候補として報告に記載）
         │
         ├─ issue_url を lesson エントリに書き戻し
         │
         └─ 完了報告を Yuki へ返す
               │
               ▼
            Yuki
               │
               ├─ スプリント完了報告にレトロサマリーを統合
               │
               └─ Slack 通知（レトロ完了）
```

---

## 設計トレードオフ

### みゆきちが Issue 化 vs Yuki が Issue 化

みゆきちに Issue 化を担わせる理由：
- みゆきちはレトロスペクティブの文脈（エビデンス・観察理由）を持っているため、Issue本文の品質が高い
- Yuki が Issue 化する場合、みゆきちから構造化されたデータを受け取る必要があり、インターフェースが複雑になる
- 責務の分離が明確（みゆきち = 観察・記録・Issue化、Yuki = オーケストレーション・報告）

### スプリント完了後の自動起動 vs 手動

自動起動（Yuki が NEXT STEP を出力）を採用した理由：
- Antigravity 環境では SubagentStop hook が使えないため、完全自動化は困難
- NEXT STEP 出力でオーナーにコマンドを提示し、手動で `@retro` を呼ぶ運用が現実的
- 将来的に hook が使えるようになれば完全自動化に移行可能（reversible な設計）

### `_lessons.json` への書き込みタイミング

みゆきちが観察後に即座に書き込む（Issue化の前に書き込む）設計を採用した理由：
- Issue化に失敗した場合でも観察記録が失われない
- issue_url は後から書き戻せるため、2フェーズで処理しても整合性が保てる
