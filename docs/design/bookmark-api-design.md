# bookmark-api 設計ドキュメント

## 概要

URLブックマークを管理するREST API。インメモリストアで動作し、認証なし。
最小限の構造で始め、必要に応じて拡張可能な設計とする。

## データモデル

### Bookmark

```go
type Bookmark struct {
    ID        string    `json:"id"`
    URL       string    `json:"url"`
    Title     string    `json:"title"`
    Tags      []string  `json:"tags"`
    CreatedAt time.Time `json:"created_at"`
}
```

- `ID`: UUID v4（サーバー側で生成）
- `URL`: 必須。形式バリデーションあり
- `Title`: 必須。空文字不可
- `Tags`: 任意。0個以上の文字列スライス

## エンドポイント定義

### POST /bookmarks — ブックマーク作成

リクエスト:
```json
{
  "url": "https://example.com",
  "title": "Example Site",
  "tags": ["tech", "go"]
}
```

レスポンス: `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://example.com",
  "title": "Example Site",
  "tags": ["tech", "go"],
  "created_at": "2026-04-12T10:00:00Z"
}
```

エラー:
- `400 Bad Request` — URL/Title未指定、URL形式不正

### GET /bookmarks — ブックマーク一覧取得

クエリパラメータ:
- `tag` (任意): 指定タグを持つブックマークでフィルタ。複数指定時はAND条件（例: `?tag=go&tag=tech`）

レスポンス: `200 OK`
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "url": "https://example.com",
    "title": "Example Site",
    "tags": ["tech", "go"],
    "created_at": "2026-04-12T10:00:00Z"
  }
]
```

該当なしの場合は空配列 `[]` を返す（404ではない）。

### DELETE /bookmarks/{id} — ブックマーク削除

レスポンス: `204 No Content`

エラー:
- `404 Not Found` — 指定IDのブックマークが存在しない

## エラーレスポンス形式

全エラーで統一:
```json
{
  "error": "説明メッセージ"
}
```

## パッケージ構成

```
bookmark-api/
├── main.go              # エントリポイント、サーバー起動
├── handler/
│   └── bookmark.go      # HTTPハンドラ（リクエスト解析・レスポンス生成）
├── model/
│   └── bookmark.go      # Bookmark構造体定義
├── store/
│   └── memory.go        # インメモリストア（Store interface + MemoryStore実装）
└── go.mod
```

### 各パッケージの責務

| パッケージ | 責務 |
|-----------|------|
| `main` | サーバー起動、ルーティング定義、依存注入 |
| `handler` | HTTPリクエスト/レスポンスの変換。ビジネスロジックは持たない |
| `model` | ドメインモデル定義。依存なし |
| `store` | データ永続化の抽象化。`Store` interfaceとインメモリ実装 |

### Store interface

```go
type Store interface {
    Create(bookmark model.Bookmark) error
    List(tags []string) []model.Bookmark
    Delete(id string) error
}
```

`Delete` は存在しないIDの場合にエラーを返す。

### ルーティング（Go 1.22+ ServeMux）

```go
mux := http.NewServeMux()
mux.HandleFunc("POST /bookmarks", h.Create)
mux.HandleFunc("GET /bookmarks", h.List)
mux.HandleFunc("DELETE /bookmarks/{id}", h.Delete)
```

## 設計判断のポイント

1. **フラットなパッケージ構成**: handler/model/storeの3層。Clean Architectureのような多層構造は、この規模では過剰
2. **Store interface**: インメモリ実装のみだが、interfaceを切ることでテスト時のモック差し替えとDB移行時の変更範囲を限定
3. **タグフィルタはAND条件**: 複数タグ指定時、すべてのタグを持つブックマークのみ返す。OR条件より直感的で実装も単純
4. **ページネーションなし**: インメモリストアで個人利用のため、初期実装では不要。必要になった時点で `cursor` パラメータを追加可能
5. **UUID v4をID**: 連番だとストア実装に状態管理が増える。UUIDなら生成がステートレス
