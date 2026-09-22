# Notion成果物の作り方レシピ

ライフプランの成果物は「**ハブページ（全体像）＋ 2つのデータベース（やること／お金）**」で構成する。Notion MCP が使える前提（`notion-create-pages` / `notion-create-database` / `notion-create-view` / `notion-update-page` / `notion-update-data-source` / `notion-fetch`）。

## 0. 置き場所の確認
ユーザーに保存先ページのURLを聞く（または既存の「ライフプラン」ページ等）。`notion-fetch` で親ページを確認してから作る。

## 1. ハブページ（読みやすさ最優先）
長い1ページのベタ書きは嫌われる。**コールアウトで要点を目立たせ、詳細はトグルで折りたたむ。**

Notion-flavored Markdown の要点（`notion://docs/enhanced-markdown-spec` を読むと確実）：
- コールアウト：
  ```
  <callout icon="⭐" color="green_bg">
  	**見出し**
  	- 中身（子要素はタブで字下げ）
  </callout>
  ```
- トグル見出し：`## 見出し {toggle="true"}` の次行から**タブ字下げ**で中身（表も各行タブ字下げ）。
- 目次：`<table_of_contents/>`
- 既存DBをページ末尾に埋め込む（移動させない参照）：
  ```
  <database url="{{DB_URL}}" inline="false" data-source-url="collection://{{DATA_SOURCE_ID}}">DB名</database>
  ```
  ※ `replace_content` でページを書き換える時は、この行を必ず残すこと（消すと子DBが外れる）。色は `blue_bg/green_bg/red_bg/yellow_bg/gray_bg` 等。

おすすめ構成：
1. 🗺️ 概要コールアウト（このページの説明・注意書き）
2. 📂 使い方コールアウト（下のDBの説明）
3. `<table_of_contents/>`
4. 前提テーブル
5. 🚨 いますぐやることコールアウト（最優先タスク）
6. ⭐ 最重要ポイントのコールアウト（例：給付を最大化する条件）
7. 📅 月別/年別タイムライン（各期を `### … {toggle="true"}` で個別トグル）
8. 💰 もらえるお金／💸 かかるお金（トグル＋表）
9. ✅ 決めることチェックリスト（トグル＋ `- [ ]`）
10. 住まい／資産形成／リスク管理 など（トグル）
11. 📌 次のステップコールアウト＋出典トグル
12. 末尾に2つのDBを埋め込み

## 2. やること・タイムライン DB
`notion-create-database`（DDL）。例：
```
CREATE TABLE ("名前" TITLE, "時期" DATE,
  "種別" SELECT('手続き':blue,'決定':purple,'行事':pink,'準備':orange,'健診/点検':green),
  "担当" SELECT('本人':blue,'配偶者':red,'両方':green),
  "ステータス" STATUS, "メモ" RICH_TEXT)
```
- 行は `notion-create-pages`（parent= data_source_id）。日付は `"date:時期:start": "YYYY-MM-DD"` 形式。
- ビューを追加（`notion-create-view`）：
  - タイムライン：`TIMELINE BY "時期" TO "時期"` / `SORT BY "時期" ASC`
  - 担当ボード：`GROUP BY "担当"`
  - 一覧（テーブル）

## 3. お金 DB
```
CREATE TABLE ("名前" TITLE, "区分" SELECT('もらえる':green,'かかる':red),
  "金額の目安" RICH_TEXT, "時期" RICH_TEXT,
  "制度元" SELECT('国':blue,'都道府県':purple,'市区町村':orange,'健保':green,'税':yellow,'実費':gray),
  "申請期間・窓口" RICH_TEXT, "リンク" URL, "メモ" RICH_TEXT)
```
- もらえるお金は **制度元・申請期間・公式リンク・説明** を必ず埋める（金額は事前にWeb確認）。
- ビュー：`GROUP BY "区分"`（もらえる/かかるボード）、申請期限順のテーブルなど。
- 金額はレンジが多いので `金額の目安` は数値型でなくテキストが扱いやすい。

## 4. 仕上げ
- `notion-fetch` で作成後の構造を確認（DBが重複していないか、埋め込みが残っているか）。
- ユーザーに各URLと「タイムラインビューで今月やることが見える」等の使い方を一言添える。

## 注意
- プロパティ名が `url`/`id`（大小無視）の場合は `userDefined:` プレフィックスが要る（`リンク` は不要）。
- 既存ページを `replace_content` で整形し直す時は、末尾のDB埋め込み行を新コンテンツに含めて子DBを保持する。
- ページに個人情報が入るのは当然OK（それは利用者のNotion）。このスキルの**ファイル**側には個人情報を書かないこと。
