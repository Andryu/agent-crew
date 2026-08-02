# チームSDD品質改善還流ループ ― 提案 / レビュー依頼

> **⚠ agent-crew での採否**: 本提案は不採用（Rejected）。agent-crew の仕様管理は軽量機能仕様書方式 — `docs/adr/ADR-015-spec-driven-development.md` を参照。

> **目的**: チームのSDDオーケストレーション（Kiro系）で「開発させたが品質が悪かった」が起きたとき、その原因を構造的に分析し、**改善を特定ファイル（spec/requirementsテンプレ・フェーズプロンプト・agent定義）へのPRとして共有リポに還流させ、チーム全員に伝播させる**仕組みの提案。
>
> **レビューしてほしい観点**: ①根因タクソノミーの粒度は妥当か ②PR還流ワークフローがチームの運用に乗るか ③MVPスコープの切り方は適切か ④プライバシー（トランスクリプト・author_hash）の扱い

---

## 1. 背景と課題

SDDオーケストレーションでは品質問題のほとんどが**3か所**に集約される。

```
requirements.md ──①──▶ design.md ──②──▶ tasks.md ──③──▶ 実装
   │
   ①requirements-gap : 受入基準/制約/非機能要件の欠落・曖昧さ（最も多い根因）
   ②design-gap       : 設計が要件を満たさない / 技術選定の根拠欠落 / 境界条件の考慮漏れ
   ③drift            : specは十分だったが実装が逸脱（レビュー/実行プロセスの問題）
```

**チーム特有の課題**: これらの学びが個人の頭・個人のローカル設定に閉じてしまい、蓄積・共有されない。「同じ失敗を別の人がまた踏む」「Aさんが見つけた改善がAさんの手元で死ぬ」。

前提（チームの現状）:
- **SDD基盤 = Kiro系**: 各機能を `requirements.md` / `design.md` / `tasks.md` の3ファイルで進める。これがコンテキストの本体で、git管理されている。
- **オーケストレーション設定（agent定義・フェーズプロンプト・テンプレ）は既に共有GitHubリポにコミット済み** → 真実源リポは既に存在する。新規Hub構築は不要。**そのリポに改善が還流する経路を足す**のがこの提案の核。
- **検知トリガー = 人が気づいたとき（手動）**。

**ゴール**: 品質問題を印象論で終わらせず、**必ず特定ファイルへの差分提案（PR）に着地させる**。

---

## 2. アイデア全体像（6案）

| # | 案 | 解く課題 | 位置づけ |
|---|---|---|---|
| **A** | **`/spec-postmortem` スキル** | 品質問題→根因分析→改善提案を構造化 | 🌟MVP中核 |
| **B** | **改善PR還流ループ** | 改善が個人に閉じず共有リポに還流・伝播 | 🌟MVP土台（共有リポは既存なので経路を足すだけ） |
| C | Context Provenance | 「必要なコンテキスト」を実測で特定（availability gap / retrieval gap の切り分け） | 後続 |
| D | spec-failure → Eval 回帰ガード | 直した改善が他の人によって退行するのを防ぐ | 後続 |
| E | チーム品質ダッシュボード | spec/フェーズ/作成者単位で系統的欠陥を可視化 | 後続 |
| F | versioning + CHANGELOG | テンプレ/プロンプト改善の伝播と追跡可能性 | A/Bに内包 |

**MVP = A + B**。共有リポをHubにして `/spec-postmortem` を実際の「品質が悪かった案件」1件に流し、出た改善をテンプレへのPRにする。これが回れば C/D/E は後乗せできる。

---

## 3. MVP全体フロー

```
[品質問題に気づいた人]
        │  /spec-postmortem を手動起動
        ▼
[/spec-postmortem スキル]
        │  入力: requirements.md / design.md / tasks.md + 実装diff(or PR) + トランスクリプト(任意) + 「何が悪かったか」の一言
        │  ├─ 根因タクソノミーで分類（6カテゴリ）
        │  ├─ why_chain を5-whysで構造化
        │  ├─ fix_target_file を特定（カテゴリ→ファイルのマッピング）
        │  ├─ postmortem記録を生成（フロントマター付きMD）
        │  └─ 改善diff提案を生成
        ▼
[共有リポ knowledge/postmortems/]
        │  index.yaml に根因カテゴリ・頻度を集約（匿名）
        ▼
[改善PR → テンプレ / プロンプト / agent定義]
        │  レビュー（1名以上）→ 承認 → マージ → CHANGELOG記録
        ▼
[チーム全体に改善が伝播]
```

---

## 4. 根因タクソノミー（固定6分類）

Kiro 3フェーズに対応。複数カテゴリの同時指定を許容（例: `requirements-gap` + `context-gap`）。

| カテゴリID | 名称 | 定義 | 典型的な証跡 |
|-----------|------|------|------------|
| `requirements-gap` | 要件の欠落・曖昧さ | 受入基準/制約/非機能要件が未記載または曖昧で、実装者が誤った仮定を置いた | 受入基準が「正常に動くこと」程度しか書かれていない |
| `design-gap` | 設計の欠落・誤り | 設計が要件を満たさない/技術選定根拠が欠落/境界条件の考慮なし | design.md にエラーハンドリング設計がない |
| `tasks-gap` | タスク分解の粗さ | 粒度が大きすぎる/依存関係未記述で並行作業が破綻/完了条件が曖昧 | タスク1件が「APIを実装する」だけ |
| `context-gap` | 前提コンテキストの未リンク | specが既存コード・設計・docへのリンクを欠き、実装者がコンテキストを持てなかった | 既存の認証フローへの参照がない |
| `drift` | spec-実装間の乖離 | specは十分だったが実装が逸脱。specでなくレビュー/実行プロセスの問題 | 設計ではDBトランザクション使用だが実装で未使用 |
| `review-gap` | QA・受入チェックのすり抜け | 根因がspec側でもQAフェーズで発見できなかった | テスト仕様にエラーケースが含まれていない |

### 判定フロー

```
問: specに書かれていなかったことが原因か？
  YES → どのフェーズに書かれるべきだった？
        requirements.md → requirements-gap / context-gap
        design.md       → design-gap
        tasks.md        → tasks-gap
        前提リンク欠落   → context-gap
  NO  → specはあったが守られなかった？
        YES → drift
        NO  → QAで本来発見できたはず？
              YES → review-gap
              NO  → タクソノミー外（新規カテゴリをissue起票）
```

---

## 5. postmortem記録スキーマ（フロントマター付きMarkdown）

> **設計判断**: 純JSONは「PRで人が読む」用途に不向き、純散文は「集計」に不向き。フロントマター付きMarkdownで両立。`id/category/fix_target_file/author_hash/status` を機械可読フロントマターに、why_chain・証跡・差分提案を散文本文に。ダッシュボード(E)はフロントマターのパースだけで作れる。

```yaml
---
id: "pm-YYYYMMDD-HHMMSS"               # タイムスタンプベース。ファイル名にも使う
target_feature: "機能名または機能ディレクトリパス"
root_cause_category:                    # 1つ以上
  - requirements-gap
source_repo: "github.com/org/repo"
fix_target_file:                        # 改善提案の対象。1つ以上
  - "spec/templates/requirements.md.tpl"
author_hash: "sha256(github_id)[:8]"    # 疑似匿名化
status: "draft"                         # draft | proposed | merged | closed
created_at: "2026-06-18T00:00:00Z"
---
```

本文構造: `## 概要` / `## why_chain（5-whys）` / `## 証跡（evidence）` / `## 改善提案（変更前→変更後→変更理由）` / `## 未解決事項`

---

## 6. 共有リポのディレクトリ構成（既存リポに追加）

```
<shared-orchestration-repo>/
├── knowledge/
│   └── postmortems/
│       ├── index.yaml              # 根因カテゴリ別の集約インデックス
│       ├── pm-20260618-120000.md   # 個別postmortem記録
│       └── ...
├── spec/templates/
│   ├── requirements.md.tpl         # ← 改善対象になりうるファイル群
│   ├── design.md.tpl
│   └── tasks.md.tpl
├── prompts/phases/
│   ├── requirements-phase.md
│   ├── design-phase.md
│   └── tasks-phase.md
├── agents/                         # agent定義ファイル群
└── CHANGELOG.md                    # テンプレ/プロンプト/agent定義の変更履歴
```

`index.yaml` は `/spec-postmortem` がpostmortem追加のたびに自動更新（カテゴリ別count・priority_queue上位5件）。`author_hash` はサマリーには集計せず個別ファイルのみ（プライバシー）。

---

## 7. 根因カテゴリ → 改善対象ファイル マッピング

「印象論で終わらせない」核。各カテゴリが必ず特定ファイルへの差分に落ちる。

| 根因カテゴリ | 主な改善対象 | 補足 |
|------------|------------|------|
| `requirements-gap` | `spec/templates/requirements.md.tpl` | 受入基準・制約・非機能要件セクションを強化 |
| `design-gap` | `spec/templates/design.md.tpl` | エラーハンドリング・境界条件・技術選定根拠を強化 |
| `tasks-gap` | `spec/templates/tasks.md.tpl` | タスク粒度ガイドライン・完了条件テンプレを追加 |
| `context-gap` | `requirements.md.tpl` または `prompts/phases/requirements-phase.md` | 「前提コンテキストのリンクリスト」セクションを追加 / プロンプトで列挙を促す |
| `drift` | `prompts/phases/tasks-phase.md` または `agents/[review-agent]` | spec照合チェックリストを追加 |
| `review-gap` | `prompts/phases/tasks-phase.md` | QAチェックリストにカバレッジ要件を追加 |

---

## 8. PR還流ワークフロー

```
/spec-postmortem 実行 → ブランチ作成指示を出力
  └─ git checkout -b postmortem/<feature>/<timestamp>
     postmortem記録 + diff提案(fix_target_fileへの変更)をコミット → PR作成
        └─ レビュアー(1名以上)レビュー
             ├─ APPROVE → マージ → CHANGELOG更新
             └─ 修正要請 → 起動者が修正
```

**PR粒度: 1根因1PR を推奨**（バッチはレビュー負荷と差し戻し切り分けを悪化させる。同一ファイルへの軽微修正のみ例外的にまとめてよい）。

**SLA案**: PRレビュー3営業日 / 修正対応3営業日 / マージ承認は承認後2営業日。

**CHANGELOG はpostmortem IDと紐付け必須**（「なぜこの変更をしたか」の追跡可能性。ロードマップDのeval基盤にもなる）:

```markdown
## [v1.2.0] - 2026-06-18
### Changed
- spec/templates/requirements.md.tpl: 非機能要件セクションを追加
  - postmortem: pm-20260618-120000 (requirements-gap)
```

---

## 9. 頻度集約（同じ失敗が重なったら優先的に直す）

- `/spec-postmortem` が `index.yaml` の `by_category[*].count` をインクリメントし `priority_queue` を再ソート。
- **count ≥ 2 の根因カテゴリは次のチームレトロの議題候補**（運用ルール。自動通知はロードマップE）。
- 同一機能×同一カテゴリの再実行はデdup（既存IDを提示し新規/更新を選択）。

---

## 10. バージョニング方針

対象: `spec/templates/*.tpl` / `prompts/phases/*.md` / `agents/*`。セマンティックバージョニング。

| 変更種別 | 上げ幅 |
|---------|-------|
| 後方互換を壊す（セクション削除・必須項目追加） | MAJOR |
| 後方互換な追加（新セクション・選択肢追加） | MINOR |
| 文言・誤字修正 | PATCH |

各ファイル先頭に `<!-- version: v1.2.0 | last_updated: 2026-06-18 -->`。

---

## 11. 後続ロードマップ（見通しのみ）

- **C: Context Provenance** — 実際にロードしたコンテキスト vs specがリンクした前提の diff を取り、`context-gap` を *availability gap*（リンクはあったが読まれず）/ *retrieval gap*（リンクすら無し）に細分化。実測で「必要なコンテキスト」を特定。Kiro側のロードログ取得拡張が必要になりうる。
- **D: spec-failure → Eval 回帰ガード** — 過去failureをevalケース化し、テンプレ/プロンプト変更を配布前に検証。退行防止。postmortem ID ⇔ eval ID 紐付け（§8のCHANGELOG連携が基盤）。
- **E: チーム品質ダッシュボード** — `index.yaml` + 各フロントマターを集計し、根因カテゴリ分布・月次トレンド・priority_queue・Slack通知を可視化。GitHub Pages等で配信可能。

---

## 12. 設計上の残課題 / 判断ポイント

| 課題 | 内容 | 判断タイミング |
|------|------|-------------|
| トランスクリプトのプライバシー | 機密情報が含まれうる。postmortem記録には**引用のみ**とし全文は含めない方針を推奨 | MVP運用開始前 |
| author_hashの粒度 | sha256先頭8文字。衝突リスクはほぼ無いがチーム拡大時に見直し | チーム10名以上 |
| index.yamlの競合 | 同時追加でコンフリクトしうる。シリアルマージなら影響小。頻度増ならDB移行検討 | 月10件以上 |
| タクソノミー外の根因 | 新規カテゴリのissue起票を促す | 発生都度 |

---

## 13. レビュー後の次アクション候補

1. このタクソノミー・ワークフローをチームの実運用に合わせて調整
2. `/spec-postmortem` スキル本体を実装（evalケースは過去のKiro失敗例から起こす）
3. 共有リポに `knowledge/postmortems/` と PRテンプレ・CHANGELOG運用を追加
4. 実際の「品質が悪かった案件」1件でドッグフーディング
