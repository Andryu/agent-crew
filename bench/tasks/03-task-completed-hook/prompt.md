# タスク: タスク完了シグナルを記録するフックを作る

このリポジトリでは .claude/_queue.json でタスクを管理し、.claude/_signals.jsonl に
出来事を1行1JSONで追記している。タスク完了時に呼ばれるフックスクリプト
.claude/hooks/task_completed.sh を新しく作ってほしい。

## 動き

- キューから status が "IN_PROGRESS" のタスクを探し、その slug と assigned_to、
  キュー全体の sprint を読み取る。IN_PROGRESS が複数あれば最初の1件だけ扱う。
- _signals.jsonl に次のキーを持つ JSON を1行追記する:
  - ts（時刻）
  - sprint（キューの sprint）
  - slug
  - agent（タスクの assigned_to。無ければ "unknown"）
  - event（固定で "task_completed"）
  - tool_use_id（環境変数 CLAUDE_TOOL_USE_ID の値。無ければ "unknown"）
- キューのパスは環境変数 QUEUE_FILE、出力先は SIGNALS_FILE で差し替えられること
  （省略時はそれぞれ .claude/_queue.json と .claude/_signals.jsonl）。

## 受け入れ基準

- IN_PROGRESS のタスクが1件あれば、上記の内容の JSON が1行だけ追記される。
  すでにあった行はそのまま残る。
- slug に空白・日本語・引用符（"）が入っていても、追記された行は正しい JSON になる。
- IN_PROGRESS が無い・キューファイルが無い・jq が入っていない、のどの場合も
  何も追記せず終了コード 0 で終わる（フックなので他の処理を止めてはいけない）。
- キューファイルの中身は一切書き換えない（読み取りのみ）。
