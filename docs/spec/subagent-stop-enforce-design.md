# queue.sh done 実行漏れ 構造対策 設計書（Issue #139）

> 対象slug: `subagent-stop-enforce-design`（Sprint-26 #7, risk_level: high）。実装は `subagent-stop-enforce-impl`（#8, Riku）、QAは `subagent-stop-enforce-qa`（#9, Sora）。

## 1. 問題

`pm-learned-rules.md` の `agent-crew-sprint-25-process-001` が示す通り、実装タスク完了後に `scripts/queue.sh done` を呼ばずに完了報告のみで終わる事象が **2連続**（Sprint-24 → Sprint-25）で再発した。文書に「やること」を書くだけでは実行が保証されないという組織憲章前文の教訓通り、**構造的な検知**が必要。

## 2. 方針

`SubagentStop` フック（サブエージェントが応答を終える瞬間に発火）で、`_queue.json` 上に「`start` イベントだけが記録され、その後 `done`/`qa`/`block` のいずれも記録されていない `IN_PROGRESS` タスク」が存在するかを確認し、あれば stderr に警告を出す。

**`enforce-retro-stop.sh`（Issue #128）の前例を踏襲する**:
- **常に `exit 0`**。ブロックしない（`exit 2` は使わない）
- 誤検知バイパスを複数用意し、判定不能な場合は「警告を出さずに抜ける」を安全側のデフォルトとする
- 既存の `subagent_stop.sh`（次ステップ提示・Slack通知）とは責務を分離し、**別スクリプト・別フックエントリ**として追加する（既存ロジックへの変更ゼロ）

## 3. 検知ロジック

### 3.1 対象イベント

`_queue.json` の各タスクは `events[]` 配列にアクション履歴を持つ（`start` / `done` / `qa` / `block` 等、`scripts/queue.sh` が自動追記）。

**検知条件**: `status == "IN_PROGRESS"` かつ `events` の中に `action != "start"` のイベントが1件も無いタスク。

これは「`queue.sh start` は呼ばれたが、その後 `done`/`qa`/`block` のいずれも呼ばれていない」状態と同値であり、まさに `agent-crew-sprint-25-process-001` が指摘した再発パターンそのものである。

### 3.2 誤検知バイパス（いずれか1つでも満たせば即 `exit 0`、警告なし）

| # | バイパス条件 | 理由 |
|---|------------|------|
| 1 | `jq` が使用できない | 判定手段が無い以上、警告よりも黙って抜ける方が安全 |
| 2 | `.claude/_queue.json` が存在しない | スプリント外のリポジトリ操作（キュー管理を使っていないセッション）を誤検知しない |
| 3 | `_queue.json` が壊れている（JSONとしてparse不可） | 判定不能。破損検知は別の関心事（`audit-scan.sh` 側） |
| 4 | `.sprint` フィールドが無い | テンプレート用の空キュー等、実運用外のキューを対象外にする |
| 5 | `IN_PROGRESS` のタスクが1件も無い | 該当タスクなし。**既に `DONE`/`BLOCKED`/`READY_FOR_*` になっているタスクはこの時点で自動的に対象から外れる**（「既にDONE」バイパスは本条件に内包される） |

### 3.3 既知の限界（残課題として明記し、対策はしない）

- 本フックは「どのサブエージェントがどのタスクを担当していたか」を厳密には対応付けられない（Claude CodeのSubagentStopフックにサブエージェント↔タスクslugの紐付け情報が渡されないため）。そのため、**複数タスクが並行して `IN_PROGRESS` になる運用**（本来のキュー運用ルール「並列実行禁止、進めるのは1タスクだけ」に反する状態）が発生した場合、無関係なサブエージェント終了時に警告が出ることがありうる
- この限界は許容する。警告のみでブロックしないため実害は「気づきの通知が早すぎる/多すぎる」程度に留まり、`enforce-retro-stop.sh` と同じリスク判断（誤検知で処理を止める方が深刻）に従う

## 4. Bashコードサンプル（`bash -n` で構文検証済み）

以下は `subagent-stop-enforce-impl`（#8, Riku）が `scripts/enforce-queue-done-stop.sh` として実装する際の参照コードである。**このサンプルは `bash -n` で構文検証済み**（Alexが `sdd-adr-design` 実施環境で確認、`agent-crew-sprint-08-tooling-001` 準拠）。Rikuは実装時にファイル名・パスをこのまま採用し、必要に応じてコメントを調整してよい。

```bash
#!/usr/bin/env bash
# scripts/enforce-queue-done-stop.sh
#
# SubagentStop フック用スクリプト（Issue #139）。
# サブエージェント（Riku/Sora/みゆきち/Alex等）が queue.sh done/qa/block を
# 呼ばずに応答を終えてしまい、_queue.json 上のタスクが IN_PROGRESS のまま
# 取り残される再発パターン（agent-crew-sprint-25-process-001 で2連続確認）
# への構造的対策。
#
# 設計方針（risk_level: high につき明記, enforce-retro-stop.sh の前例踏襲）:
#   このスクリプトは SubagentStop を「ブロック」しない（exit 2 は使わない）。
#   常に exit 0 で終了し、警告は stderr へのメッセージのみとする。
#
# バイパス条件（いずれか1つでも満たせば即 exit 0、警告なし）:
#   1. jq が使用できない
#   2. .claude/_queue.json が存在しない、または壊れている
#   3. .sprint フィールドがない（スプリント外のキュー）
#   4. IN_PROGRESS のタスクが1件も無い（＝該当タスクなし。既にDONE等も含む）

set -uo pipefail
# 注意: set -e は使わない。途中の jq コマンドが失敗しても
# 「警告を出さずに exit 0」へ安全にフォールスルーさせるため。

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [[ -z "$REPO_ROOT" ]]; then
  exit 0
fi

QUEUE_FILE="${QUEUE_FILE:-$REPO_ROOT/.claude/_queue.json}"  # 環境変数優先（§7のQA手順と整合。実装時にRikuが検知した設計内不整合の修正）

if [[ ! -f "$QUEUE_FILE" ]]; then
  exit 0
fi

if ! jq -e . "$QUEUE_FILE" >/dev/null 2>&1; then
  exit 0
fi

SPRINT=$(jq -r '.sprint // empty' "$QUEUE_FILE" 2>/dev/null)
if [[ -z "$SPRINT" ]]; then
  exit 0
fi

# --- IN_PROGRESS タスクのうち、start イベント以降に何も記録されていないものを検出 ---
STALE_TASKS=$(jq -r '
  .tasks[]?
  | select(.status == "IN_PROGRESS")
  | select(((.events // []) | map(select(.action != "start")) | length) == 0)
  | .slug + "|" + (.assigned_to // "unknown")
' "$QUEUE_FILE" 2>/dev/null)

if [[ -z "$STALE_TASKS" ]]; then
  exit 0
fi

{
  echo ""
  echo "⚠️  [enforce-queue-done-stop] スプリント '${SPRINT}' に、start 後まだ"
  echo "    done/qa/block が記録されていない IN_PROGRESS タスクがあります:"
  while IFS='|' read -r slug agent; do
    [[ -z "$slug" ]] && continue
    echo "      - ${slug}（担当: ${agent}）"
  done <<< "$STALE_TASKS"
  echo "    queue.sh done/qa/block の実行を忘れていないか確認してください。"
  echo "    （このメッセージは警告のみで、処理はブロックされません）"
  echo ""
} >&2

exit 0
```

## 5. `.claude/settings.json` への登録（既存hooksを壊さないjqマージ手順）

**既存の `subagent_stop.sh` の呼び出し・他フックには一切触れず、`hooks.SubagentStop` 配列に新規エントリを1件 `+=` で追加するのみ**とする。`--argjson` で新規エントリをJSONとして安全に渡し、追加後に `jq -e .` でJSONとして正当かを検証してから上書きする（壊れたJSONで上書きしてしまう事故を防ぐ）。

```bash
NEW_HOOK='{"hooks":[{"type":"command","command":"bash -c '"'"'cd \"$(git rev-parse --show-toplevel 2>/dev/null)\" && scripts/enforce-queue-done-stop.sh || true'"'"'"}]}'

jq --argjson newhook "$NEW_HOOK" '.hooks.SubagentStop += [$newhook]' .claude/settings.json > .claude/settings.json.tmp \
  && jq -e . .claude/settings.json.tmp >/dev/null \
  && mv .claude/settings.json.tmp .claude/settings.json
```

**Alexが実際に検証済み**: 上記と同等の手順（`command` は簡略形 `"scripts/enforce-queue-done-stop.sh || true"`）を `.claude/settings.json` のコピーに対して実行し、以下を確認した。

- `jq -e .` によるJSON構文検証が通過する
- 追加後の `.hooks.SubagentStop` に新規エントリが1件増え、既存の `.claude/hooks/subagent_stop.sh` エントリはそのまま残っている
- `.hooks.Stop`（無関係な配列）が一切変化していない（`diff` で確認済み）

Rikuは実装時、上記コマンドをそのまま実行するか、または `Write` ツールで `.claude/settings.json` 全体を手動編集してもよい（後者の場合、既存の `SubagentStop` 配列に1エントリ追加するだけで、他のキー・配列は一切変更しないこと）。

## 6. `subagent-stop-enforce-impl`（Riku, #8）への引き継ぎ

- 実装対象:
  1. `scripts/enforce-queue-done-stop.sh`（本設計書 §4 のコードをそのまま採用可）を新規作成し `chmod +x`
  2. `.claude/settings.json` の `hooks.SubagentStop` に §5 のエントリを追加（既存 `subagent_stop.sh` 呼び出しは変更しない）
- 委譲時の注意（sprint-26.md 記載事項の再掲）: 既存 hook スクリプト（`subagent_stop.sh` / `task_completed.sh`）全文を丸ごと渡さないこと。差分（新規ファイル＋settings.jsonへの1エントリ追加）に絞って委譲する
- `permissions.allow` への新規追加は不要（`scripts/enforce-queue-done-stop.sh` はフックから自動実行されるため、Bashツール経由の直接実行許可を明示登録する必要はない。ただしQA実機検証でBash経由手動実行する場合は `Bash(scripts/enforce-queue-done-stop.sh *)` の追加が必要になる可能性があり、その場合はQA側でブロッカー化してYukiに申請すること）

## 7. `subagent-stop-enforce-qa`（Sora, #9）への引き継ぎ

- 実機検証手順（`agent-crew-sprint-25-reliability-001` 準拠、静的レビューのみでのAPPROVED禁止）:
  1. `_queue.json` のコピーを作成し、テスト用タスクを1件 `IN_PROGRESS` かつ `events` を `start` のみにした状態を作る
  2. `QUEUE_FILE=<コピーのパス> bash scripts/enforce-queue-done-stop.sh` を実行し、stderrに警告が出ることを確認する
  3. 同じタスクに `done` イベントを追加した状態で再実行し、警告が出ないことを確認する（バイパス条件5の動作確認）
  4. `.claude/_queue.json` が存在しないディレクトリで実行し、`exit 0` かつ無警告であることを確認する（バイパス条件2）
  5. 常に `echo $?` で `exit 0` であることを毎回確認する（ブロックしない設計の担保）
