# SDD品質改善還流ループ 設計書

> **対象**: チームSDDオーケストレーション（Kiro系）向け。agent-crew 個人開発リポジトリとは別物。
> **位置づけ**: 設計提案。実装は別リポジトリで行う。
> **⚠ agent-crew での採否**: 本方式は不採用（Rejected）。agent-crew の仕様管理は軽量機能仕様書方式 — `docs/adr/ADR-015-spec-driven-development.md` を参照。

---

## 1. システム概要

```
[品質問題を検知した人]
        |
        | /spec-postmortem を手動起動
        v
[/spec-postmortem スキル]
        |
        |-- 根因タクソノミーで分類
        |-- why_chain を構造化
        |-- fix_target_file を特定
        |-- postmortem記録を生成
        |-- diff提案を生成
        v
[真実源リポ knowledge/postmortems/]
        |
        |-- index.yaml に根因カテゴリ・頻度を集約
        v
[改善PR → テンプレ / プロンプト / agent定義]
        |
        |-- レビュー・承認
        v
[チーム全体に改善が伝播]
```

---

## 2. 根因タクソノミー（固定分類）

Kiro 3フェーズ（requirements / design / tasks）に対応して6カテゴリを定義する。

### 2.1 カテゴリ定義

| カテゴリID | 名称 | 定義 | 典型的な証跡 |
|-----------|------|------|------------|
| `requirements-gap` | 要件の欠落・曖昧さ | 受入基準/制約/非機能要件が未記載または曖昧で、実装者が誤った仮定を置いた | requirements.md の受入基準が「正常に動くこと」程度にしか書かれていない |
| `design-gap` | 設計の欠落・誤り | 設計がrequirementsを満たしていない、技術選定の根拠が欠落している、境界条件の考慮がない | design.md にエラーハンドリングの設計がない |
| `tasks-gap` | タスク分解の粗さ | タスクの粒度が大きすぎる、依存関係が未記述で並行作業が破綻した、完了条件が曖昧 | tasks.md のタスク1件が「APIを実装する」だけで定義されている |
| `context-gap` | 前提コンテキストの未リンク | specが参照すべき既存コード・設計・ドキュメントへのリンクを欠いており、実装者がコンテキストを持てなかった（availability gap） | requirements.md に既存の認証フローへの参照がない |
| `drift` | spec-実装間の乖離 | specは十分だったが、実装がspecから逸脱した。specの問題ではなくレビュー・実行プロセスの問題 | design.md ではDBトランザクションを使う設計だが、実装では使われていない |
| `review-gap` | QA・受入チェックのすり抜け | 根因がrequirements/design/tasksにあっても、QAフェーズで発見できなかった。チェックリストの欠落 | テスト仕様にエラーケースが含まれていない |

### 2.2 分類の判定フロー

```
問: specに書かれていなかったことが原因か？
  YES → requirements-gap / design-gap / tasks-gap / context-gap のいずれか
    問: どのフェーズの3点セットに書かれるべきだったか？
      requirements.md → requirements-gap または context-gap
      design.md → design-gap
      tasks.md → tasks-gap
      前提へのリンク欠落 → context-gap
  NO → specはあったが守られなかったか？
    YES → drift
    NO → QAで本来発見できたはずか？
      YES → review-gap
      NO → 上記以外（カテゴリを新規提案としてissueに起票）
```

複数カテゴリの同時指定を許容する（例: `requirements-gap` + `context-gap`）。

---

## 3. postmortem記録スキーマ

### 3.1 フロントマター（構造化フィールド）

```yaml
---
id: "pm-YYYYMMDD-HHMMSS"           # 自動生成。衝突回避のためタイムスタンプベース
target_feature: "機能名または機能ディレクトリパス"
root_cause_category:               # 1つ以上。上記タクソノミーのカテゴリIDから選択
  - requirements-gap
source_repo: "github.com/org/repo" # 対象コードが存在するリポジトリ
fix_target_file:                   # 改善提案の対象ファイル。1つ以上
  - "spec/templates/requirements.md.tpl"
author_hash: "sha256(github_id)[:8]" # 匿名化済み作成者識別子
status: "draft"                    # draft | proposed | merged | closed
created_at: "2026-06-18T00:00:00Z"
---
```

### 3.2 本文構造（散文Markdown）

```markdown
## 概要

[何が起きたか。1-3文。]

## why_chain（5-whys的根因展開）

- なぜ問題が発生したか: [...]
  - なぜその状態になったか: [...]
    - なぜそれが起きたか: [根因カテゴリに対応する特定]

## 証跡（evidence）

対象ファイル・コミット・PRへのリンク、またはトランスクリプトの抜粋を記載。

- requirements.md: [リンクまたはパス]
- 問題のある実装箇所: [コミットSHAまたはPR番号]

## 改善提案

### [fix_target_file に対応する各ファイルへの提案]

**変更前（問題のある状態）:**

```[ファイル種別]
[変更前の記述]
```

**変更後（提案）:**

```[ファイル種別]
[変更後の記述]
```

**変更理由:** [なぜこの変更が根因に対処するか]

## 未解決事項

[設計の迷い・追加調査が必要な点]
```

### 3.3 フォーマット選定の根拠

フロントマター付きMarkdownを選定した理由はADRに記述した通り。補足として：

- `id` フィールドはタイムスタンプベースにすることで、index.yaml のキーとして一意性を保ちながら、ファイル名にも使える（`pm-20260618-120000.md`）
- `author_hash` は `sha256(github_user_id)` の先頭8文字とする。完全な匿名化ではなく「同一人物の複数postmortemを相関付けられる」程度の疑似匿名化。完全匿名化が必要な場合はチームポリシーで別途検討する
- `status` は4段階。`draft`（スキル生成直後）→`proposed`（PR作成済み）→`merged`（承認・マージ済み）→`closed`（PR却下等で終了）

---

## 4. 真実源リポのディレクトリ構成

既存の共有GitHubリポジトリに以下の構成を追加する。

```
<shared-orchestration-repo>/
├── knowledge/
│   ├── postmortems/
│   │   ├── index.yaml              # 根因カテゴリ別集約インデックス（後述）
│   │   ├── pm-20260618-120000.md   # 個別postmortem記録
│   │   └── pm-20260620-093000.md
│   └── decisions/                  # チームレベルのアーキテクチャ決定記録（既存があれば流用）
├── spec/
│   └── templates/
│       ├── requirements.md.tpl     # 改善対象の可能性があるファイル群
│       ├── design.md.tpl
│       └── tasks.md.tpl
├── prompts/
│   └── phases/
│       ├── requirements-phase.md
│       ├── design-phase.md
│       └── tasks-phase.md
├── agents/
│   └── [agent定義ファイル群]
└── CHANGELOG.md                    # テンプレ・プロンプト・agent定義の変更履歴
```

### 4.1 index.yaml のスキーマ

```yaml
# knowledge/postmortems/index.yaml
# このファイルは /spec-postmortem スキルが postmortem記録を追加するたびに自動更新する
last_updated: "2026-06-18T12:00:00Z"
total_count: 3

by_category:
  requirements-gap:
    count: 2
    postmortem_ids:
      - "pm-20260618-120000"
      - "pm-20260620-093000"
  design-gap:
    count: 1
    postmortem_ids:
      - "pm-20260618-120000"  # 複数カテゴリ指定のため重複あり

# 頻度が高い順にソートされた優先改善候補（上位5件）
priority_queue:
  - category: requirements-gap
    count: 2
    top_fix_targets:
      - "spec/templates/requirements.md.tpl"
```

---

## 5. `/spec-postmortem` スキル仕様

### 5.1 入力

| 入力項目 | 必須 | 説明 |
|---------|------|------|
| `requirements.md` | 必須 | 対象機能のrequirements |
| `design.md` | 必須 | 対象機能のdesign |
| `tasks.md` | 必須 | 対象機能のtasks |
| 実装diff または PR URL | 推奨 | 実際に何が作られたかの証跡 |
| 人↔Claudeのトランスクリプト | 任意 | 会話の流れからcontext-gapを検出するために使用 |
| 「何が悪かったか」の一言 | 必須 | 起動者の主観的な問題認識。タクソノミー分類のアンカーになる |

### 5.2 処理フロー

```
1. 入力読み込みと前処理
   - spec 3点セットを読み込み
   - 起動者の「何が悪かったか」をアンカーとして根因カテゴリ候補を絞り込む
   - トランスクリプトがある場合はcontext-gap検出に使用

2. タクソノミー分類
   - 判定フロー（§2.2）に従い、根因カテゴリを1つ以上特定
   - 確信度が低い場合は複数候補を提示し、起動者に選択を促す

3. why_chain 生成
   - 選定されたカテゴリに対して5-whys的展開を行う
   - 「なぜspecに書かれなかったか」まで掘り下げる

4. fix_target_file 特定
   - 根因カテゴリと why_chain に基づき、どのテンプレ/プロンプト/agent定義を変更すべきかを特定
   - カテゴリ-ファイルのマッピングテーブル（§5.3）を参照

5. diff提案生成
   - fix_target_file の現在の内容を読み込み
   - 根因に対処する具体的な追加・変更・削除を提案

6. postmortem記録の生成と配置
   - フロントマター付きMarkdownを生成
   - `knowledge/postmortems/pm-<timestamp>.md` として出力
   - `index.yaml` を更新（カテゴリ別カウント・priority_queue）

7. PRの準備
   - postmortem記録とdiff提案を含むブランチを作成するための指示を出力
```

### 5.3 根因カテゴリ → fix_target_file マッピング

| 根因カテゴリ | 主な fix_target_file | 補足 |
|------------|---------------------|------|
| `requirements-gap` | `spec/templates/requirements.md.tpl` | 受入基準・制約・非機能要件のセクションを強化 |
| `design-gap` | `spec/templates/design.md.tpl` | エラーハンドリング・境界条件・技術選定根拠のセクションを強化 |
| `tasks-gap` | `spec/templates/tasks.md.tpl` | タスク粒度ガイドライン・完了条件テンプレートを追加 |
| `context-gap` | `spec/templates/requirements.md.tpl` または `prompts/phases/requirements-phase.md` | 「前提コンテキストのリンクリスト」セクションを追加するか、プロンプトで列挙を促す |
| `drift` | `prompts/phases/tasks-phase.md` または `agents/[review-agent]` | レビュー指示を強化。specとの照合チェックリストを追加 |
| `review-gap` | `prompts/phases/tasks-phase.md` | QAチェックリストにカバレッジ要件を追加 |

---

## 6. PR還流ワークフロー

### 6.1 全体フロー

```
[起動者] /spec-postmortem 実行
    |
    | スキルがブランチを作成する指示を出力
    v
[起動者] git checkout -b postmortem/<feature>/<timestamp>
[起動者] postmortem記録をコミット
[起動者] diff提案をコミット（fix_target_fileへの変更として）
[起動者] PR作成（テンプレートを使用）
    |
    v
[レビュアー（最低1名）] PRレビュー
    |
    |-- APPROVE → マージ担当者がマージ
    |-- 修正要請 → 起動者が修正
    v
[マージ] メインブランチへマージ
    |
    v
[CHANGELOG.md 更新] マージ時に自動または手動で記録
```

### 6.2 PRテンプレート

```markdown
## postmortem PR

**対象機能**: [機能名]
**postmortem ID**: [pm-YYYYMMDD-HHMMSS]
**根因カテゴリ**: [タクソノミーカテゴリ]

### 変更の概要

[何を変更し、なぜその変更が根因に対処するかを1-3文で]

### 変更ファイル

- `knowledge/postmortems/pm-*.md` — postmortem記録の追加
- `knowledge/postmortems/index.yaml` — 集約インデックスの更新
- `[fix_target_file]` — テンプレ/プロンプト/agent定義の改善

### レビューチェックリスト

- [ ] why_chain が根因を適切に特定しているか
- [ ] diff提案が根因に対処しているか（不必要な変更を含んでいないか）
- [ ] テンプレ変更が既存の機能開発に悪影響を与えないか
- [ ] author_hash による匿名化が適切か
```

### 6.3 承認フローとSLA

| フェーズ | 担当 | SLA |
|---------|------|-----|
| PRレビュー | レビュアー（1名以上） | 3営業日以内 |
| 修正対応 | 起動者 | 3営業日以内 |
| マージ承認 | チームリード | レビュー承認後2営業日以内 |

SLAを超過した場合はPR上でリマインドを行う（自動化はロードマップE）。

### 6.4 PRのクローズ条件

- **merged**: 承認済みでメインブランチにマージされた
- **closed（却下）**: 根因分析が誤っている、またはdiff提案が有害と判断された場合。postmortem記録の `status` を `closed` に更新し、却下理由をコメントとして記録する

---

## 7. versioning と CHANGELOG 方針

### 7.1 バージョニング対象

以下のファイルをバージョニング対象とする。

- `spec/templates/*.tpl`
- `prompts/phases/*.md`
- `agents/` 配下のagent定義ファイル

### 7.2 バージョン番号スキーム

セマンティックバージョニング（`vMAJOR.MINOR.PATCH`）を採用する。

| 変更種別 | バージョン上げ幅 | 例 |
|---------|---------------|---|
| 後方互換を壊す変更（セクション削除、必須項目追加） | MAJOR | `v1.0.0 → v2.0.0` |
| 後方互換な追加（新セクション追加、選択肢追加） | MINOR | `v1.0.0 → v1.1.0` |
| 文言修正・誤字修正 | PATCH | `v1.0.0 → v1.0.1` |

各テンプレ・プロンプトファイルの先頭にバージョンを記載する。

```markdown
<!-- version: v1.2.0 | last_updated: 2026-06-18 -->
```

### 7.3 CHANGELOG.md 記述ルール

```markdown
## [v1.2.0] - 2026-06-18

### Changed
- `spec/templates/requirements.md.tpl`: 非機能要件セクションを追加
  - postmortem: pm-20260618-120000 (requirements-gap)

### Added
- `spec/templates/requirements.md.tpl`: 前提コンテキストリンクリストを追加
  - postmortem: pm-20260620-093000 (context-gap)
```

postmortem IDとの紐付けを必須にすることで、「なぜこの変更をしたか」の追跡可能性を確保する。

### 7.4 退行防止

- ロードマップDで過去failureをevalケース化する際に、CHANGELOG + postmortem IDの紐付けが重要な役割を果たす
- テンプレ変更をマージする際は、既存の機能開発（進行中のブランチ）への影響を確認する（破壊的変更の場合はアナウンスを先行させる）

---

## 8. 同種根因の重複・頻度集約（最小設計）

### 8.1 集約の仕組み

`/spec-postmortem` スキルが `index.yaml` を更新する際に、以下を行う。

1. `by_category[<カテゴリ>].count` をインクリメント
2. `by_category[<カテゴリ>].postmortem_ids` にIDを追記
3. `priority_queue` を count降順で再ソートし、上位5件を更新

### 8.2 重複検出

同一機能に対して複数回 `/spec-postmortem` を実行した場合のデdup処理。

- `target_feature` + `root_cause_category` の組み合わせが既存のpostmortemと一致する場合、スキルは既存IDを提示して「新規作成か更新かを選択」するよう促す
- 異なる機能で同じカテゴリが出た場合は新規IDで追加（重複ではない）

### 8.3 優先度の判断基準

`priority_queue` のcountが2以上になった根因カテゴリは、次のチームレトロスペクティブでの議題候補とする（運用ルールとして定める。自動通知はロードマップE）。

### 8.4 匿名化の運用

- `author_hash = sha256(github_user_id)[:8]`
- `index.yaml` のサマリーでは `author_hash` を集計しない（プライバシー観点）。個別postmortemファイルのみに記載
- 同一ハッシュが複数のpostmortemに出現する場合も、ダッシュボード等での個人特定には使用しない

---

## 9. 後続ロードマップ（設計見通し）

### C: Context Provenance（コンテキスト来歴追跡）

実際にClaudeがロードしたコンテキストと、specがリンクした前提ドキュメントのdiffを取ることで、`context-gap` をさらに細分化する。

- **availability gap**: specにリンクが書かれていたが、実際にロードされなかった
- **retrieval gap**: specにリンクすら書かれていなかった

現在の `/spec-postmortem` は起動者の主観と証跡から `context-gap` を推定するが、Cでは実際のロードログを根拠にすることで精度が上がる。実装にはClaudeのコンテキストロードログを取得する仕組みが必要（Kiro側の拡張が必要になる可能性あり）。

### D: spec-failure → Eval 回帰ガード

postmortem記録を元に、過去のfailureをevalケースとして自動生成する。テンプレ/プロンプト/agent定義の変更をマージする前に、evalケースを実行して退行がないことを確認する。

- postmortem ID と eval ケース ID を紐付けることで、「どの問題に対処するためのevalか」を追跡可能にする
- CHANGELOG の postmortem ID 紐付け（§7.3）が基盤になる

### E: チーム品質ダッシュボード

`index.yaml` と各 postmortem のフロントマターを集計し、以下を可視化する。

- spec種別（requirements / design / tasks）ごとの根因カテゴリ分布
- 月次トレンド（改善後に同種根因が減少しているか）
- priority_queue のリアルタイム表示とSlack通知

フロントマターをパースするスクリプト（`grey-matter` または `python-frontmatter`）で実現でき、静的サイト（GitHub Pages等）として配信できる。

---

## 10. 設計上の残課題と今後の判断ポイント

| 課題 | 内容 | 判断タイミング |
|------|------|-------------|
| トランスクリプトのプライバシー | 人↔Claudeのトランスクリプトを共有リポにコミットする場合、機密情報が含まれる可能性がある。postmortem記録に含める場合は引用のみとし、全文は含めないことを推奨 | MVP運用開始前 |
| author_hashの粒度 | sha256の先頭8文字で衝突リスクはほぼないが、チーム規模が大きくなった場合に見直しが必要 | チーム規模10名以上になったとき |
| index.yamlの競合 | 複数人が同時にpostmortemを追加するとindex.yamlにコンフリクトが発生する可能性がある。PRがシリアルにマージされる限り問題は小さいが、頻度が上がった場合はDBへの移行を検討 | postmortemが月10件以上になったとき |
| fix_target_fileが存在しないケース | 根因が「タクソノミー外」のときは新規カテゴリのissue起票を促す | 発生都度 |
