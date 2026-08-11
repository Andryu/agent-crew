# インサイトマネジメントシステム 設計書 v2 — 議事録から、更新され続けるインサイトを育てる

作成日: 2026-08-11（v2 全面改訂。v1はgit履歴に保存）
ステータス: Draft（オーナー承認待ち）
起案: team-lead（Fable）
前提: 社内限定・プロダクト別・SaaS化なし・AI処理はClaude Codeスキルで実行
関連: docs/spec/centou-gui-redesign.md（GUI比較の詳細版）。HTML版（Claude Artifact）が図付き完全版

---

## v2での主な変更（v1との差分）

- Workspace・テナント・SaaS前提を**完全削除**。仕切りは product_id のみ
- 呼び名を修正: リサーチクエスチョン／リサーチ（Source）／ハイライト／ファクト／インサイト／根拠リンク（EvidenceLink）／提案（Suggestion）／監査ログ
- SaaS向けの大規模システムアーキテクチャ（モジュラーモノリス・イベントバス・ワーカー群）を**削除**
- AIパイプライン基盤を廃止し、**Claude Codeスキル4本**での実行に変更
- アーキテクチャは**3案を根拠付きで比較**（すべてNotion案を含む）
- 確信度モデルの**根拠を明記**（構成要素は研究手法に根拠あり、式・係数は設計仮説と明示）
- DB設計を更新（product_id・insight_versions・sync_state・skill_runs、workspaces廃止）

---

## §1 概要

### 1.1 解決したいこと

| 課題 | 解き方 |
|---|---|
| リサーチ結果が議事録のまま散在し、読み返されない | ファクト単位で構造化し、検索できる資産にする |
| 「前に誰かが同じことを聞いた」ことに気づけない | 新しいファクトを既存インサイトと自動照合する |
| インサイトが作った時点で止まり、古くなる | 新しい根拠の到着でAIが更新・反証を提案する |
| 思い込みの強い施策判断 | 確信度と反証を明示し、根拠の弱さを見えるようにする |

### 1.2 中核コンセプト（3つ）

1. **Atomic UX Researchの階層** — リサーチクエスチョン（問い）→ リサーチ（調査1件）→ ファクト（事実の最小単位）→ インサイト（解釈）。Tomer Sharonの枠組みに準拠
2. **更新され続ける資産** — インサイトは新しい根拠の到着で確信度が動き、反証が出たら見直しがかかる
3. **AIは提案まで、確定は人間** — AIの書き込み先は提案（Suggestion）と監査ログのみ

### 1.3 データソースと利用者

- 取り込み対象: Google Meet議事録（Docs/リンク）、Notion AI文字起こし、Slack・Chatworkスレッド。リンクか本文貼り付けで渡す。CS問い合わせは対象外（将来拡張）
- 実測値: 議事録1本≒ファクト約38件。週2〜3本→年間4,000〜6,000ファクト
- 利用者: 社内チーム。運用の中心はオーナー、他メンバーは閲覧・コメント

---

## §2 ドメインモデル（1つに固定）

どのアーキテクチャ案でもこのモデルは変わらない。心臓部はファクト⇄インサイトを結ぶ**根拠リンク**（stance: supports/contradicts/context、weight 0–1、UNIQUE(fact_id, insight_id)）。

### 2.1 エンティティ一覧

| エンティティ | 意味 | 主な属性 |
|---|---|---|
| **プロダクト**（products） | 社内プロダクトの単位。データの基本的な仕切り | name, status |
| **リサーチクエスチョン**（research_questions） | 「何を明らかにしたいか」という問い | product_id, question, status(open/answered/parked) |
| **リサーチ**（sources） | 調査1件とその生データ（議事録・スレッド・文字起こし） | product_id, research_question_id, type, title, occurred_at, raw_ref, channel(link/paste/auto), ingestion_status |
| **ハイライト**（highlights） | 原文の切り抜き（要約ではない）。ファクトの根拠箇所そのもの | source_id, span, text |
| **ファクト**（facts） | 解釈を含まない事実1文＋引用 | product_id, source_id, statement, verbatim_quote, origin(ai/human), speaker_attrs, extracted_confidence, status |
| **インサイト**（insights） | 解釈。確信度・状態を持つ | product_id(**NULL=全社横断**), statement, description, status, confidence_*, freshness, owner, superseded_by_id |
| **根拠リンク**（evidence_links） | ファクト⇄インサイトの多対多リンク。**心臓部** | stance(supports/contradicts/context), weight, linked_by, rationale（紐付け理由文） |
| **提案**（suggestions） | AIからの提案書。承認までデータ本体は変わらない | type, payload(変更前後の差分), rationale, score, status, reviewed_by, expires_at |
| **監査ログ**（audit_logs） | 誰が・いつ・何を・どう変えたか。追記専用 | actor, action, entity_ref, diff, suggestion_id |
| タグ（tags/taggings） | ファセット分類 | name, facet |
| 将来: 機会・レポート・キャンバス | 活用レイヤー。MVPに含めない（v1b以降） | — |

> **設計判断**: ①ファクト・インサイトはリサーチクエスチョンに閉じ込めない（隔離すると重複リサーチが再発）。②インサイトのみ product_id NULL可（全社横断の知見）。照合は「同一プロダクト＋全社」を対象。

### 2.2 インサイトの状態遷移

```
draft ──公開──▶ active ◀──解決── needs_review（要見直し）
                  │  ▲                  ▲
                  │  └─（更新承認で復帰）│
                  │  自動トリガー ───────┘
                  │   ①反証リンクの追加提案 ②確信度の大幅変動 ③鮮度の閾値割れ
                  ├──統合──▶ merged（superseded_by で後継へ）
                  └──保管──▶ archived
※ merged / archived は削除しない（監査とリンク整合性のため）
```

### 2.3 確信度・鮮度の計算モデルと、その根拠

```
確信度 = clamp( 根拠の強さ × 多様性 × 鮮度 − 反証の減点 )

根拠の強さ = Σ supports（手法の重み × リンクの重み）を飽和曲線で頭打ちに
             ── 11件目の価値 < 2件目の価値
多様性     = 独立した発言者数・リサーチ数・種別数（同一人物の10発言 ≪ 10人の発言）
鮮度       = 根拠の発生日に半減期付きの減衰（デフォルト12ヶ月・調整可）
反証の減点 = contradicts側の同様の合算。支持/反証比が閾値割れで needs_review へ

表示: 4段階レベル（仮説→兆候→検証済→強固）を主、数値を従。内訳を必ず開示
```

**このモデルは何を根拠にしているか（正直な整理）**

| 構成要素 | 根拠 |
|---|---|
| 件数の頭打ち（飽和曲線） | 定性調査の**データ飽和（saturation）**の知見。少数サンプルで大半の発見が出て追加の新情報は逓減する（Guest et al. 2006、Nielsenの5ユーザーテスト） |
| 多様性（独立ソース重視） | 研究手法の**トライアンギュレーション**（独立した複数の情報源による裏付け）。同一人物の繰り返しは独立した裏付けにならない |
| 鮮度の半減期減衰 | 知識の陳腐化モデル（文献計量学の「引用半減期」と同型）。市場・ユーザー行動は変わるため古い根拠は割り引く |
| 反証の減点・一級市民化 | 反証主義と**確証バイアス対策**。医療のエビデンス評価**GRADE**が「結果の非一貫性」で証拠の質を下げるのと同じ構造 |
| 4段階レベル表示 | GRADEの4段階（High/Moderate/Low/Very low）に倣った離散化 |

> **ただし——式と係数は「設計仮説」**。構成要素の選定には上記の根拠があるが、式の形・手法の重み（面談1.0/Slack 0.6等）・半減期12ヶ月の具体値は実証された標準ではない。だからこそ ①内訳を必ず開示 ②係数は設定で変更可 ③運用実データ（承認率、レビュー時の体感とのズレ）で校正する。スコアが信頼を失ったら数値を隠し4段階レベルだけにする退路も残す。

---

## §3 AI処理 — Claude Codeのスキルとして実行する

専用パイプライン基盤（キュー・ワーカー・イベントバス）は**作らない**。AI処理はすべてClaude Codeのスキルとして実装し、手動またはcronで起動する。基盤はBQとGCSだけ。

### 3.1 スキル構成（4本）

| スキル | やること | 起動 |
|---|---|---|
| `/research-ingest` | 議事録のリンク/本文を受け取る → 原文をGCS/BQ保存 → ハイライト切り抜き＋ファクト抽出（grounding必須）→ ファクト登録＋提案作成 → Notion投影 | 手動（議事録を渡すとき）。将来はフォルダ監視cron |
| `/insight-match` | 新ファクトを既存インサイトと照合（BQ VECTOR_SEARCH → リランク＋支持/反証判定）→ リンク提案・新インサイト提案・見直し提案 | ingest後に連続実行 or cron |
| `/review-apply` | Notionで accepted の提案をBQ反映 → 確信度再計算 → Notion再投影 → 監査記録。Notion側の人間編集の取り込みもここで実施 | cron（毎時）or 手動 |
| `/insight-report` | 週次まとめ（新規・要見直し・確信度変動）をNotionページ生成 | cron（週1） |

### 3.2 原則（基盤がなくても守るもの）

- AIの書き込み先は提案と監査ログのみ。データ本体の変更は人間の承認（review-apply）を通る
- ファクトは原文grounding必須（引用元スパンのないファクト文は登録しない）
- すべてのBQ書込は監査ログ追記とセット
- スキルは何度実行しても安全（sourceのcontent_hashで二重取り込み防止）
- レビュー運用: ファクトは実測38件/本のため**議事録1本＝1レビューの一括承認**。個別レビューは新インサイト・見直し・反証リンクに集中
- 実行記録は skill_runs テーブルに残す

---

## §4 アーキテクチャ3案の比較と推奨

ドメインモデル（§2）とスキル構成（§3）は共通。違いは「マスタをどこに置き、画面を何にするか」だけ。

### 案1: すべてNotion（NotionがマスタもGUIも）

構成: NotionのDB群がマスタ兼画面。Claude CodeはNotion APIだけを読み書き。BQなし。

- **メリット**: ストア1つで同期不要／最速で開始（今日から）／コメント・通知・モバイル内蔵／運用対象ゼロ
- **デメリット（根拠付き）**:
  - **照合ができない** — Notionにベクトル検索はない。「新ファクトと既存インサイトの自動照合」という本システムの核が成立しない。代替でClaudeが毎回全ファクトを読むと、API平均3req/s制限下で年4,000件超のスキャンは1回20分以上→議事録のたびに実行する処理として破綻
  - **確信度計算が表現できない** — 飽和曲線・半減期減衰はNotionの数式機能では実装困難。rollup多用DBは2,000〜3,000行から劣化（裏取り済み）
  - **容量が実測で持たない** — 38件/本→年4,000〜6,000ファクト。1〜2年で1万行域＝UI劣化ゾーン（保存上限25万行の遥か手前でUIが先に死ぬ）
  - **監査・版管理が弱い** — ページ履歴は構造化された監査ログ・版テーブルにならない
- **判定**: 最初の2週間の実験には使えるが、照合と確信度という中核が作れないため**本線にできない**

### 案2: BQマスタ × Notion GUI

構成: BQが全量・履歴・計算のマスタ。Notionは「人が触る分だけ」の投影＋レビューInbox＋コメント。Claude Codeスキルが取り込み・照合・反映・同期。

- **メリット**: 照合（VECTOR_SEARCH）・確信度計算・版履歴・監査・横断分析がSQLで確実に作れる。承認率などの計測もSQL一発。Notionのレビュー・コメントはそのまま
- **デメリット（根拠付き）**:
  - **双方向同期の造り込み** — フィールド所有権固定・content_hash差分・429対策・夜間突合の一式（§6）。設計済みだが運用の複雑さは増える
  - **ファクト全量の閲覧面がない** — 38件/本により、Notionには直近30日＋リンク済みしか置けない
- **判定**: 中核要件はすべて成立。弱点は「閲覧面の不足」に集約される

### 案3: 案2＋閲覧Artifact（公式BigQueryコネクタ）【推奨】

構成: 案2に、Claude Artifact＋Google公式のマネージドBigQuery MCPコネクタによる**読み取り専用の閲覧画面**を足す。検索・全量ファクト一覧・インサイト詳細（確信度内訳・支持/反証）の閲覧をArtifactが担う。

```
議事録/Slack ──▶ Claude Codeスキル4本 ──▶ BigQuery（マスタ）◀──公式BQコネクタ── 閲覧Artifact（読取専用）
                                     　        │▲
                            投影（差分・秒3件以下）│ 編集・承認の取り込み
                                     　        ▼│
                                         Notion（協働の場: Inbox・コメント・レポート）◀── 人間
```

- **追加メリット**: 案2の弱点「ファクト全量の閲覧面」が埋まる。追加コストは**設定のみ**（コネクタ追加＋IAM付与。Google公式マネージドMCPのためコード・サーバ運用ゼロ）。読み取り専用はIAM（dataViewerのみ）で構造的に強制。将来、書込用自作MCP＋分析キャンバスへ同じ構成のまま拡張できる
- **残るデメリット**: Artifact閲覧にclaude.aiログイン＋コネクタ同意が必要／書込（承認）は当面Notionのまま／window.claude.mcpの実挙動が未検証（v1a冒頭で確認）

### 4.4 比較表と推奨

| 観点 | 案1: すべてNotion | 案2: BQ×Notion | 案3: 案2＋閲覧Artifact |
|---|---|---|---|
| 照合（意味検索）＝本システムの核 | × 不成立 | ◎ VECTOR_SEARCH | ◎ 同左 |
| 確信度計算・版履歴・監査 | × 表現できない | ◎ SQL＋監査ログ | ◎ 同左 |
| レビュー・コメント・通知 | ◎ | ◎（Notion） | ◎（Notion） |
| ファクト全量の閲覧・検索 | △ 1〜2年で劣化ゾーン | × 置き場がない | ◎ ArtifactがBQ直読 |
| 同期の複雑さ | ◎ なし | △ 双方向同期一式 | △ 同左（投影は縮小） |
| 構築の速さ | ◎ 今日から | ○ 2〜4週 | ○ 2〜4週＋設定 |
| 運用対象 | ゼロ | BQ＋スキルcron | 同左（Artifactは運用不要） |
| 将来拡張（キャンバス・書込UI） | × 不可能 | △ 自作MCPから | ◎ 同構成のまま伸ばせる |

> **推奨 — 案3。根拠は4つ**
> ① 本システムの核である照合と確信度計算がNotion単体では成立しない（ベクトル検索の不在・数式機能の限界・rollup劣化はいずれも裏取り済み）→案1除外
> ② 実測38件/本により、ファクト全量の閲覧はNotionに置けない→閲覧面が必須
> ③ その閲覧面はGoogle公式BigQueryコネクタが「設定のみ」で提供する（自作サーバ不要という事実が案3の追加コストをほぼゼロにする）
> ④ 双方向同期の複雑さ（案2・3共通の弱点）は所有権固定＋投影最小化で管理可能と設計済み。案3ではNotion投影が「レビューと議論の分だけ」に減るためむしろ小さくなる
> **進め方: まず案2の縦1ループを2〜4週で動かし、その直後に設定だけで案3へ。**

---

## §5 データベース設計（BigQuery）

```
-- dataset: core（データ本体）
products(id, name, status)
research_questions(id, product_id, question, status, created_at)
sources(id, product_id, research_question_id, type, title, occurred_at,
        raw_ref,          -- GCS上の原文への参照
        content_hash,     -- 同じ議事録の二重取り込み防止
        channel,          -- link / paste / auto
        ingestion_status, meta JSON)
highlights(id, source_id, span_start, span_end, text)
facts(id, product_id, source_id, statement, verbatim_quote,
      origin, speaker_attrs JSON, extracted_confidence, status, created_at)
fact_highlights(fact_id, highlight_id)
insights(id, product_id,  -- NULL = 全社横断
         statement, description, status, owner,
         confidence_score, confidence_level, confidence_breakdown JSON,
         freshness_score, last_evidence_at, superseded_by_id, published_at)
insight_versions(insight_id, version, statement, description, edited_by, edited_at)
evidence_links(id, fact_id, insight_id, stance, weight,
               linked_by, suggestion_id, rationale, created_at)
               -- UNIQUE(fact_id, insight_id)
suggestions(id, product_id, type, target_refs JSON, payload JSON, rationale,
            score, model_version, prompt_version,
            status, reviewed_by, reviewed_at, expires_at, created_at)
tags(id, name, facet) / taggings(tag_id, entity_type, entity_id)

-- dataset: derived（派生データ。いつでも再構築できる）
embeddings(entity_type, entity_id, model_version, vector, created_at)
    -- ML.GENERATE_EMBEDDING で生成、VECTOR_SEARCH で照合

-- dataset: ops（運用データ）
audit_logs(id, actor_type, actor_id, action, entity_type, entity_id,
           diff JSON, suggestion_id, created_at)   -- 追記専用
sync_state(entity_type, entity_id, notion_page_id,
           content_hash, last_synced_at)           -- BQ⇄Notion対応表のマスタ
skill_runs(id, skill, started_at, finished_at, status, stats JSON)
```

設計メモ:
- **workspace系テーブルは存在しない**。仕切りは product_id のみ。主要テーブルは product_id でクラスタリング
- アクセス制御はBQのIAM（スキル実行者=オーナー、閲覧者=dataViewer）
- audit_logs は追記専用（UPDATE/DELETE権限を発行しない）
- 確信度の再計算は evidence_links 変化時（review-apply内）＋日次の減衰更新（スケジュールドクエリ）
- キャンバス系テーブルは v1b で追加。今は作らない

---

## §6 Notion側の設計（投影・レビュー・429対策）

### 6.1 DB構成（4つ）と投影規約

| DB | 置くもの | Notionで編集できるもの |
|---|---|---|
| インサイトDB | active＋needs_review のみ | **statement / description / status のみ** |
| 提案Inbox DB | pending のみ。処理済みは完了アーカイブ | **status のみ**（ファクトは議事録1本＝1レビューの一括承認） |
| ファクトDB | 直近30日＋リンク済みのみ（全量はArtifactで見る） | 不可（修正は修正提案として起票） |
| リサーチDB | メタデータのみ（タイトル・種別・日付・GCSリンク） | 不可 |

- コメント・議論・レポートページは**Notionがマスタ**（唯一の例外）。夜間にBQへバックアップ
- 計算値はBQの結果を「ただの数値・セレクト」として書く。**rollup・formulaは使わない**（2,000〜3,000行からの劣化要因）。ビューには必ずフィルタ＋読み込み上限
- 投影上限の目安: インサイト≤1,000行／ファクト≤2,000行。超えたら古いものを外す（BQに全量あり）

### 6.2 429対策

- Notion APIは平均3req/s。書込は単一の流れに直列化し1件350ms間隔。429は Retry-After 秒停止→再発で待ち倍増
- content_hash が変わったレコードだけ書く。議事録1本≒90〜120リクエスト≒40秒、バックフィル50本≒30分（夜間）

### 6.3 Notion編集のBQ取り込み（逆方向同期）

- `/review-apply` が last_edited_time（10分オーバーラップ窓）で変更検出。Claude自身の編集はスキップし、投影時hashと比較して人間の編集だけを拾う
- 編集可フィールドはBQへ反映（インサイト文言は版を残す）。編集不可フィールドはBQ値で復元し notion_manual_edit として監査記録。同期ステータス（synced/pending/rejected）をNotionに表示し、無言で戻さない
- ページ削除・アーカイブはサポート外。夜間突合がBQから復元

---

## §7 ロードマップ

| 段階 | 内容 | ゲート |
|---|---|---|
| **MVP-0（2〜4週）** | 案2の縦1ループ: BQスキーマ→スキル4本→Notion 4DB。議事録を渡す→抽出→照合→Inbox承認→確信度が動く、が1本つながる | 承認率50%以上／週次レビュー習慣／判断が変わった事例1件 |
| **v1a（+1〜2週）** | 案3へ: 公式BQコネクタ設定＋閲覧Artifact（検索・全量一覧・確信度内訳）。window.claude.mcp実挙動検証もここで完了 | チームが閲覧Artifactを日常的に開く |
| **v1b（+1〜2ヶ月）** | 書込用自作MCP＋Artifactで承認・編集・分析キャンバス。Notionはコメント・配布に役割縮小 | キャンバス経由の昇格が月N件 |
| **v2** | 取り込み自動化（新着監視）、週次レポート本運用、抽出粒度の校正 | — |

---

## §8 リスクと未決事項

### リスク

| リスク | 緩和策 |
|---|---|
| **取り込み習慣が続かない**（最大の事業リスク） | 「リンクを貼るだけ」の1アクションに絞る。v2で自動化 |
| レビュー負荷（実測38件/本） | 議事録1本＝1レビューの一括承認。個別レビューはインサイト系のみ |
| 確信度が信頼されない | 内訳の完全開示・係数調整可・4段階主表示。承認率とのズレで校正 |
| 同期ドリフト（BQ⇄Notion） | 所有権固定・hash差分・夜間突合・同期ステータス可視化 |
| window.claude.mcp 実挙動未検証 | v1a冒頭で「検索1画面」の縦スライスで確認してから広げる |
| 抽出粒度（38件は多すぎる可能性） | 最初の数本で「根拠リンクに使われた率」を測り重要度フィルタを校正 |

### 未決事項

- 確信度の係数（手法の重み・半減期）の初期値（§2.3の仮説を最初の1ヶ月で校正）
- Slack・Chatworkスレッドの「1リサーチ」の切り方（スレッド単位か期間単位か）
- 閲覧者のIAM運用（dataViewer付与の手順と棚卸し）
- 発言者の匿名化レベル（speaker_attrs の範囲）
- v1b書込MCPの認証設計（カスタムコネクタのOAuth）

---

## 参考資料

- Tomer Sharon "Atomic UX Research" ／ Guest et al. (2006) データ飽和 ／ GRADEエビデンス評価
- [Notion API Request limits](https://developers.notion.com/reference/request-limits) ／ [Notion公式: DB読み込み最適化](https://www.notion.com/help/optimize-database-load-times-and-performance)
- [Google Cloud: BigQuery MCP server](https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp)
- [Centou（ベンチマーク）](https://centou.jp/)

## 変更履歴

- 2026-08-10: v1（SaaS前提・案1/案2構成）。詳細はgit履歴参照
- 2026-08-11: **v2 全面改訂** — 社内・プロダクト別に前提を再設定。Workspace/テナント/SaaSアーキテクチャを削除、呼び名修正（リサーチクエスチョン・リサーチ等）、AI処理をClaude Codeスキル4本に変更、アーキテクチャ3案（すべてNotion/BQ×Notion/＋閲覧Artifact）の根拠付き比較で案3を推奨、確信度モデルの根拠を明記、DB設計を更新
