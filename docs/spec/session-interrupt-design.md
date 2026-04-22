# セッション中断タスク検出機構 — 設計書

Sprint-05 / Issue #39
作成: Alex（2026-04-23）

---

## 1. 「中断タスク」の定義

### 定義

> `status == "IN_PROGRESS"` かつ、`events[]` の最後の `start` アクションのタイムスタンプから
> **60分以上**経過しているタスクを「中断タスク（stale task）」とみなす。

### 根拠

- Claude セッションは通常数分〜最大30分程度で完了する
- レート制限によるウォームアップ待機（最大60分）を考慮し、60分を閾値とした
- Bash タイムアウトは `timeout 30` が標準（ADR-004 Section 5）。最長タスクでも60分は十分なバッファ

### タイムスタンプの取得方法

```
stale_start_ts = max(events[].ts where action == "start")
elapsed = now - stale_start_ts
is_stale = (status == "IN_PROGRESS") AND (elapsed >= 60 minutes)
```

events にstartが存在しない IN_PROGRESS タスクは「不整合状態」として別途警告する。

---

## 2. 検出タイミング

### 採用案: `queue.sh show` 呼び出し時に検出

`queue.sh show`（引数なし）の実行時に中断タスクを検出し、STDERRに警告を出力する。

#### 採用理由

| 検出タイミング | メリット | デメリット |
|-------------|---------|---------|
| **show 呼び出し時**（採用） | 追加プロセス不要。オーナーが状況確認する自然なタイミングと一致 | リアルタイムではない |
| session_start hook | 早期検出 | Claude の session_start hook は不安定・環境依存 |
| 定期実行（cron/launchd） | リアルタイムに近い | 常駐プロセスが必要。macOS環境で設定コストが高い |

#### 補足

- `queue.sh next` コマンドでも同様に中断タスクを検出・警告する（次タスク選択前に状態異常を通知するため）
- 将来的に定期実行への移行も可能。その場合は `detect-stale` サブコマンドを単体で呼べる設計にしておく

---

## 3. 通知先と通知フォーマット

### 通知先: STDERR（即時） + Slack（オプション）

#### STDERR 出力（必須）

`queue.sh show` または `queue.sh next` 実行時に、中断タスクが存在すれば STDERR へ出力する。

```
WARN: STALE TASK DETECTED
  slug:    session-interrupt-design
  status:  IN_PROGRESS
  agent:   Alex
  started: 2026-04-23T08:47:15+0900
  elapsed: 73 min
  action:  手動リカバリを検討してください (scripts/queue.sh done または scripts/queue.sh retry)
```

複数の中断タスクが存在する場合は全件を列挙する。

#### Slack 通知（将来実装、Sprint-06 候補）

Slack 通知は現在 `.github/workflows/` の GitHub Actions 経由で実装されている（Sprint-01実績）。
detect-stale を独立コマンドとして実装しておけば、Actions の schedule trigger から呼び出すことができる。

```yaml
# 将来のActions設定イメージ
on:
  schedule:
    - cron: '0 * * * *'   # 毎時0分
jobs:
  detect-stale:
    steps:
      - run: scripts/queue.sh detect-stale --slack
```

Slack メッセージフォーマット（将来）:

```
[WARN] スプリント中断タスク検出
タスク: session-interrupt-design
担当: Alex | 経過: 73分
操作: queue.sh done <slug> <agent> "リカバリ完了" または queue.sh retry <slug>
```

---

## 4. 自動リカバリの可否判断

### 判断基準（ADR-004 Section 5 のリカバリ条件に準拠）

ADR-004 は手動クローズの条件として以下を定める：

1. 出力ファイルが存在し、内容が完了条件を満たしている
2. `events[]` に `start` イベントが記録されている
3. `retry_count` が `MAX_RETRY` 未満である

これらを **自動判定することはしない**。理由：

- 完了条件の定義はタスクごとに異なり（ファイルパスが固定されていない）、汎用的な自動判定は誤判定リスクが高い
- 誤って DONE に遷移すると QA をスキップして次タスクへ進んでしまう（品質ゲートの迂回）

### Sprint-05での設計方針

**自動リカバリは実装しない。検出と通知のみに留める。**

検出後の操作はオーナーまたはエージェントが以下の手順で手動実施する：

```bash
# Step 1: 成果物ファイルの確認
ls -la <期待するファイルパス>

# Step 2a: ファイルが存在し内容が妥当 → 手動DONE
scripts/queue.sh done <slug> <agent> "リカバリ: ファイル確認済み、手動クローズ"
scripts/queue.sh handoff <next-slug> <next-agent>

# Step 2b: ファイルが存在しない → リセット
scripts/queue.sh retry <slug>
# または
scripts/queue.sh block <slug> <agent> "中断・原因不明"
```

### 将来的な自動リカバリの条件（Sprint-06以降の検討事項）

タスクに `output_files: [...]` フィールドが追加されれば、ファイル存在チェックによる自動リカバリが可能になる。
この拡張は queue.json のスキーマ変更を伴うため、別途 ADR を作成して判断する。

---

## 5. 実装の影響範囲

### 採用構成: `queue.sh` に `detect-stale` サブコマンドを追加

```
scripts/
└── queue.sh   # detect-stale サブコマンドを追加（約40〜60行の追加）
```

別スクリプトは作成しない。理由：ロジックが軽量であり、queue.sh の共通ヘルパー（`require_queue`、`now_iso` など）を再利用できるため。

### queue.sh への変更詳細

#### 追加するサブコマンド: `detect-stale`

```bash
queue.sh detect-stale [--slack] [--threshold <minutes>]
```

- `--slack`: Slack 通知を送信（SLACK_WEBHOOK_URL 環境変数が必要）
- `--threshold`: 中断判定の閾値（分、デフォルト60）

#### `show`・`next` への組み込み

`cmd_show`（引数なし呼び出し時）および `cmd_next` の冒頭で `_detect_stale_inline` を呼び出す。
この関数はロックを取得せず読み取り専用で動作し、中断タスクを STDERR に出力するだけ。

#### スキーマ変更

- `_queue.json` のスキーマ変更は**なし**
- `events[].ts` と `status` の既存フィールドだけで判定可能

### 変更ファイルまとめ

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `scripts/queue.sh` | 修正 | `detect-stale` サブコマンド追加、`show`/`next` に検出ロジック組み込み |
| `docs/spec/session-interrupt-design.md` | 新規 | 本ドキュメント |
| `.claude/_queue.json` | 変更なし | スキーマ拡張不要 |

---

## 6. 実装メモ（Riku向け引き継ぎ）

### 中断判定のコアロジック（bash + jq）

```bash
STALE_THRESHOLD_MIN=60

# IN_PROGRESS タスクのうち、最終 start から THRESHOLD 分以上経過しているものを抽出
now_epoch=$(date +%s)
threshold_secs=$((STALE_THRESHOLD_MIN * 60))

jq --argjson now "$now_epoch" --argjson thr "$threshold_secs" '
  .tasks[]
  | select(.status == "IN_PROGRESS")
  | . as $task
  | (.events // [] | map(select(.action == "start")) | last | .ts // null) as $last_start
  | if $last_start == null then
      { slug: $task.slug, issue: "start イベントなし（不整合）" }
    else
      ($last_start | sub("(?<d>[0-9T:+-]+)"; "\(.d)") | strptime("%Y-%m-%dT%H:%M:%S%z") | mktime) as $start_epoch
      | if ($now - $start_epoch) >= $thr then
          { slug: $task.slug, agent: $task.assigned_to, started: $last_start,
            elapsed_min: (($now - $start_epoch) / 60 | floor) }
        else empty end
    end
' "$QUEUE_FILE"
```

注意: macOS の jq は `strptime` でタイムゾーンオフセット付き文字列の扱いが不安定。
`date -j -f` を使った bash 側での変換を代替案として検討すること。

### テスト方法

```bash
# テスト用: 閾値を1分に下げて動作確認
QUEUE_FILE=.claude/_queue.json scripts/queue.sh detect-stale --threshold 1
```

---

*設計書終了*
