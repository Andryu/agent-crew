# bookmark-api UX仕様書

CLI/curlユーザー向けのAPI操作フローとリクエスト/レスポンス仕様。

---

## 1. ユーザーフロー

典型的な操作順序を示す。各ステップで「何が見えるか」「次に何をするか」を明確にする。

```
[1. 一覧を確認（ゼロ状態）]
        │
        ▼
[2. ブックマークを作成]
        │
        ▼
[3. 一覧で作成結果を確認]
        │
        ▼
[4. タグでフィルタして絞り込み]
        │
        ▼
[5. 不要なブックマークを削除]
        │
        ▼
[6. 一覧で削除結果を確認]
```

### フロー詳細

| ステップ | 操作 | 期待する結果 | 次のアクション |
|---------|------|-------------|--------------|
| 1 | `GET /bookmarks` | 空配列 `[]` が返る | データがないことを確認し、作成に進む |
| 2 | `POST /bookmarks` | `201 Created` + 作成されたブックマークJSON | IDを控えておく（削除に使う） |
| 3 | `GET /bookmarks` | 配列に作成したブックマークが含まれる | 内容を目視確認 |
| 4 | `GET /bookmarks?tag=go` | 指定タグを持つもののみ返る | フィルタの動作を確認 |
| 5 | `DELETE /bookmarks/{id}` | `204 No Content`（レスポンスボディなし） | 削除成功を確認 |
| 6 | `GET /bookmarks` | 削除したブックマークが含まれない | 完了 |

---

## 2. エンドポイント別リクエスト/レスポンス例

### 2.1 POST /bookmarks — ブックマーク作成

#### 正常系

```bash
curl -s -X POST http://localhost:8080/bookmarks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://go.dev/doc/tutorial/getting-started",
    "title": "Go入門チュートリアル",
    "tags": ["go", "tutorial"]
  }'
```

レスポンス: `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://go.dev/doc/tutorial/getting-started",
  "title": "Go入門チュートリアル",
  "tags": ["go", "tutorial"],
  "created_at": "2026-04-12T10:00:00Z"
}
```

#### 正常系: タグなしで作成

```bash
curl -s -X POST http://localhost:8080/bookmarks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "title": "Example"
  }'
```

レスポンス: `201 Created`
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "url": "https://example.com",
  "title": "Example",
  "tags": [],
  "created_at": "2026-04-12T10:01:00Z"
}
```

> **注意**: `tags` フィールドを省略した場合、レスポンスでは `null` ではなく空配列 `[]` を返すこと。クライアント側で `len(tags)` のようなコードが null チェックなしで動くようにするため。

#### 異常系: URL未指定

```bash
curl -s -X POST http://localhost:8080/bookmarks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "タイトルだけ"
  }'
```

レスポンス: `400 Bad Request`
```json
{
  "error": "url is required"
}
```

#### 異常系: Title未指定

```bash
curl -s -X POST http://localhost:8080/bookmarks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com"
  }'
```

レスポンス: `400 Bad Request`
```json
{
  "error": "title is required"
}
```

#### 異常系: URL形式不正

```bash
curl -s -X POST http://localhost:8080/bookmarks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "not-a-url",
    "title": "壊れたURL"
  }'
```

レスポンス: `400 Bad Request`
```json
{
  "error": "url is not a valid URL (must start with http:// or https://)"
}
```

#### 異常系: リクエストボディが不正なJSON

```bash
curl -s -X POST http://localhost:8080/bookmarks \
  -H "Content-Type: application/json" \
  -d 'これはJSONではない'
```

レスポンス: `400 Bad Request`
```json
{
  "error": "request body is not valid JSON"
}
```

#### 異常系: Content-Type未指定 / 空ボディ

```bash
curl -s -X POST http://localhost:8080/bookmarks
```

レスポンス: `400 Bad Request`
```json
{
  "error": "request body is empty"
}
```

---

### 2.2 GET /bookmarks — 一覧取得

#### 正常系: 全件取得

```bash
curl -s http://localhost:8080/bookmarks
```

レスポンス: `200 OK`
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "url": "https://go.dev/doc/tutorial/getting-started",
    "title": "Go入門チュートリアル",
    "tags": ["go", "tutorial"],
    "created_at": "2026-04-12T10:00:00Z"
  },
  {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "url": "https://example.com",
    "title": "Example",
    "tags": [],
    "created_at": "2026-04-12T10:01:00Z"
  }
]
```

#### 正常系: ゼロ状態（ブックマークが1件もない）

```bash
curl -s http://localhost:8080/bookmarks
```

レスポンス: `200 OK`
```json
[]
```

> **設計判断**: 空の場合に `404` ではなく `200` + 空配列を返す。「ブックマーク一覧」というリソースは常に存在し、中身が0件なだけ。クライアントは `if len(result) == 0` で空状態を判定できる。

#### 正常系: タグフィルタ（単一タグ）

```bash
curl -s "http://localhost:8080/bookmarks?tag=go"
```

レスポンス: `200 OK` — `go` タグを持つブックマークのみ返る。

#### 正常系: タグフィルタ（複数タグ、AND条件）

```bash
curl -s "http://localhost:8080/bookmarks?tag=go&tag=tutorial"
```

レスポンス: `200 OK` — `go` **かつ** `tutorial` 両方のタグを持つブックマークのみ返る。

#### 正常系: フィルタ結果が0件

```bash
curl -s "http://localhost:8080/bookmarks?tag=存在しないタグ"
```

レスポンス: `200 OK`
```json
[]
```

> ゼロ状態と同様、フィルタ結果が0件でも `200` + 空配列。

---

### 2.3 DELETE /bookmarks/{id} — 削除

#### 正常系

```bash
curl -s -X DELETE http://localhost:8080/bookmarks/550e8400-e29b-41d4-a716-446655440000
```

レスポンス: `204 No Content`（レスポンスボディなし）

> curlで確認する場合は `-w "\n%{http_code}\n"` を付けるとステータスコードが見える:
> ```bash
> curl -s -o /dev/null -w "%{http_code}" -X DELETE \
>   http://localhost:8080/bookmarks/550e8400-e29b-41d4-a716-446655440000
> ```

#### 異常系: 存在しないIDを削除

```bash
curl -s -X DELETE http://localhost:8080/bookmarks/00000000-0000-0000-0000-000000000000
```

レスポンス: `404 Not Found`
```json
{
  "error": "bookmark not found"
}
```

#### 異常系: ID形式不正

```bash
curl -s -X DELETE http://localhost:8080/bookmarks/abc
```

レスポンス: `404 Not Found`
```json
{
  "error": "bookmark not found"
}
```

> **設計判断**: ID形式のバリデーション（UUID形式チェック）を個別に行って `400` を返すこともできるが、結果として「そのIDのブックマークは見つからない」ことに変わりないので `404` に統一する。実装が単純になり、クライアント側のエラーハンドリングも分岐が減る。

---

## 3. エッジケース一覧

| # | ケース | 入力例 | 期待する挙動 | ステータス |
|---|--------|--------|-------------|-----------|
| 1 | タグが空配列 | `"tags": []` | 正常に作成。タグなしブックマーク | `201` |
| 2 | タグが省略 | `"tags"` フィールドなし | 正常に作成。レスポンスの tags は `[]`（nullにしない） | `201` |
| 3 | 同一URLで複数作成 | 同じURLで2回POST | 両方作成される（重複チェックなし）。IDは別々に採番 | `201` |
| 4 | 存在しないIDの削除 | 不正なUUID | `bookmark not found` | `404` |
| 5 | 同一IDで2回削除 | 1回目成功 → 2回目 | 1回目: `204`、2回目: `404` | — |
| 6 | タイトルが空文字 | `"title": ""` | バリデーションエラー | `400` |
| 7 | URLにクエリ文字列含む | `"url": "https://example.com?q=1"` | 正常に作成 | `201` |
| 8 | タグに日本語 | `"tags": ["技術"]` | 正常に作成。フィルタも `?tag=技術` で動作 | `201` |
| 9 | タグに空文字 | `"tags": ["", "go"]` | 空文字タグは無視するか、そのまま保存するか → **Rikuと要相談** | — |
| 10 | 非常に長いURL/Title | 10,000文字超 | 上限チェックするかはスコープ外。初期実装では制限なし | `201` |
| 11 | GETに未知のクエリパラメータ | `?foo=bar` | 無視して全件返す | `200` |
| 12 | DELETEにボディ付き | ボディ付きDELETE | ボディを無視して正常にIDで削除 | `204` |
| 13 | 存在しないエンドポイント | `PUT /bookmarks` | Goの `ServeMux` がデフォルトで `405` または `404` を返す | — |

---

## 4. エラーメッセージ方針

### 基本方針: 英語で統一

| 理由 | 詳細 |
|------|------|
| CLIツール向け | curlやjqでパースすることが前提。多言語対応のコストに見合わない |
| grepしやすい | エラーメッセージでログをgrepする際、英語の方が安定 |
| Go標準の慣習 | Goのエラーメッセージは小文字英語が慣習（`fmt.Errorf("something failed")` ） |

### エラーメッセージ一覧

| ステータス | error値 | 発生条件 |
|-----------|---------|---------|
| `400` | `url is required` | URLフィールドが未指定または空 |
| `400` | `title is required` | Titleフィールドが未指定または空 |
| `400` | `url is not a valid URL (must start with http:// or https://)` | URLの形式バリデーション失敗 |
| `400` | `request body is not valid JSON` | JSONパース失敗 |
| `400` | `request body is empty` | ボディが空 |
| `404` | `bookmark not found` | 指定IDのブックマークが存在しない |

### メッセージの書き方ルール

1. **小文字で始める** — Go慣習に合わせる
2. **何が問題かを具体的に書く** — `"invalid request"` のような曖昧なメッセージは使わない
3. **修正方法のヒントを含める** — URLバリデーションでは `(must start with http:// or https://)` のように期待形式を示す
4. **内部実装の詳細を漏らさない** — スタックトレースやパッケージ名をエラーに含めない

---

## 補足: レスポンスヘッダー

全レスポンスで `Content-Type: application/json` を返すこと（`204 No Content` を除く）。
