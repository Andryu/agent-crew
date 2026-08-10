# Centou型インサイトマネジメントシステム 設計書

作成日: 2026-08-10
ステータス: Draft（オーナー承認待ち）
起案: team-lead（Fable）
前提: 新規プロダクト（SaaS志向・マルチテナント）／技術スタックは本書では確定しない／AI前提設計
関連: HTML版（Claude Artifact）が図付き完全版。本ファイルはリポジトリ正本
参考: Centou（alma社, centou.jp）/ Tomer Sharon "Atomic UX Research" / Dovetail / EnjoyHQ

---

## 概要

Centou型のインサイトマネジメントSaaS（仮称: **Nugget**）の設計。PdM・プロダクトデザイナー・フルスタックエンジニアの3視点で、ドメインモデル／UX／システムアーキテクチャ／AIパイプラインを定義する。

自社開発構成（§4〜§8, アーキテクチャ1）に加え、オーナー決定に基づく **BigQuery（マスタ）× Notion（GUI）× Claude 構成の本設計（§10, アーキテクチャ2）** を併記する。§10は責任範囲（10.2）とデータ配置（10.3: マスタに残すデータ／Notionで保持するデータ）を核に、同期設計・破綻ポイント評価・独自ロードマップまで定義する。

---

## §1 プロダクト概要

### 1.1 解決する4つの構造的課題

| 課題 | 現状の症状 | 解き方 |
|---|---|---|
| インサイトの属人化 | リサーチ結果が個人のメモ・記憶に散在 | ファクト単位で構造化し、検索可能な組織資産に |
| 意思決定の遅さ | 「あの調査どこ？」から始まる会議 | セマンティック検索＋Slackエージェントで数秒到達 |
| 重複リサーチ | 過去に同じ問いを調べた事実に気づけない | 新規調査計画時に類似インサイトを自動提示 |
| 施策の打率の低さ | エビデンスの弱い思い込みが施策になる | 確信度スコアと反証の明示 |

### 1.2 中核コンセプト

- **Atomic UX Research の階層**: Source（調査活動・生データ）→ Fact（解釈を含まない事実の最小単位）→ Insight（解釈）→ Opportunity（機会）→ Recommendation（提言）
- **Updatable Asset**: インサイトは「作って終わり」ではなく、新エビデンス到着のたびにAIが更新・統合・反証を提案し続ける生きた資産
- **AI-native / Human-in-the-loop**: AIは抽出・照合・提案まで。確定（publish）は必ず人間。UI規約ではなくアーキテクチャで強制する

### 1.3 ペルソナ

| ペルソナ | 主用途 | 成功指標 |
|---|---|---|
| PdM（プライマリ） | 施策判断の根拠探索・機会の優先度付け | 意思決定に引用されたインサイト数 |
| UXリサーチャー | 調査の取り込み・ファクト化・分析 | 分析時間の短縮率 |
| CSリード | 問い合わせからのファクト供給 | VoC→プロダクト反映率 |
| 経営層（閲覧中心） | レポート閲覧・確信度の高い示唆の把握 | レポート閲覧率 |

### 1.4 差別化仮説（vs Centou / Dovetail / EnjoyHQ）

1. **説明可能な確信度モデル**（エビデンス強度×多様性×鮮度−反証、内訳完全開示。競合は件数表示止まりが多い）
2. **反証（contradicts）の一級市民化** — 矛盾するファクトを構造化し過信を防ぐ
3. **更新提案キューのUX** — レビュー習慣をプロダクト構造が作る
4. **日本語最適化** — 敬語・曖昧表現・言い淀みからの抽出品質

---

## §2 ドメインモデル

心臓部は Fact ⇄ Insight を結ぶ **EvidenceLink**（stance: supports / contradicts / context、weight 0–1）。確信度計算・更新提案・体系図すべての基礎。

### 2.1 エンティティ

**テナント・組織系**
- Workspace: 会社（組織）ごとのデータの入れ物。SaaSとして複数社に提供するときに他社とデータを完全に分けるための箱。自分専用の運用ならWorkspaceは1個だけ作り、以後は意識しなくてよい。id, name, plan, settings(retention, ai_policy)
- Member: workspace_id, user_id, role(admin/editor/contributor/viewer)
- ResearchQuestion（リサーチクエスチョン）: 「何を明らかにしたいか」という問い。例:「なぜ週次レポートの閲覧率が低いのか」。Source（リサーチ＝議事録など）はこの問いにぶら下がる。question, status(open/answered/parked)

> **設計判断**: Fact / Insight はリサーチクエスチョンに閉じ込めず、ワークスペース横断で存在させる。問いの中に隔離すると、別の問いを調べるときに過去の知見に気づけず、重複リサーチ問題が再生産される。

**ナレッジ系（コア）**
- Source: リサーチ1件とその生データ。当面の取り込み対象は議事録が中心。type(meet_minutes / notion_transcript / slack / chatwork / document / interview / survey), channel(link=URLを渡す / paste=本文を貼る / auto=将来の自動連携), title, raw_content_ref, transcript, occurred_at, ingestion_status。CS問い合わせは当面対象外（将来拡張）
- Highlight: 原文スパン（テキスト範囲 or タイムスタンプ範囲）。Factのgrounding
- Fact: statement(1事実1文), verbatim_quote, highlight_ids[], participant_attrs(匿名化済み), origin(ai_extracted/human), extracted_confidence
- Insight: statement, description, status, confidence_score, confidence_level, freshness, owner_id, superseded_by_id
- EvidenceLink: fact_id, insight_id, stance, weight, linked_by(ai_suggested→human_approved / human), rationale。UNIQUE(fact_id, insight_id)
- Opportunity: statement, insight_ids[], impact, effort, status, linked_external_ref(Jira/Linear)
- Recommendation: opportunity_id, statement, outcome（「施策の打率」計測の起点）
- Tag / TagGroup: ファセット型（persona / journey_stage / theme / product_area / sentiment）

**AI・運用系**
- Suggestion: type(new_fact/link_evidence/update_insight/new_insight/merge_insights/split_insight), payload(提案diff), rationale, model_version, prompt_version, score, status(pending/accepted/accepted_with_edit/rejected/expired), reviewed_by
- AuditLog: 不変・追記専用。actor(user/ai/system), action, entity_ref, before/after diff, suggestion_id
- Canvas / CanvasNode / CanvasEdge / CanvasGroup（§3.4）
- Report: 静的スナップショット＋ライブ参照のハイブリッド

### 2.2 インサイトのライフサイクル

```
draft ──publish──▶ active ◀──resolve── needs_review
                     │  ▲                   ▲
                     │  └──(更新承認で復帰)  │
                     ├── 自動トリガー ───────┘
                     │   ①contradictsリンク追加提案 ②確信度構成の大幅変動
                     │   ③鮮度スコア閾値割れ ④merge/split提案の発生
                     ├──merge──▶ merged（superseded_by で後継へ）
                     └──archive──▶ archived
```

merged / archived は削除しない（監査とリンク整合性のため）。

### 2.3 確信度・鮮度の計算モデル

```
confidence = clamp( base_evidence × diversity × recency − contradiction_penalty )

base_evidence  = Σ_supports ( method_weight × link_weight ) を飽和曲線で正規化
                 ── 件数の線形加算にしない（11件目の価値 < 2件目の価値）
method_weight  = ソース種別の強度係数（面談1.0 / サーベイ自由回答0.7 / CS0.6 / SNS0.4、調整可）
diversity      = 独立ソース数・参加者数・種別数（同一人物10件 ≪ 10人の発言）
recency        = 半減期付き指数減衰（デフォルト12ヶ月）
contradiction_penalty = contradicts側の同様の合算。
                 supports/contradicts比が閾値割れ → needs_review 強制遷移
```

- confidence_level（UI主表示）: hypothesis → emerging → validated → strong の4段階
- freshness は確信度と独立表示（「強いが古い」を可視化）
- 再計算: EvidenceLink変更イベント駆動＋日次バッチ（減衰）

> **設計判断**: スコアは説明可能でなければ信頼されない。詳細パネルで因子分解を必ず表示（「エビデンス12件（面談8・CS4）／参加者9名／反証1件／最終更新2ヶ月前」）。confidence_breakdown をJSONで永続化する。

---

## §3 UX設計

### 3.1 情報アーキテクチャ

```
[Inbox] [Sources] [Facts] [Insights] [Opportunities] [Canvas] [体系図] [Reports]
                                    ｜ 全域検索（⌘K） ｜ 設定
```

Inbox を先頭に置くのは意図的。AI提案レビューが日々の入口になる習慣を、ナビ構造で強制する。

### 3.2 画面一覧（11画面）

| # | 画面 | 目的 | 主要UI |
|---|---|---|---|
| S1 | **Inbox** | AI提案レビュー | 提案カード（diff・根拠引用・承認/編集して承認/却下）、種別フィルタ |
| S2 | Source取り込み | 投入 | D&D、Zoom/Slack/Zendesk連携、処理ステータス |
| S3 | Sourceビューア | 原文とファクトの対比 | 左:トランスクリプト（ハイライト着色）/右:ファクト一覧、手動ハイライト→ファクト化 |
| S4 | Facts DB | 一覧・フィルタ・選択 | テーブル/カード、ファセット、複数選択→リンク |
| S5 | Insights DB | 資産の俯瞰 | 確信度バッジ・鮮度・needs_reviewフラグ・保存ビュー |
| S6 | **Insight詳細** | 深掘り | 確信度内訳パネル、supports/contradictsタブ、変更履歴、関連Opportunity |
| S7 | 分析キャンバス | アフィニティマッピング | 無限キャンバス、付箋、グルーピング、インサイト昇格、AIクラスタ提案 |
| S8 | 体系図 | 思考プロセス可視化 | ツリー/グラフ、Opportunity→Insight→Factドリルダウン |
| S9 | 検索 | 全域探索 | ハイブリッド検索、フィルタ、類似インサイト表示 |
| S10 | Reports | 社内共有 | ライブ引用ブロック、スナップショット、閲覧専用リンク |
| S11 | 設定/管理 | テナント管理 | メンバー・ロール、AIポリシー、連携、監査ログ閲覧 |

### 3.3 コアユーザーフロー（3本）

1. **取り込み→ファクト化**: 投入 → 非同期処理 → Inboxに抽出ファクト提案 → 一括レビュー → Facts DB
2. **分析→インサイト化**: Facts DB絞り込み → キャンバス → グルーピング → 「インサイトに昇格」→ publish（EvidenceLink自動生成）
3. **更新提案ループ（差別化の核）**: 新Source → AIが既存インサイトと照合 → 支持/反証の提案 → Inboxレビュー → 承認で確信度更新 → needs_review はオーナーに通知

### 3.4 分析キャンバスのデータ表現

> **原則**: キャンバスは「ビュー」でありドメインオブジェクトを所有しない。ノード削除でFactは消えない。空間→論理の橋は promote_to_insight ただ一つ。

- CanvasNode: position, size, z, style, ref(entity_type + entity_id, **nullable**), free_text（ref無し付箋も許容）
- CanvasGroup: promote_to_insight でグループ内Fact参照ノードから Insight＋EvidenceLink群を生成
- CanvasEdge: 論理関係線（「だから」「しかし」）。体系図はこのエッジ＋EvidenceLinkから自動描画
- 同時編集: MVPは楽観ロック＋ポーリング → v1でCRDT（Yjs系）

---

## §4 システムアーキテクチャ（案1: 本命）

物理的にはモジュラーモノリス＋非同期ワーカー群。モジュール境界＝イベント境界を最初から明確にする。

```
[Web App(SPA)] [Slack App] [Public API]
        └── API Gateway（AuthN・AuthZ・テナント解決）
   ┌─ Identity/Tenant ─ Knowledge(コア) ─ Canvas ─ Reporting ─┐
                 │ domain events (fact.created 等)
             Event Bus / Job Queue
   ┌─ Ingestion Workers ─ AI Suggestion Workers ─ Search Indexer ─┐
   [Object Storage] [RDB=SSoT] [Vector/FTS Index] [LLM Provider]
```

### 4.1 設計原則

- **RDBが Single Source of Truth**。検索インデックス・埋め込みは再構築可能な派生データ
- **AI Workerは Suggestion を書くだけ**。ドメイン直接変更はDB権限レベルでも不可能にする
- **モジュール境界＝イベント境界**で将来の物理分割に備える

### 4.2 API境界（論理定義）

| モジュール | 代表エンドポイント |
|---|---|
| Ingestion | POST /sources, GET /sources/:id/status |
| Knowledge | CRUD /facts /insights /opportunities; POST /insights/:id/evidence-links; GET /insights/:id/confidence-breakdown |
| Suggestion | GET /suggestions?status=pending; POST /suggestions/:id/accept（修正payload可）/reject |
| Search | POST /search {query, mode: keyword\|semantic\|hybrid, filters} |
| Canvas | CRUD /canvases, /canvases/:id/nodes(バルク); POST /canvas-groups/:id/promote |
| Slack | Search/Knowledge APIの薄いアダプタ（新境界を作らない） |

### 4.3 マルチテナント × ベクトル検索

用語: **テナント**＝Workspaceとほぼ同じ意味の技術用語で、SaaSに同居する顧客企業1社のこと。マルチテナント＝1つのシステムに複数社が同居してもデータが混ざらない仕組み。自分専用の運用（§10）には関係せず、SaaSとして他社に提供するときだけ必要になる。

| 方式 | 分離強度 | 運用コスト | 判定 |
|---|---|---|---|
| A. 共有テーブル＋tenant_id＋RLS（pgvector等） | 中（論理） | 低 | **MVP〜v1採用** |
| B. テナント別namespace（専用ベクトルDB） | 中〜高 | 中 | v2で大規模テナント |
| C. テナント別DBインスタンス | 高（物理） | 高 | エンタープライズ層 |

方式A採用理由: ①トランザクション内でFactと埋め込みの整合 ②RLSで「WHERE tenant_id忘れ」をDB層で防止 ③小規模のうちはパーティションで十分。
必須規約: ベクトル検索は必ず pre-filter（tenant_idで絞ってからANN）／embedding_model_version を持たせ再埋め込みバッチを最初から設計／PIIマスキングは埋め込み・LLM送信の前段。

---

## §5 AIパイプライン

### 5.1 取り込み→提案の8段

```
1. Ingest       受領 → Object Storage、Source(status=processing)
2. Normalize    文字起こし・話者分離・PII検出/マスキング（LLM送信より前段）
3. Chunk/Ground 意味単位チャンク化、原文スパン保持
4. Fact Extract 解釈を含まない事実文。grounding必須（無ければ棄却）
5. Embed        埋め込み生成（model_version付与）
6. Dedupe       既存Fact近傍照合 → 重複はmerge提案へ
7. Match        既存Insightとベクトル近傍 → LLMリランク＋stance判定
8. Suggest      一致→link_evidence（確信度影響プレビュー付き）/
                クラスタ形成→new_insight / 反証検出→update_insight＋needs_review遷移
```

各段は冪等・リトライ可能なジョブ。失敗は ingestion_status に反映しUIから再実行可能。

### 5.2 Human-in-the-loop

- **AIの書き込み権限はSuggestionテーブルのみ**（アーキテクチャで強制）
- レビュー3値: accept / accept_with_edit（修正diffも記録）/ reject。理由コード付きでAuditLogへ
- accept時に初めてドメイン変更がトランザクション実行。actor=user, via_suggestion_id で完全遡及可能
- 提案TTL（例30日）で expired 化しInboxを腐らせない
- reject/editデータはプロンプト改善の教師データに
- 通知: needs_review遷移とInbox滞留をオーナーへ（アプリ内＋Slack）

### 5.3 プロンプト・評価戦略

- プロンプトはバージョン管理（prompt_version をSuggestionに記録）
- ゴールデンセット: 日本語インタビュー20本規模の正解ファクト・正解リンクでCI回帰評価（Precision/Recall・stance精度）
- オンライン指標: 提案承認率・編集距離・種別別承認率。閾値割れでロールバック判断
- ハルシネーション対策: grounding必須（原文スパンのないファクト文は生成段階で棄却）

---

## §6 データベース論理設計

```
workspaces(id, name, plan, ai_policy jsonb, created_at)
members(workspace_id, user_id, role, invited_by)
research_questions(id, workspace_id, question, status)

sources(id, workspace_id, research_question_id, type, title, raw_ref, transcript_ref,
        occurred_at, channel, ingestion_status, meta jsonb)
highlights(id, source_id, span_start, span_end, ts_start, ts_end, text)

facts(id, workspace_id, source_id, statement, verbatim_quote, origin,
      participant_attrs jsonb, extracted_confidence, status, created_by, created_at)
fact_highlights(fact_id, highlight_id)

insights(id, workspace_id, statement, description, status, owner_id,
         confidence_score, confidence_level, confidence_breakdown jsonb,
         freshness_score, last_evidence_at, superseded_by_id, published_at)

evidence_links(id, workspace_id, fact_id, insight_id, stance, weight,
               linked_by, suggestion_id, rationale, created_at)
               -- UNIQUE(fact_id, insight_id)

opportunities(id, workspace_id, statement, impact, effort, status, external_ref)
insight_opportunities(insight_id, opportunity_id)
recommendations(id, opportunity_id, statement, outcome, outcome_recorded_at)

tags(id, workspace_id, group_id, name) / tag_groups(id, workspace_id, name, facet_type)
taggings(tag_id, entity_type, entity_id)

embeddings(id, workspace_id, entity_type, entity_id, model_version, vector, created_at)
  -- 派生データ。RLS/パーティションの単位

suggestions(id, workspace_id, type, target_refs jsonb, payload jsonb, rationale,
            score, model_version, prompt_version, status, reviewed_by,
            reviewed_at, review_note, expires_at, created_at)

audit_logs(id, workspace_id, actor_type, actor_id, action, entity_type,
           entity_id, diff jsonb, suggestion_id, created_at)  -- append-only

canvases(id, workspace_id, research_question_id, name, updated_at)
canvas_nodes(id, canvas_id, entity_type?, entity_id?, free_text, x, y, w, h, z,
             style jsonb, group_id?)
canvas_groups(id, canvas_id, label, style jsonb, promoted_insight_id?)
canvas_edges(id, canvas_id, from_node_id, to_node_id, relation_type, label)

reports(id, workspace_id, title, blocks jsonb, snapshot_at?, share_token)
```

設計メモ: 全テーブルに workspace_id を非正規化しRLSの単一キーに／embeddings独立テーブルはモデル移行を独立バッチにするため／confidence_breakdown 保存は説明可能性のため／audit_logs にUPDATE/DELETE権限を発行しない。

---

## §7 スタック選定の選択肢比較（案1の実装スタック）

| 観点 | 案A: TSモジュラーモノリス（Next.js + Node + Postgres/pgvector + Redis） | 案B: TS Front + Python AI基盤（FastAPI + 専用ベクトルDB） | 案C: BaaS加速型（Supabase系） |
|---|---|---|---|
| 開発速度（MVP） | ◎ 単一言語・単一リポジトリ | △ 2言語・2デプロイ | ◎ 認証/RLS/ストレージ即利用 |
| AIパイプライン表現力 | ○ 十分 | ◎ ML生態系豊富 | △ 長時間ジョブに制約 |
| マルチテナント分離 | ◎ Postgres RLS一元化 | ○ 二重管理 | ◎ RLSネイティブ・上限あり |
| ベクトル検索スケール | ○ 中規模まで→限界時にB移行 | ◎ 大規模対応 | ○ pgvector依存 |
| 運用複雑性 | ◎ 低 | △ 中〜高 | ◎ 低（ロックイン） |
| 将来の分割容易性 | ○ 境界維持すれば可 | ◎ 最初から分離 | △ 移行コスト大 |

**推奨**: 案Aで開始し、AIワーカーだけは最初からキュー越しの独立プロセスに（将来Python化しても境界が変わらない）。実装開始時にADRとして正式決定する。

---

## §8 ロードマップ

### MVP（〜3ヶ月）— 価値ループを最小で成立させる

判断基準: 「新しいデータが来たら既存の知が更新される」体験が縦に1本つながっていること。

**削ってはいけない**: Source取り込み＋AIファクト抽出（grounding付き）／Fact・Insight CRUD／EvidenceLink（stance含む）／確信度v1（簡易係数でよいが**内訳表示は必須**）／**Suggestionキュー＋Inbox**（これを削るとただのメモDB）／**AuditLog**（後付け不可能）／DBビュー・ハイブリッド検索・Workspace/認証/RLS・基本タグ

**削る**: 分析キャンバス・体系図・Slackエージェント・レポート・SNS/CS自動連携・リアルタイム共同編集・細粒度権限・Opportunity/Recommendation（フリーリンク欄で代替）

### v1（+3〜6ヶ月）— 分析体験と流通
分析キャンバス＋昇格・AIクラスタ提案／Opportunity・Recommendation正式実装／レポート／Slack検索エージェント（読み取り専用から）／Zoom・Zendesk連携／needs_review通知運用

### v2（6ヶ月〜）— スケールとエンタープライズ
体系図自動生成／CRDT共同編集／打率ダッシュボード／Public API・Webhook／SSO・SCIM・監査エクスポート・物理分離／ベクトル基盤分離検討

---

## §9 リスクと未決事項

### リスク

| # | リスク | 緩和策 |
|---|---|---|
| 1 | 確信度スコアの正当性（信頼されないと機能全体が死ぬ） | 内訳完全開示＋係数調整可。初期は4段階レベルを主表示 |
| 2 | コールドスタート | 過去資産の一括バックフィルをオンボーディングの中核に |
| 3 | AI提案過剰によるInbox疲れ | スコア閾値・日次上限・ダイジェスト。承認率をガードレール指標に |
| 4 | PII/機密 | マスキング前段配置、テナント別AIポリシー、データ不使用契約 |
| 5 | 埋め込みモデル移行 | model_version設計＋デュアルインデックス運用手順の事前定義 |
| 6 | **習慣化の壁（最大の事業リスク）** | 連携による自動流入をv1で急ぐ |

### 未決事項

- 確信度の減衰半減期のデフォルト値（ドメイン別プリセット化の要否）
- Fact編集可否ポリシー（不変性 vs 誤字修正。提案: 履歴を残す軽量バージョニング）
- 匿名化レベルの規定（participant_attrs の範囲、GDPR/個情法）
- 料金モデル（シート課金 vs 取り込み量課金、AIコスト転嫁）
- Slackエージェントの書き込み許可範囲

---

## §10 アーキテクチャ2: BigQuery（マスタ）× Notion（GUI）× Claude 本設計

オーナー決定: **マスタデータソースは BigQuery、Notion はユーザーが使う GUI という位置づけ**とする。本節はこの前提でのアーキテクチャ本設計——各コンポーネントの**責任範囲**（10.2）と、**マスタに残すデータ／Notionで保持するデータの配置**（10.3）を核に定義し、同期設計（10.4）・破綻ポイント評価（10.5）・ロードマップ（10.8）まで通す。ドメインモデル（§2）・確信度モデル（§2.3）・AI原則（AIはSuggestionまで、確定は人間）はアーキテクチャ1と共通。

### 10.1 位置づけと全体像

```
Drive/GCS（生データ）
   │ 新着検知
   ▼
Claude 抽出ルーチン（Agent SDK / cron・冪等）── facts 書込（grounding付き）
   ▼
BigQuery ＝ マスタ（SSoT）
   ├ core: sources / facts / insights / evidence_links / suggestions / audit_logs(append-only)
   ├ derived: embeddings ← ML.GENERATE_EMBEDDING（※Claude APIに埋め込みAPIはない）
   ├ 照合: VECTOR_SEARCH ＋ SQLで確信度再計算（スケジュールドクエリで日次減衰）
   ▼                                    ▲
Claude 照合ルーチン（リランク＋stance判定） │ Claude 反映ルーチン（承認済み提案を適用＋監査記録）
   ▼                                    │
Notion ＝ GUI（投影・ワークベンチ）        │ status=accepted を巡回検知
   ├ Insights DB（active のみ）／ Facts DB（直近・リンク済のみ）
   ├ Suggestion Inbox DB（pending → accepted/rejected）
   └ EvidenceLinks DB（リレーション2本＋stanceセレクト＝属性付きn:mの代替）
   ▲
人間のレビュー（承認/編集/却下。コメント・通知はNotion標準機能）
```

- **取り込み対象（当面）**: Google Meet 議事録（Docs／リンク）、Notion AI 文字起こし、Slack・Chatwork のスレッド。Claudeへはリンクか本文貼り付けで渡し、リンクの場合は Claude が本文を取得して GCS／BQ に保存する。CS問い合わせは対象外（将来拡張）
- **BigQuery（マスタ）**: §6スキーマをほぼそのまま写す（workspace_id は単一固定値）
- **Notion（GUI）**: リレーションは属性を持てないため、stance・weight付きn:mは EvidenceLinks を独立DBにして代替。レビューUX・コメント・通知・モバイルが開発ゼロで手に入るのが最大の資産
- **Claude**: 冪等ルーチン3本（抽出/照合/反映）＋夜間の整合性照合ジョブ。BQ書込は必ず audit_logs 追記とセット

### 10.2 責任範囲 — 誰が何のオーナーか

**大原則（3つ）**

1. **BigQuery が唯一の SSoT** — Notion が全損しても BQ から全投影を再構築できる状態を常に維持する（復元もルーチン化）。逆は成り立たない——BQ は Notion から再構築できない
2. **Notion は「使い捨て可能なワークベンチ」** — 人が見て・レビューして・議論する場所であり、ドメインデータのマスタを一切持たない。唯一の例外はコメント・議論・レポートページ（コラボレーションデータ）で、これだけは Notion がマスタ
3. **Claude は処理の実行役で、データを保存しない** — 必要なデータは毎回 BQ から読み、結果は BQ へ書く。Claude 自身の中には何も残さない。すべての BQ 書込は audit_logs への追記とセット

| コンポーネント | 責任（オーナーであるもの） | 責任外（持ってはいけないもの） |
|---|---|---|
| **BigQuery** | 全ドメインデータの SSoT（facts / insights / evidence_links / suggestions の全量・全履歴）、確信度・鮮度の計算、ベクトル照合（ML.GENERATE_EMBEDDING / VECTOR_SEARCH）、audit_logs、IDマッピング（sync_state） | UI・通知・コラボレーション |
| **Notion** | レビューワークベンチ（Suggestion Inbox）、人が触る範囲の閲覧・検索、コメント・メンション・共有（*ここだけマスタ*）、レポートの配布面 | ドメインデータのマスタ。全量保持・履歴保持・計算 |
| **Claude ルーチン** | 抽出・照合・提案生成・承認反映・双方向同期・夜間整合性照合・Slack検索応答・レポート生成 | データの保存（Claude内には何も残さない）、人間の承認なしのデータ確定 |
| **GCS / Drive** | 生ファイル（音声・原文・添付）のマスタ | 構造化データ |
| **人間** | 確定（publish・承認・却下）の唯一の権限者。insight の文言・ステータスの編集 | facts の直接編集（修正提案として起票する） |

### 10.3 データ配置設計 — BQに残すデータ・Notionで保持するデータ

配置は3値で判定する: **全量=BQ**（マスタ）／**投影=Notion**（条件付きの写し、人が触る分だけ）／**Notionマスタ**（コラボレーションのみ）。投影の絞り込み条件は、Notion の1万行・3req/s 限界（10.5-5）への対策そのもの。

| データ | BigQuery（マスタ） | Notion（保持するもの） | Notionでの編集 |
|---|---|---|---|
| 生データ（音声・原文・添付） | GCS参照のみ（マスタはGCS） | **置かない**（PIIをNotionに出さない） | — |
| sources | 全量＋transcript参照＋ingestion状態 | メタデータのみ投影（title / type / 日付 / ステータス / GCSリンク） | 不可 |
| highlights | 全量（スパン・原文） | DBとしては置かない。Factページ本文に引用として表示のみ | 不可 |
| facts | 全量＋全履歴 | 直近90日 or EvidenceLinkで参照中のものだけ投影 | 不可（修正は「修正提案」として起票） |
| insights | 全量＋版履歴（insight_versions） | active＋needs_review のみ投影。archived / merged は外す | **statement / description / status のみ可** |
| evidence_links | 全量（stance / weight / rationale） | 投影中の insight に紐づく分のみ（EvidenceLinks DB） | 不可（承認済み提案の適用でのみ変化） |
| suggestions | 全量・全状態＋レビュー履歴 | pending のみ（Inbox）。処理済みは完了アーカイブへ | **status のみ可**（accept / reject） |
| confidence / freshness / 内訳 | 計算のマスタ＋confidence_breakdown | プロパティとして表示（ロック運用・編集しても上書き） | 不可 |
| embeddings | 全量（model_version付き） | 置かない | — |
| audit_logs | 全量 append-only | 置かない（閲覧は週次レポート経由） | — |
| sync_state（BQ id ⇄ notion_page_id） | **マスタ**（content_hash / last_synced_at 含む） | 各ページに BQ ID プロパティのみ | 不可 |
| コメント・議論・メンション | 夜間バックアップとして取り込み（検索用） | **Notionがマスタ（唯一の例外）** | 可（自由） |
| レポート | スナップショットを保存 | 配布面としてのページ（Claudeが生成） | 可 |

- **IDマッピングの所有はBQ側** — sync_state テーブルが BQ id ⇄ notion_page_id ⇄ content_hash を持つ。Notion側の孤児ページ・重複ページは夜間照合がこのテーブルとの突合で検出
- **Notion全損リストア** — sync_state＋coreテーブルから全DB・全ページを再生成するルーチンを平時から用意し、四半期に一度リハーサル。「Notionはいつでも作り直せる」が大原則①の担保
- **投影の絞り込みが効かなくなったら**（active insightだけで1万行に迫る等）、それは10.8の移行トリガーであり、投影条件をさらに複雑化して延命しない

### 10.4 フィールド所有権と同期設計

2ストア＋人間＋AIの4者が同じデータを触る以上、双方向同期のドリフトが死因になり得る。10.3の配置を前提に、編集可能なフィールドの所有権を固定する。**「どちらでも編集できる」フィールドを1つでも作った瞬間に破綻する。**

| データ | 所有者 | 同期方向 | 競合規則 |
|---|---|---|---|
| facts（statement, quote, grounding） | BQ（Claude抽出） | BQ→Notion | Notion側は読み取り専用運用。修正は「修正提案」として起票 |
| insights.statement / description | **Notion（人間）** | Notion→BQ | last_edited_time 巡回検知で取り込み、BQに版として追記 |
| insights.status（publish/archive） | Notion（人間） | Notion→BQ | 同上。needs_review への遷移だけはBQ側計算が勝つ |
| confidence / freshness / needs_review | BQ（計算） | BQ→Notion | Notion側プロパティはロック運用（編集しても上書き） |
| suggestions.status | Notion（人間） | Notion→BQ | accepted 検知で反映ルーチンが適用 |
| evidence_links | BQ（承認済み提案の適用） | BQ→Notion | Notion手動リンクは夜間照合で検出、notion_manual_edit として監査記録の上で正規化 |

#### Notion → BQ 反映: 変更捕捉の方式比較

「Notionを変更したら、それをBQにどう反映するか」——この逆方向同期が案2の生命線。3方式を比較する。

| 方式 | 仕組み | 長所 | 短所 | 判定 |
|---|---|---|---|---|
| **A. ポーリング** | last_edited_time カーソル＋content_hash 差分で変更ページを巡回検出（5〜15分間隔） | サーバ不要。「Claudeはデータを保存しない」原則（10.2）を維持。単純で、二重実行しても安全にしやすい | 反映遅延＝ポーリング間隔 | **MVP-0〜v1 採用** |
| B. Notion Webhook | 変更イベントをHTTPエンドポイントで受信 | 秒オーダーの反映 | 常設の受信サーバ（Cloud Run等）が必要になり「サーバを持たない」構成の例外になる。取りこぼしがあるため結局Aの照合が要る | v1以降、遅延が実測で問題化したら*Aに追加*（置換ではない） |
| C. 夜間全件照合のみ | 日次でBQ↔Notionを全件diff | 最も単純 | 最大24hの反映遅延、日中の二重編集リスク | 安全網として常設（単独では不採用） |

#### 差分取り込みルーチンの仕様（方式A）

1. 対象DB（Insights / Suggestions）を `last_edited_time ≥ cursor − 10分` の**オーバーラップ窓**付きでクエリ
2. `last_edited_by` が連携ボット自身のページはスキップ（**エコー防止の第1層** — BQ→Notion投影を「人間の編集」として拾い直さない）
3. 各ページの現在値を正規化して content_hash を計算し、sync_state の「最後に投影した状態のhash」と比較。一致なら人間編集なしとしてスキップ（**エコー防止の第2層**。ボット更新直後・同一分内の人間編集もここで拾える）
4. 差分フィールドを所有権マトリクスで判定:
   - **編集可フィールド**（insight.statement / description / status、suggestion.status）→ BQへMERGE。insightは旧版を insight_versions にappendしてから更新し、audit_logs に `actor=user, channel=notion_sync`、before/after diff を記録
   - **編集不可フィールド**（confidence、facts本文、evidence_links等）→ BQ値でNotion側を上書き復元し、audit_logs に `notion_manual_edit（rejected）` を記録
5. sync_state を更新（content_hash / last_synced_at）し、カーソル前進
6. `suggestion.status = accepted` を検出したら反映ルーチン（10.1）へ引き渡す

#### 落とし穴と対策

- **last_edited_time は分単位精度** — 厳密比較のカーソルは同一分内の編集を取りこぼす。オーバーラップ窓（10分）＋hash比較で、取りこぼしと二重適用の両方を防ぐ（ルーチン全体を冪等にする）
- **競合**（人間のNotion編集とBQ計算が同時） — 所有権で機械的に解決: statement は人間が勝つ（旧版が insight_versions に残るため破壊なし）。needs_review 遷移は BQ が勝つ
- **Notionページの削除・アーカイブ** — サポート外の操作。夜間照合が BQ から復元し notion_manual_edit として記録。消したい場合の正規経路は status=archived（編集可フィールド経由）
- **反映遅延のUX** — Notion側に「同期ステータス」プロパティ（synced / pending / rejected）を表示。編集が未取り込みの状態と、編集不可フィールドが復元された事実（rejected）を無言にせず可視化する

### 10.5 破綻ポイントの評価 — どこで壊れるか

| # | 破綻ポイント | 深刻度 | 評価と緩和 |
|---|---|---|---|
| 1 | **マルチテナント不可** | 致命的（SaaSとして） | 緩和不能。単一組織の内部運用専用と割り切る。SaaS化の瞬間に案1が必要 |
| 2 | **同期ドリフト**（Notion直編集・ルーチン失敗・部分適用） | 高 | 10.4の所有権マトリクス＋夜間の全件整合性照合（diff→自動修復＋監査記録） |
| 3 | **監査の抜け道**（Notion直接編集がSuggestionフローを迂回） | 中〜高 | 完全阻止は不可能（Notionに権限粒度がない）。夜間照合で事後検出し監査ログに残す。「迂回はできるが記録は残る」で検証用途には十分 |
| 4 | **BQはOLTPではない**（DMLはジョブ・行ロックなし・原子性なし） | 中 | レビュー承認は毎分〜毎時のバッチで十分なワークロード。suggestion_id で重複適用防止。同時レビュアー数人なら実害なし |
| 5 | **Notionの規模限界**（DB1万行超で劣化、API約3req/s） | 中 | 「人が触る対象だけ投影」原則で回避。全量検索はSlack/CLI→Claude→BQに逃がす |
| 6 | **分析キャンバス・体系図が作れない** | 中 | ボード/ギャラリー＋グループ化で部分代替。検証スコープ外と明示（§8でもMVP除外） |
| 7 | **提案diffの表現力**（Notionに構造化diff UIがない） | 低〜中 | 提案ページ本文に「現在文↔提案文」引用ブロック併記＋根拠引用 |
| 8 | **ルーチン実行基盤の可用性**（cron失敗・二重起動・レート制限） | 低〜中 | 冪等設計＋実行ログテーブル（BQ）＋再実行。agent-crew の既存運用資産と同型 |
| 9 | **PII**（顧客発話がNotion・BQ・LLMの3箇所を通過） | 中 | 生データはGCS/BQに限定、Notionへは匿名化済みstatementのみ投影。マスキングは抽出ルーチン内（LLM送信前）＝案1の段2と同じ位置 |

### 10.6 この構成が強い理由

1. **構築2〜4週間・フロントエンド開発ゼロ**（案1 MVPの1/3以下）。検証したいのはUIではなく「更新提案ループが使われるか」という行動仮説
2. **BQのベクトル検索＋SQL分析が初日から効く** — 承認率・Inbox滞留・確信度分布（§5.3のオンライン指標）がSQL一発。検証トラックとしては案1より計測能力が高い
3. **ドメインモデルは共通** — §2をそのままBQスキーマに写すため、データと知見は案1へそのまま移行（BQ→Postgresエクスポート）。捨てるプロトタイプではなく本番の先行検証
4. **「AIはSuggestionまで」の原則が保てる** — BQのテーブル別権限で担保可能

### 10.7 アーキテクチャ1との比較と判定

| 観点 | 案1: 自社開発 | 案2: BQ × Notion × Claude |
|---|---|---|
| 到達点 | マルチテナントSaaS | v1で単一組織のフル運用、v2でハイブリッド化し案1へ連続収斂（§10.8）。マルチテナントは最後まで不可 |
| 構築期間（価値ループ1本） | 約3ヶ月 | 2〜4週間 |
| レビューUX | 専用Inbox・diff表示 | Notion DB＋ページ本文diff（劣るが足りる） |
| 整合性・監査 | トランザクション＋RLSで構造的に担保 | 冪等バッチ＋夜間照合で運用的に担保（迂回は検出のみ） |
| 計測（承認率等） | 要実装 | SQLで即日 |
| キャンバス・体系図 | v1以降 | 構造的に不可 |
| 廃棄コスト | — | 低（データ・モデルは案1へ持ち越し） |

> **判定 — 案2は使い捨てではなく、独自のロードマップを持つ第2の本線**
> 案2を MVP-0 として先行させるのは変わらないが、MVP-0 で終わりではない。案2は §10.8 の独自ロードマップ（MVP-0 → v1 → v2）を持ち、進み方は2通り:
> **(a) SaaS化を急ぐなら**: MVP-0 のゲート通過後すぐ案1へ投資
> **(b) 内部価値の最大化を優先するなら**: 案2を v1 まで育て、移行トリガー（§10.8）に当たった時点で案1へ
> どちらの経路でもドメインモデルとBQ上のデータはそのまま持ち越せる。
> MVP-0のゲート基準: 4週間の実運用で ①提案承認率（accept＋accept_with_edit）50%以上 ②週次レビュー習慣が途切れない ③「更新提案で意思決定が変わった」事例1件以上。満たさなければ、作るべきはSaaSではなくプロンプトとドメインモデルの見直しであり、その学びを3ヶ月分の開発費を燃やす前に得られる。

### 10.8 ロードマップ — この構成のまま、どこまで育てられるか

案1（§8）と対称に、案2自身の成長パスを3段で設計する。各段にゲート基準（次へ進んでよい条件）と移行トリガー（この構成を出るべき条件）を持たせ、「いつまでもNotionに居座って限界に気づかない」事故と「まだ育つのに早すぎる開発投資」の両方を防ぐ。

#### MVP-0（2〜4週）— 縦1ループの成立

- スコープは §10.1 のとおり: 抽出 → BQ → 照合 → Notion Inbox → 承認 → 反映 → 確信度再計算の縦1本
- **ゲート基準（→ v1へ）**: 承認率50%以上／週次レビュー習慣の継続／意思決定が変わった事例1件以上

#### 案2 v1（+1〜3ヶ月）— 構成を変えずに広げる

- **取り込み自動化**: Zendesk / Gmail / Slack export → GCS の自動連携、新着検知の常時化。§9 最大の事業リスク「習慣化の壁」への正面対策で、案2 v1 の最優先項目
- **Slack検索エージェント**: Slack → Claude → BQ VECTOR_SEARCH → 回答＋Notionリンク。案1では v1 の機能を、この構成のまま先行実現できる（Claudeルーチンの追加のみ）
- **レポート自動生成**: Claude が週次で Notion ページを生成（needs_review 一覧・新着インサイト・確信度の変動サマリ）
- **体系図の部分代替**: EvidenceLink から Mermaid 図を自動生成して Notion ページに埋め込み（Notion は mermaid コードブロックを描画可能）。閲覧専用だが「思考の連鎖の可視化」はここまで届く
- **確信度モデル v2**: method_weight の調整運用、鮮度減衰スケジュールドクエリの本運用、Notion 上での内訳表示改善
- **運用強化**: 夜間整合性照合の自動修復レポート、ルーチン実行ダッシュボード（BQ実行ログ＋Looker Studio）

> **v1 に進んでも解消されない構造的限界（再掲・厳守）**
> ①マルチテナント不可（10.5-1） ②アフィニティマッピング不可（10.5-6） ③監査迂回は「検出まで」（10.5-3）。
> この3つは案2にいくら投資しても直らない。v1 の追加開発をこの3領域に向けてはならない——それは案1の仕事。

#### 案2 v2（6ヶ月〜）— ハイブリッド化: 限界に達した部分だけ置換

- Inbox と検索だけを薄い専用UI（BQを叩く最小の読み書きAPI＋最小フロント）に置換。Notion は閲覧・コメント・レポート配布用に残す
- BQ マスタは維持したまま——案1のアーキテクチャへビッグバン移行ではなく連続的に収斂するパス。RDB（Postgres）への載せ替えは SaaS 化（マルチテナント要求）が確定したときのみ

#### 移行トリガー — この条件に当たったら構成を出る

| トリガー（観測可能な条件） | 行き先 |
|---|---|
| Notion 投影対象が1万行に接近（投影絞り込みで回避不能） | 案2 v2（ハイブリッド化） |
| 同時レビュアー5人超、または承認→反映のバッチ待ちが業務ボトルネックに | 案2 v2（専用Inbox） |
| アフィニティマッピングの不在が分析品質のボトルネックに | 案1 v1（分析キャンバス）着手 |
| 社外テナント・顧客提供（SaaS化）の要求発生 | 案1 必須 — 案2では緩和不能 |
| 監査要件が「迂回の事後検出」では通らない（コンプライアンス要求） | 案1 必須 |

---

## 次のアクション

1. §10 の MVP-0（案2）着手可否をオーナーが判断
2. 着手する場合: BQスキーマ定義・Notion DB設計・Claudeルーチン仕様を feature-spec 化（docs/spec/features/）
3. 案1実装開始時: §7 のスタック決定を ADR-017 として起票

## 変更履歴

- 2026-08-10: 初版（案1: §1〜§9）＋オーナー指示により案2（§10: BQ × Notion × Claude）を追記
- 2026-08-10: オーナー指摘（案2にv1がない）を受け案2独自のロードマップ（MVP-0→v1→v2）、移行トリガー表、構造的限界の再掲を追加。判定を「使い捨てMVP-0」から「独自ロードマップを持つ第2の本線」へ改訂
- 2026-08-10: オーナー決定（BQ=マスタ・Notion=GUI）を受け §10 を「代替案の検討」から「アーキテクチャ2の本設計」へ再構成 — 10.2 責任範囲マトリクス（大原則3つ: BQが唯一のSSoT／Notionは使い捨て可能なワークベンチ／Claudeはステートレス）と 10.3 データ配置設計（BQに残すデータ・Notionで保持するデータの全対応表、sync_state、Notion全損リストア）を新設。旧10.2〜10.6は10.4〜10.8へ再番号
- 2026-08-10: オーナーフィードバック反映 — ①比喩表現の排除（「ステートレスな糊」→平易な説明へ。CLAUDE.md に文体ルールとして記録） ②Project を ResearchQuestion（リサーチクエスチョン）へ改名しオーナーのAtomic Research理解（問い→リサーチ→ファクト→インサイト）と一致させた ③Source種別を実データに合わせ更新（Meet議事録・Notion AI文字起こし・Slack・Chatwork、リンク/本文貼り付け。CS問い合わせは対象外） ④Workspace・テナントに平易な説明を追加 ⑤図3に記法説明（同期/非同期・ジョブ/ストアの見分け）を追加
- 2026-08-10: 10.4 に Notion→BQ 反映（逆方向同期）の設計を追加 — 変更捕捉3方式の比較（ポーリング採用・Webhookは追加オプション・夜間照合は安全網）、差分取り込みルーチン仕様（オーバーラップ窓・エコー防止2層・所有権判定・版管理）、落とし穴と対策（分単位精度・競合解決・削除の扱い・同期ステータスの可視化）
