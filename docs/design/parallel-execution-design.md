# 並列実行解禁 設計メモ

GitHub Issue #9 / branch: `feat/phase1-parallel`

## 概要

現在の「並列委譲禁止」ルールを条件付き許可に緩和し、独立したタスクの同時実行を可能にする。

## `_queue.json` スキーマ変更

タスクオブジェクトに2フィールドを追加:

```json
{
  "parallel_group": "pg-sprint02-a",
  "depends_on": ["slack-persona-design"]
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `parallel_group` | `string \| null` | 同一値のタスクは並列実行可。`null` は直列のみ |
| `depends_on` | `string[]` | 完了を待つタスクのスラッグ一覧 |

`depends_on` が今回の核心。現状は `notes` に文字列で書かれており機械解析不可。

## queue.sh の改修方針

### 追加: `parallel-handoff` コマンド

複数タスクを単一のロック取得内で一括解放:

```bash
queue.sh parallel-handoff <slug1>:<agent1> <slug2>:<agent2> ...
```

### ロック強化

`acquire_lock` にスタールロック検出を追加（mtime が30秒以上古ければ強制削除）。

### 既存コマンドへの変更なし

`start / done / qa / block / retry / show / next` の動作・インターフェースは一切変更しない。

## pm.md 委譲ルール改訂案

```
【並列委譲の条件】
1. 対象タスクに同一の parallel_group 値が設定されている
2. depends_on の全タスクが DONE 状態である
3. risk_level が "high" のタスクは含まない
4. 担当エージェントが互いに異なる（同一エージェントへの同時委譲は禁止）

【手順】
queue.sh parallel-handoff <slug1>:<agent1> <slug2>:<agent2>

【完了監視】
各エージェントは自分のタスクを done するが handoff は行わない。
Yukiが parallel_group 内の全タスク DONE を確認して次フェーズを handoff する。
```

## Slack通知の整理

| 通知タイプ | 変更内容 |
|---|---|
| 並列グループ開始 | Yukiが全員分まとめて1通送信 |
| 個別完了 | 変更なし（既存フロー流用） |
| グループ全体完了 | 新設: 全タスク DONE 検知でYukiが1通送信 |
| ブロック発生 | 変更なし（即時通知） |

## 実装優先順位

1. `_queue.json` スキーマに `parallel_group`・`depends_on` 追加
2. `queue.sh` に `parallel-handoff` コマンド追加
3. `queue.sh` の `acquire_lock` にスタールロック検出追加
4. `pm.md` の委譲ルール改訂
5. 並列書き込み競合テスト（10プロセス同時実行）

## オーナーへの確認事項

- `depends_on` の既存タスクへのバックフィルは行うか
- `parallel_group` は Yuki が自動アサインするか、スプリント計画時に手動設定するか
- 並列実行するエージェントの同時数に上限を設けるか
