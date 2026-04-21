# エビデンス閾値ゲート設計

作成日: 2026-04-21
ステータス: Accepted
対応 Issue: #25
依存設計: docs/spec/lessons-json-schema.md（タスク2）

---

## 概要

みゆきち（retro エージェント）が改善提案を GitHub Issue として昇格させる前に、
`_lessons.json` の各エントリを定量的な基準でフィルタリングするゲートロジックを定義する。

低品質・低頻度の観察が Issue として乱立することを防ぎ、
オーナーの注意を本当に対処すべき問題に集中させる。

---

## 設計判断

### 閾値の決定

`priority_score = severity_score × frequency_score`（1〜9）を基準とする。

| priority_score | ランク | Issue 化方針 | 理由 |
|---------------|--------|------------|------|
| 9 | Critical | 即時 Issue 化（ラベル: `priority-critical`） | 重大かつ頻繁。放置するとスプリント連続失敗につながる |
| 6〜8 | High | Issue 化（ラベル: `priority-high`） | 有意な影響。次スプリントまでに対処が必要 |
| 4〜5 | Medium-High | Issue 化（ラベル: `priority-medium`） | 無視できないが緊急ではない |
| 2〜3 | Medium-Low | 保留（バックログ候補として記録のみ） | 1回限りの観察や軽微な問題 |
| 1 | Low | 記録のみ（Issue 化しない） | 作業効率の低下程度 |

**Issue 化の閾値: `priority_score >= 4`**

この閾値の根拠：
- score 4 = severity 2（中程度）× frequency 2（時々）以上。繰り返し発生する中程度の問題は対処する価値がある
- score 3 = severity 3（重大）× frequency 1（稀）。重大だが1回限りの可能性が高いため、もう1回観察されてから Issue 化する
- score 1〜2 = 軽微または稀すぎる。記録のみで十分

### エビデンスの最低要件

Issue 化するためには `priority_score >= 4` に加えて、以下の最低エビデンス要件を満たすこと：

| 要件 | 条件 | 説明 |
|------|------|------|
| `evidence` フィールドの充足 | `evidence` 配列が 1 件以上 | 根拠なしの主観的観察は Issue 化しない |
| 観察回数（frequency_score による代用） | `frequency_score >= 2` または `severity_score == 3` | 1回限りの軽度の問題は保留 |
| `issue_url` が null | `issue_url == null` | すでに Issue 化済みのエントリは再作成しない |
| `supersedes` チェック | 旧エントリが `supersedes` で参照されている場合、旧エントリは対象外 | 更新済みエントリの重複 Issue 化を防ぐ |

**最終的なゲート通過条件（AND）:**

```
priority_score >= 4
AND evidence の配列長 >= 1
AND issue_url == null
AND (supersedes によって参照されていない = 最新エントリである)
```

---

## ゲートロジック フローチャート

```
みゆきちがスプリント完了後に観察を記録
         │
         ▼
  _lessons.json に lesson エントリを追記
  （severity_score × frequency_score → priority_score を付与）
         │
         ▼
  ┌─────────────────────────────────┐
  │ ゲート判定（下記を順番にチェック）       │
  └─────────────────────────────────┘
         │
         ▼
  ① issue_url が null か？
     NO  → スキップ（既にIssue化済み）
     YES ↓
         ▼
  ② 最新エントリか？（supersedes で参照されていないか）
     NO  → スキップ（更新済み旧エントリ）
     YES ↓
         ▼
  ③ priority_score >= 4 か？
     NO  → 保留（バックログ候補としてログ出力のみ）
     YES ↓
         ▼
  ④ evidence 配列が 1件以上あるか？
     NO  → 保留（要エビデンス追加）
     YES ↓
         ▼
  ⑤ priority_score に応じたラベル決定
     9         → priority-critical
     6〜8      → priority-high
     4〜5      → priority-medium
         │
         ▼
  gh issue create を実行
  → issue_url を lesson エントリに書き戻し（flock 経由）
```

---

## jq フィルタ（ゲート判定クエリ）

```bash
# ゲート通過エントリの一覧を取得
GATE_PASSED=$(jq -r '
  .lessons[] |
  select(
    (.issue_url == null) and
    (.priority_score >= 4) and
    ((.evidence // []) | length >= 1)
  ) |
  {id, priority_score, category, description, action, evidence}
' ~/.claude/_lessons.json)
```

`supersedes` によって参照されているかのチェックは実装時に追加する（タスク10）。
設計段階では上記の3条件が主ゲートとして機能する。

---

## ラベル決定ロジック

```bash
# priority_score → GitHub ラベルのマッピング
assign_label() {
  local score=$1
  if   [ "$score" -eq 9 ]; then echo "priority-critical"
  elif [ "$score" -ge 6 ]; then echo "priority-high"
  elif [ "$score" -ge 4 ]; then echo "priority-medium"
  fi
}
```

---

## gh issue create テンプレート

```bash
# みゆきちが Issue 化するときのコマンドテンプレート
create_issue_from_lesson() {
  local lesson_id="$1"
  local title="$2"
  local body="$3"
  local label="$4"
  local project="${5:-agent-crew}"

  gh issue create \
    --title "[lesson] ${title}" \
    --body "${body}" \
    --label "${label}" \
    --label "retro" \
    --label "lessons-learned"
}
```

Issue body のテンプレート（みゆきちが生成する）：

```markdown
## 観察された問題

{description}

## 根拠（エビデンス）

{evidence の各項目を箇条書き}

## 推奨アクション

{action}

---

*このIssueは みゆきち（retro エージェント）がエビデンスゲートを通過した lesson から自動生成しました。*
*lesson ID: {id} / priority_score: {priority_score} / sprint: {sprint}*
```

---

## retro.md への組み込み方法

### みゆきちのスプリント完了後フロー（設計レベル）

スプリント完了後、Yuki からみゆきちに制御が渡ったとき、以下の手順を実行する：

**ステップ 1: 観察の記録**

`_queue.json` のイベント履歴と retro サマリーを分析し、
観察した失敗パターン・成功パターンを `_lessons.json` に追記する（flock 経由）。

**ステップ 2: ゲート判定の実行**

```bash
# ゲート通過エントリを取得
jq '.lessons[] | select(
  (.issue_url == null) and
  (.priority_score >= 4) and
  ((.evidence // []) | length >= 1)
)' ~/.claude/_lessons.json
```

**ステップ 3: ゲート通過エントリの Issue 化**

ゲートを通過した各エントリに対して `gh issue create` を実行する。
Issue 作成後、`issue_url` を lesson エントリに書き戻す。

**ステップ 4: 保留エントリの報告**

`priority_score < 4` または `evidence` 不足のエントリは、
Yuki への完了報告に「保留: {件数}件（エビデンス不足 or 低優先度）」として含める。

### retro.md に追記すべきセクション（Riku への引き継ぎ）

`retro.md` の `## 完了フロー` または `## みゆきちの責務` セクションに
以下のゲート判定手順を追加する：

```markdown
## エビデンスゲート（evidence-gate）

スプリント完了後、_lessons.json に記録した観察を Issue 化する前に
以下の条件で絞り込む：

- priority_score >= 4（severity × frequency の積）
- evidence フィールドが 1 件以上ある
- issue_url が null（未Issue化）

条件を満たした lesson のみ gh issue create を実行し、
作成した URL を lesson の issue_url に書き戻す。

条件を満たさなかった lesson は保留として Yuki への報告に含める。
```

---

## 設計トレードオフ

### 閾値 4 vs 6

閾値を 6 にすると（High 以上のみ Issue 化）、Issue の量は減るが
「重大×稀」（score 3）や「中程度×時々」（score 4）が漏れる。
個人開発では Issue の管理コストより問題の捕捉率を重視するため、
閾値 4（Medium-High 以上）を採用した。

### 自動 Issue 化 vs 手動承認

完全自動化だとノイズリスクがあるが、
エビデンスゲート（score × evidence 件数）による事前フィルタリングが
人間の承認コストを代替できると判断した。
不安であれば `EVIDENCE_GATE_DRY_RUN=true` 環境変数でドライラン出力のみにするオプションを
実装タスク（タスク10）で追加する。

### `supersedes` チェックの省略

最新エントリかどうかの判定（`supersedes` 被参照チェック）は
jq の逆参照が必要で実装コストが高い。
設計段階では `issue_url == null` と `priority_score` の組み合わせで
実用上十分にフィルタリングできるため、実装段階（タスク10）で対処する。

---

## 他コンポーネントとの関係

| コンポーネント | 関係 |
|-------------|------|
| `_lessons.json` スキーマ（タスク2） | `priority_score`・`evidence`・`issue_url` フィールドを使用 |
| みゆきち連携フロー設計（タスク4） | Yuki→みゆきち→ゲート判定→Issue化の順序を定義 |
| エビデンスゲート実装（タスク10） | このドキュメントの仕様に基づき `retro.md` を更新 |
| Start hook（タスク6） | `priority_score >= 4` かつ `issue_url == null` の lesson を表示する際に同じ条件を使用 |
