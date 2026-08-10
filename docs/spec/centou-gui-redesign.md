# GUI再設計: Notion案 × Claude Artifact案 — 社内・プロダクト別運用への転換

作成日: 2026-08-10
ステータス: Draft（オーナー承認待ち）
起案: team-lead（Fable）
親ドキュメント: docs/spec/centou-insight-management-design.md
前提: 社内限定・BigQueryマスタ・AI前提。HTML版（Claude Artifact）が図付き完全版

---

## §1 前提の更新とドメイン修正

### 決定事項

- **SaaSとして売らない。社内利用に限定**。親ドキュメント§4〜§8（マルチテナントSaaS構成）は「将来外販するなら」のアーカイブ扱い
- **テナント・Workspaceの概念を廃止**。アクセス制御はGoogleアカウント（BQ IAM）とNotionの社内共有で足りる
- **社内のプロダクトごとに扱う** — product_id を導入

### ドメイン修正

```
products(id, name, status)   -- 社内プロダクトのマスタ

-- workspace_id を全テーブルから削除し product_id に置き換え
research_questions(id, product_id, question, status)
sources(id, product_id, research_question_id, ...)
facts(id, product_id, source_id, ...)
insights(id, product_id NULLABLE, ...)   -- NULL = プロダクト横断（全社）の知見
suggestions(id, product_id, ...)
audit_logs(id, product_id, ...)

-- workspaces / members は廃止
```

- insights.product_id のみ NULL 可（全社共通の知見）
- 検索・AI照合はプロダクト内＋全社がデフォルト。重複リサーチ防止は横断検索が担う
- BQは product_id でクラスタリング（テナント分離のような厳密さは不要）

---

## §2 案A: Notion GUI — 429制限の調査結果と対策

### Notion APIの制限（調査結果）

| 制限 | 内容 | 影響 |
|---|---|---|
| レート制限 | インテグレーション1つあたり**平均3リクエスト/秒**（バースト若干可）。超過で **HTTP 429**（rate_limited）＋ Retry-After ヘッダ | 大量レコードの一括同期が最大の敵 |
| ペイロード | 1リクエスト最大 **500KB・1000ブロック**。children配列は1回**100ブロック**、ネスト2階層まで | 長文はページ分割append |
| テキスト | リッチテキスト1要素 2,000字 | 原文はGCS/BQ、Notionは要点のみ（方針と合致） |
| クエリ | DBクエリ1回100件（カーソルページング） | 差分取り込み設計（親10.4）で対応済み |
| UI実用限界（裏取り済み） | 公式仕様ではなく体感性能の問題。**rollup・formula・リレーションが多いDBは2,000〜3,000行**から、そうでなくても**1〜2万行**で表示・検索の劣化が顕著という報告が多数。Notion公式にも読み込み最適化のヘルプあり（フィルタ・表示プロパティ削減・ビュー読み込み上限を推奨）。保存上限自体は1DB約25万行 | 「人が触る対象だけ投影」原則の根拠。投影DB規約（下記）で回避 |

### 429の現実的な目安

- 議事録1本の取り込み（**実測: ファクト約38件**＋提案38件＋本文）≒ 約90〜120リクエスト ≒ **40秒前後** → 定期バッチなら依然問題なし
- 過去議事録50本のバックフィル ≒ 5,000リクエスト ≒ **約30分** → 夜間バッチ必須、対話的には無理
- 全インサイト200件のプロパティ更新 ≒ 70秒 → **日次なら可、毎時は邪魔**
- 結論: **定期バッチの書込なら実用圏。「画面のための大量常時同期」をした瞬間に破綻**

### 429前提の同期設計（親10.4への追記）

1. 書込は単一キューで直列化。1リクエストごとに350ms空ける（秒2.8件の自主制限）
2. 429を受けたら Retry-After 秒だけ完全停止。再発なら指数バックオフ＋ランダムなゆらぎ
3. content_hash が変わったレコードだけ書く（全件書き直し禁止）
4. 投影絞り込み（active/pending/直近のみ）が429対策も兼ねる
5. 夜間全件照合はBQ側で突合し、修復の書込だけNotionへ低速で
6. 429が日常化したら延命せず移行トリガー（親10.8）として扱う

### 投影DBの性能規約と想定データ量

UI劣化は行数だけでなく**プロパティの重さ**で決まる。投影DBには次の規約を課す:

- **rollup・formula・重いリレーションを使わない** — 確信度などの計算値はBQが計算した結果を「ただの数値・セレクト」として書く。Notionに計算させない（2,000行で重くなるDBと2万行でも軽いDBの分かれ目）
- **ビューには必ずフィルタと読み込み上限（load limit）**を設定し、表示プロパティを絞る
- **投影上限の目安**: Insights ≤ 1,000行／Facts ≤ 2,000行／EvidenceLinks ≤ 3,000行／Suggestions は pending のみ。超えたら古いものをNotionから外す（BQには全量残る）

**想定データ量（実測で更新）**: 議事録1本≒**ファクト約38件（実測）**。週2〜3本なら**年間4,000〜6,000ファクト**、インサイトは年間数十〜百件。Insightsは安全圏だが、Factsは**直近90日の投影だけで約1,200〜1,500件**に達し、リンク済み分を足すと上限2,000にほぼ到達する。対応: **投影窓を「直近30日＋リンク済み」に短縮**し、ファクトの一覧・検索は早期にArtifact＋MCP（案B）またはSlack検索でBQ直読に寄せる。

> **提案 — レビュー運用の変更（要オーナー判断）**
> 38件/本だと個別承認は週76〜114件のファクトレビューになりInbox疲れで破綻する。
> 提案: **ファクトは「議事録1本＝1レビュー」の一括承認**（一覧を見て、除外したいものだけ外してまとめて承認）。ファクトは原文grounding必須で捏造リスクが低く、一括でも安全性は保てる。
> **個別の丁寧なレビューは new_insight・update_insight・反証リンクに集中**——人間の注意力を「事実の確認」ではなく「解釈の判断」に使う。

### 相性まとめ

- 得意: レビューInbox・閲覧・コメント・通知・モバイル・レポート配布
- 苦手: 大量常時同期・分析キャンバス・リアルタイム・リッチな内訳表示

---

## §3 用語整理: Artifact・コネクタ・MCPでできること

1行ずつ: **Artifact＝claude.aiが配信するWebページ／コネクタ＝claude.aiに追加する外部サービス接続／MCP＝そのコネクタを自作するための標準規格**

- Artifactは既定では静的で、外部サイト（BQ API等）への直接通信はセキュリティ設定で遮断される
- ライブ機能（capabilities）として現在使えるのは2つ: `downloads`（閲覧者へのファイル保存）と `mcp`（**閲覧者本人のclaude.aiコネクタをページ内から呼ぶ**）
- 自作のAPIサーバをMCP形式で作れば「カスタムコネクタ」としてclaude.aiに登録でき、①チャットのClaude ②mcpを宣言したArtifact の両方から呼べる

> **「ArtifactからBQ更新はできる？」への回答（調査で更新）**
> 直接は不可だがコネクタ経由なら可能。しかも**閲覧（読み取り）だけなら自作MCPすら不要**——Googleが公式のマネージドBigQuery MCPサーバ（bigquery.googleapis.com/mcp、OAuth＋IAM）を提供しており、Claudeのコネクタとして登録すればArtifactからクエリ実行・一覧取得ができる。**自作MCPが必要になるのは書込（承認反映・キャンバス保存）をArtifactでやりたくなってから**。

制約（正直に）:
- 閲覧者はclaude.aiログイン＋コネクタ利用への本人同意が必要（社内なら許容範囲）
- mcpを宣言したページは外部公開共有できない（社内限定の本件では問題なし）
- 呼び出しは閲覧者本人の資格情報で実行される → 「誰が承認したか」が自然に監査に残る利点
- Artifactは開いている間だけ動く。バッチ処理（取り込み・照合・再計算）は従来どおりClaude定期ジョブの仕事
- **検証状況**: 本セッションではコネクタ未接続のため window.claude.mcp の実挙動は未検証。実装フェーズの最初に実機確認する

---

## §4 案B: Claude Artifact ＋ 自作MCP（BQゲートウェイ）

```
[閲覧者のブラウザ: Artifactページ(SPA)]
  Inbox / 検索 / インサイト詳細 / 分析キャンバス / 確信度内訳
   │ window.claude.mcp
   ▼
[claude.ai コネクタ基盤]（閲覧者本人の認証・同意）
   │ カスタムコネクタ
   ▼
[自作MCPサーバ (Cloud Run)] ── BigQuery（マスタ）読み書き＋audit_logs追記
   ▲
[Claude定期ジョブ]（従来どおり）: 取り込み・照合・提案生成・確信度再計算はArtifactを経由せずBQへ直接
```

**ポイント: 案BではBQ⇄Notionの双方向同期問題が消える。ArtifactはBQを直接読み書きするため、投影も同期ドリフトも存在しない。**

### 閲覧だけなら公式BigQueryコネクタで足りる（自作MCP不要）

- **使うもの**: Google公式のマネージドBigQuery MCPサーバ（bigquery.googleapis.com/mcp）。クエリ実行・データセット/テーブル一覧・メタデータ取得のツールを持つ。Claudeのコネクタとして追加し、閲覧者はGoogleアカウントでOAuth認証
- **セットアップは設定のみ**: ①コネクタ追加 ②閲覧者のGoogleアカウントに対象データセット限定で roles/bigquery.dataViewer＋roles/bigquery.jobUser を付与、の2手順。サーバ構築・コード不要
- **読み取り専用はIAMで構造的に強制**: dataViewerしか持たない閲覧者はDML（書込SQL）が権限エラーで失敗する
- **できる画面**: 検索・ファクト/インサイト一覧・詳細（確信度内訳・supports/contradicts）・体系図の閲覧。38件/本問題で溢れるファクト全量閲覧の受け皿がすぐ作れる
- **できないこと**: 承認・編集・キャンバス保存などの書込。当面はNotion Inboxで行い、Artifactでやりたくなったら下記の自作MCPを建てる

### 書込が必要になったら: 自作MCPサーバのツール設計

| ツール | 内容 | 書込 |
|---|---|---|
| search | ハイブリッド検索（BQ VECTOR_SEARCH）。product指定/横断 | — |
| get_insight | 詳細＋確信度内訳＋エビデンス一覧（supports/contradicts） | — |
| list_suggestions | pending提案一覧（Inbox用） | — |
| review_suggestion | accept / accept_with_edit / reject。反映＋audit_logs追記 | あり |
| update_insight | statement/description/statusの編集（版を残す） | あり |
| save_canvas / load_canvas | キャンバス配置の保存・読込 | あり |
| promote_group | グループ→インサイト昇格（EvidenceLink一括生成） | あり |

- 書込系ツールはすべて audit_logs 追記込み。閲覧者本人に紐づくため actor 特定が構造的に保証される
- 認証: カスタムコネクタのOAuthでclaude.ai↔MCPサーバ間を保護。BQアクセスはサーバ側サービスアカウント（個人ごとのBQ権限配布が不要になる）

### 案Bの追加価値と弱点

- **分析キャンバスが実現できる**（Notionでは構造的に不可能）。ドラッグ&ドロップ付箋→グループ化→「昇格」ボタン→promote_group
- 弱点: コメント・議論・通知がない／claude.aiログインの一手間／MCPサーバの構築運用が増える／window.claude.mcp実挙動が未検証（縦スライスで最初に検証）

---

## §5 比較と推奨

| 観点 | 案A: Notion | 案B: Artifact＋MCP |
|---|---|---|
| 提案レビュー（Inbox） | ◎ コメント通知込みで今すぐ | ○ UI自由だが通知なし |
| 閲覧・共有・モバイル | ◎ | △ claude.aiログイン必要 |
| コメント・議論 | ◎（Notionがマスタ） | × |
| 分析キャンバス | × 不可能 | ◎（最大価値） |
| 確信度内訳等リッチ表示 | △ | ◎ |
| 大量レコード | ×（429・1万行限界） | ◎ BQ直読 |
| 同期の複雑さ | 高（双方向同期一式） | **低（同期問題が消える）** |
| 構築コスト | 低 | 中（MCPサーバ＋SPA） |

> **推奨 — ハイブリッド（画面ごとに得意な方）**
> Notion＝協働の場（議論・コメント・レポート配布・軽い閲覧）。Artifact＋MCP＝作業の場（キャンバス・横断検索・確信度深掘り・提案レビュー）。この分担なら Notion同期は「人が読んで議論する分」だけに減り、429と同期ドリフトのリスクが両方小さくなる。

---

## §6 ロードマップ更新

| 段階 | 内容 | ゲート |
|---|---|---|
| MVP-0（2〜4週） | BQ＋Notion＋Claude定期ジョブで縦1ループ。product_id は初日から | 承認率50%／週次レビュー習慣／意思決定変化1件 |
| v1a（+1〜2週） | **閲覧専用Artifact**: 公式BigQueryコネクタ（自作MCP不要）で検索・一覧・詳細・確信度内訳。window.claude.mcp実挙動もここで検証。承認は引き続きNotion Inbox | チームが閲覧Artifactを日常的に開く。実挙動確認完了 |
| v1b（+1〜2ヶ月） | 書込用の自作MCPを追加し、承認・キャンバス編集・昇格をArtifactで実装。Notionはコメント・配布に役割縮小 | キャンバス経由の昇格が月N件 |
| v2 | 取り込み自動化（Meet/Slack/Chatwork常時化）、週次レポート本運用 | — |

---

## §7 未決事項

- **window.claude.mcp の実挙動検証**（本設計最大の技術リスク。v1a冒頭で潰す）
- カスタムコネクタの認証設計（OAuth、社内メンバー確認）
- claude.aiログインの一手間をチームが受け入れるか（拒否ならNotion Inbox継続）
- Notionコメント（協働データ）とBQ知見の接続導線（コメント→ファクト起票の要否）
- MCPツールの粒度（個別ツール vs 汎用query。監査と安全性は個別が有利）

## 参考資料

- [Notion API Request limits（公式）](https://developers.notion.com/reference/request-limits)
- [How to Handle Notion API Request Limits](https://thomasjfrank.com/how-to-handle-notion-api-request-limits/)

## 変更履歴

- 2026-08-10: 初版。オーナー決定（SaaS化しない・社内・product_id・テナント廃止）と、GUI 2案（Notion / Claude Artifact＋自作MCP）の比較設計、Notion 429調査、Artifact・コネクタ・MCPの整理
