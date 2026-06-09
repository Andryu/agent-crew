# 見直し成果物の作り方レシピ

ライフプランの**定期見直し**の成果物は「**見直しダッシュボード（テーマ横断の1枚）＋ 2つのデータベース（資産スナップショット／見直しログ）**」で構成する。Notion MCP が使える前提（`notion-fetch` / `notion-create-pages` / `notion-create-database` / `notion-create-view` / `notion-update-page` / `notion-update-data-source` / `notion-search`）。

**コールアウト/トグルの記法・DDL書式・ビューの作法は `../../life-planner/references/notion-recipe.md` と同じ**（ここでは差分だけ書く。記法に迷ったらそちらと `notion://docs/enhanced-markdown-spec` を参照）。

## 0. 置き場所と既存プランの確認
- 保存先ページの URL をユーザーに聞く。テーマ別プラン（出産プラン等）と**同じ親ページの配下**だと見通しが良い。
- `notion-search`/`notion-fetch` で既存のテーマ別プランを把握し、ダッシュボードからリンクするための URL を控える。
- **重要：テーマ別ハブ（例：出産プラン）には見直し用のDBを足し込まない。** 見直しは資産形成を含むテーマ横断の視点なので、専用ダッシュボードに器を分ける。

## 1. 見直しダッシュボードページ（新規・テーマ横断）
初回見直し時に1枚だけ作る。長いベタ書きは避け、要点はコールアウト、詳細はトグルで。おすすめ構成：

1. 📌 **最新の見直しサマリ**コールアウト
   ```
   <callout icon="📌" color="green_bg">
   	**最新の見直し（YYYY-MM-DD 時点）**
   	- 純資産：◯◯万円（前回比 +◯◯万円）
   	- 目標純資産：◯◯万円／進捗：◯◯%
   	- 次回見直し：YYYY-MM（半年後）
   </callout>
   ```
2. 🔗 **テーマ別プラン**リンク集（出産プラン・住宅プラン等への Notion リンクを箇条書き）
3. `<table_of_contents/>`
4. 📊 資産の推移（スナップショットDBの要点を一言）
5. 末尾に**2つのDBを埋め込み**（移動させない参照。`replace_content` で書き換える時はこの行を必ず残す）：
   ```
   <database url="{{SNAPSHOT_DB_URL}}" inline="false" data-source-url="collection://{{SNAPSHOT_DS_ID}}">資産スナップショット</database>
   <database url="{{LOG_DB_URL}}" inline="false" data-source-url="collection://{{LOG_DS_ID}}">見直しログ</database>
   ```

毎回の見直しでは、①のサマリと②のリンク集を `notion-update-page` で更新する。

## 2. 資産スナップショット DB（時系列追跡の中心）
`notion-create-database`（DDL）。**見直し1回につき1行追加**することで、純資産の推移が一覧で見える。
```
CREATE TABLE ("回" TITLE, "見直し日" DATE,
  "総資産" NUMBER, "現金・預金" NUMBER, "NISA" NUMBER,
  "iDeCo・企業年金" NUMBER, "その他投資" NUMBER,
  "負債（住宅ローン等）" NUMBER, "純資産" NUMBER,
  "目標純資産" NUMBER, "目標との差分" NUMBER, "メモ" RICH_TEXT)
```
- 「回」は `2026-06 第1回` のようなラベル。`見直し日` は `notion-create-pages` で `"date:見直し日:start": "YYYY-MM-DD"` 形式。
- 金額は概算でよい（単位はメモか列名で「万円」等に統一）。`純資産 = 総資産 − 負債`、`目標との差分 = 純資産 − 目標純資産` を都度埋める。
- ビュー（`notion-create-view`）：
  - **推移テーブル（主）**：`SORT BY "見直し日" ASC`。純資産・目標との差分の伸びを上から下へ追える。
  - チャート/グラフビューが使えるなら純資産の折れ線を追加（使えなければテーブルのみでよい）。

## 3. 見直しログ DB
```
CREATE TABLE ("名前" TITLE, "見直し日" DATE,
  "区分" SELECT('資産形成':green,'ライフイベント':blue,'制度改定':purple,'家計':orange,'保険':red),
  "前回からの変化" RICH_TEXT, "気づき・決めたこと" RICH_TEXT,
  "次回までの宿題" RICH_TEXT, "ステータス" STATUS)
```
- 1回の見直しで、区分ごとに行を追加（または要点を数行に集約）。`名前` は「2026-06 資産形成」等。
- ビュー：`GROUP BY "区分"` ボード、`SORT BY "見直し日" DESC` のタイムライン一覧。
- **「次回までの宿題」は次回見直しの冒頭で最初に確認する**ので、必ず埋める（誰が・いつまでに）。

## 4. 周期化（Notion ＋ カレンダー併用）
- **Notion**：ダッシュボード先頭サマリと見直しログの両方に「次回見直し: YYYY-MM（半年後）」を残す。
- **Google カレンダー**：`create_event` で半年後に終日予定「ライフプラン見直し」を作成し、`RRULE:FREQ=MONTHLY;INTERVAL=6`（半年ごと）で繰り返しに。説明欄にダッシュボードページの URL を入れる。`list_events` で同名予定を確認し、**既にあれば重複作成しない**。

## 5. 仕上げ
- `notion-fetch` で作成後の構造を確認（DBが重複していないか、ダッシュボード末尾の埋め込みが残っているか）。
- ユーザーに「スナップショットの推移テーブルで純資産の伸びが見える」「次回はカレンダーに半年後で入れた」等、使い方を一言添える。

## 注意
- プロパティ名が `url`/`id`（大小無視）の場合は `userDefined:` プレフィックスが要る。
- 既存ダッシュボードを `replace_content` で整形し直す時は、末尾のDB埋め込み行を新コンテンツに含めて子DBを保持する。
- ページに個人情報（実資産額・固有URL）が入るのは当然OK（利用者のNotion）。このスキルの**ファイル**側には個人情報を書かないこと。
