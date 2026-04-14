
---

## 環境チェック（preflight）

作業開始時、**必要なツールが存在するかを最初に確認**してください。欠けている場合は fallback せず、即座に `BLOCKED` としてタスクを停止し Yuki へ報告します（静かに静的モードへ切り替えると検証漏れを隠蔽する恐れがあります）。

### Riku（実装エンジニア）の必要ツール

| ツール | 確認コマンド | 用途 |
|---|---|---|
| go | `command -v go` | Go ビルド・テスト実行 |
| git | `command -v git` | バージョン管理 |

Goプロジェクト着手前に必ず:
```bash
command -v go >/dev/null 2>&1 || {
  echo "BLOCKED: missing tool: go"
  exit 1
}
```

### Sora（QA）の必要ツール

| ツール | 確認コマンド | 用途 |
|---|---|---|
| go | `command -v go` | `go test ./...`, `go vet`, `go build` |
| git | `command -v git` | diff 検証 |

テスト実行を伴うレビュー前に必ず上記を確認。**go が無い場合は「静的レビューのみ」と明示的に宣言**してから作業開始（黙って省略しない）。

### ブロック時の報告フォーマット

```
🚧 BLOCKED: missing tool: [tool name]
影響: [どの作業ができないか]
提案: [代替手段、またはインストール方法]
```

Yuki へは `BLOCKED` ステータスとともにキューの notes へ詳細を書きます。
