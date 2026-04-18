# agent-crew 仕様書 / PRD

最終更新: 2026-04-16
ステータス: Draft v1

---

## 1. 概要 / Why

### 1.1 課題

個人開発では「設計・UX・実装・レビュー」を全部1人でやることになり、文脈切り替えコストが大きい。Claude Code のサブエージェント機能を使えば役割分担はできるが、素のままだと以下が問題になる。

- どのエージェントを次に呼ぶかを毎回人間が判断する必要がある
- エージェント間で **状態（誰が何をやっているか）** を共有する仕組みがない
- レビュー差し戻し → 修正 → 再レビューのループを人間が管理することになる
- 並列実行時に状態ファイルが破損する

### 1.2 ゴール

**個人開発者がトップレベル指示を出すだけで、設計→UX→実装→QA のパイプラインを最後まで回し切る** 半自動エージェントチームを提供する。

非ゴール:
- 商用CIシステムの代替（信頼性は「個人開発で許容できる範囲」）
- 複数人チームでの同時利用（前提は1ユーザー）
- マルチプロジェクト同時並行（同一ワークツリー1セッション前提）

### 1.3 ターゲットユーザー

Claude Code を使って個人開発をしている開発者。日本語でやり取りしたい。Go / フロントエンドなど複数スタックを扱う。

### 1.4 成功指標（KPI）

個人開発スケールでの「うまく機能している」の目安:

| 指標 | 目標 |
|---|---|
| 1スプリントあたりの人間介入回数 | 3回以下（plan承認 / BLOCKED解除 / 最終確認） |
| QA差し戻し率（CHANGES_REQUESTED / 総レビュー数） | 30% 以下 |
| 1スプリント（小機能）完走時間 | 1セッション（90分以内）で初版完了 |
| BLOCKED 自動解除率 | 0%（BLOCKEDは必ず人間判断、サイレントスキップしないこと） |

---

## 2. システム全体像

```
┌─────────────────────────────────────────────────────┐
│  Claude Code 本体セッション（人間との対話）           │
│  ↓ "Use the X agent on slug"                       │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│ │ Yuki │→│ Alex │→│ Mina │→│ Riku │→│ Sora │       │
│ │ (PM) │ │(設計)│ │ (UX) │ │(実装)│ │ (QA) │       │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘       │
│    │        │        │        │        │            │
│    └────────┴────────┴────────┴────────┘           │
│              ↓ scripts/queue.sh                     │
│         .claude/_queue.json                         │
│              ↑                                       │
│  Claude Code → SubagentStop hook → STDOUT/Slack      │
│  （hook はキューを read-only で参照し、次手を提示）  │
└─────────────────────────────────────────────────────┘
```

### 2.1 5 エージェント

| 名前 | 役割 | 主な責務 | モデル |
|---|---|---|---|
| **Yuki** | PM・オーケストレーター | タスク分解、ルーティング、進捗追跡、最終報告 | sonnet |
| **Alex** | アーキテクト | 設計、ADR、DBスキーマ、API設計 | sonnet |
| **Mina** | UXデザイナー | ユーザーフロー、ワイヤー、コンポーネント仕様 | sonnet |
| **Riku** | 実装エンジニア（Go） | コーディング、ユニットテスト | sonnet |
| **Sora** | QA・コードレビュー | 静的レビュー、テスト実行、判定 | sonnet |
| **Hana** | ドキュメントレビュー | PRD/仕様書/READMEの正確性・抜け・矛盾チェック（read-only） | sonnet |

各エージェント定義は `agents/<role>.md` にあり、`build.sh` で `header + vendor本文 + footer + 共通プロトコル` を合成して `.claude/agents/` に配置する。

### 2.2 vendor: agency-agents

`vendor/agency-agents/` に [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) を git submodule として取り込んでいる。「誰（who）」のナレッジは vendor、「どう動くか（how）」は agent-crew 側の overlay で上書きする2層構造。

**現状の合成対象は Alex のみ**。`overlays/architect.{header,footer}.md` だけが存在し、`build.sh` は他のエージェント（Mina/Sora など）にはヘッダが見つからないため vendor 合成をスキップして native 扱いにする。Mina/Sora の vendor 化は将来 overlay を追加した時点で可能。

理由: 役割知識を自前メンテせずアップストリームの更新を取り込みたい。

---

## 3. タスクキュー（Single Source of Truth）

### 3.1 ファイル: `.claude/_queue.json`

エージェント間で共有される唯一の状態。**全エージェントはこのファイルを `scripts/queue.sh` 経由でしか読み書きしない**。

```json
{
  "sprint": "sprint-01",
  "tasks": [
    {
      "slug": "user-auth",
      "title": "ユーザー認証機能",
      "status": "READY_FOR_RIKU",
      "assigned_to": "Riku",
      "created_at": "2026-04-13",
      "updated_at": "2026-04-16",
      "notes": "依存: api-design",
      "events": [
        {"ts": "...", "agent": "Alex", "action": "done", "msg": "..."},
        {"ts": "...", "agent": "Riku", "action": "start", "msg": "..."}
      ],
      "retry_count": 0,
      "qa_result": null,
      "summary": ""
    }
  ]
}
```

### 3.2 ステータス機械

```
TODO
  ↓ (Yuki がタスク分解)
READY_FOR_ALEX  → READY_FOR_MINA → READY_FOR_RIKU → READY_FOR_SORA
  ↓ (担当エージェントが start)
IN_PROGRESS
  ↓ (done)                      ↓ (block)
DONE                          BLOCKED
                               ↑
                  retry_count > MAX_RETRY で自動遷移
```

QA 経路:
```
READY_FOR_SORA → IN_PROGRESS → qa APPROVED          → done → DONE
                              → qa CHANGES_REQUESTED → retry → READY_FOR_RIKU
```

### 3.3 ステータス定義表

| ステータス | 意味 | 次の遷移先 |
|---|---|---|
| `TODO` | 未着手 | `READY_FOR_*` |
| `READY_FOR_ALEX` | 設計待ち | `IN_PROGRESS` |
| `READY_FOR_MINA` | UX待ち | `IN_PROGRESS` |
| `READY_FOR_RIKU` | 実装待ち | `IN_PROGRESS` |
| `READY_FOR_SORA` | レビュー待ち | `IN_PROGRESS` |
| `IN_PROGRESS` | 作業中 | `DONE` / `BLOCKED` |
| `DONE` | 完了 | （終了状態） |
| `BLOCKED` | ブロック | 人間判断後 `READY_FOR_*` |
| `ON_HOLD` | 保留（**queue.sh では遷移できない / 手動編集または将来コマンド予定**） | 人間判断後 `READY_FOR_*` |

---

## 4. scripts/queue.sh — キュー操作ヘルパー

### 4.1 なぜ必要か

複数エージェントが直接 `_queue.json` を `Write` すると **last-writer-wins で破損**する。また書き込み中にプロセスがクラッシュすると JSON が壊れる。queue.sh はこの2つを解決する。

### 4.2 設計の核

| 仕組み | 実装 |
|---|---|
| 排他制御 | `mkdir` ベースのアトミックロック（macOS で flock が無いため） |
| 書き込み破損防止 | `mktemp + jq validate + mv` の atomic write |
| 履歴自動追記 | 全コマンドが `events[]` にエントリ追加 |
| schema 正規化 | `events[]` `retry_count` `qa_result` が無ければ自動補完 |

### 4.3 コマンド一覧

| コマンド | 用途 | 主な副作用 |
|---|---|---|
| `start <slug>` | 着手宣言 | `status=IN_PROGRESS`, events追記 |
| `done <slug> <agent> "<msg>"` | 完了 | `status=DONE`, summary設定, events追記 |
| `handoff <slug> <next-agent>` | 次担当へ解放 | `status=READY_FOR_<AGENT>`, events追記 |
| `qa <slug> APPROVED\|CHANGES_REQUESTED "<msg>"` | QA判定記録 | `qa_result=...`, events追記（status は変えない） |
| `retry <slug>` | 差し戻し | `retry_count++`, `status=READY_FOR_RIKU`, 上限超過で自動 BLOCKED |
| `block <slug> <agent> "<reason>"` | ブロック宣言 | `status=BLOCKED`, events追記 |
| `show [<slug>]` | 状態表示 | （read-only） |
| `next` | 次に着手可能な READY を1件表示 | （read-only） |

### 4.4 環境変数

| 変数 | デフォルト | 用途 |
|---|---|---|
| `QUEUE_FILE` | `.claude/_queue.json` | キューファイルパス |
| `QUEUE_LOCK` | `.claude/.queue.lock` | ロックディレクトリ |
| `MAX_RETRY` | `3` | リトライ上限（超過で自動BLOCK） |

### 4.5 終了コード

| code | 意味 |
|---|---|
| 0 | 成功 |
| 2 | ロック取得失敗（5秒超） |
| 3 | キューファイル無し |
| 4 | キューJSONが不正 |
| 5 | 生成JSONが不正（書き込み中止） |
| 6 | 指定 slug 無し |
| 7 | qa の result 引数不正 |
| 8 | retry 上限超過で BLOCKED |

---

## 5. SubagentStop フック

### 5.1 ファイル: `.claude/hooks/subagent_stop.sh`

サブエージェント完了時に Claude Code が自動実行する。次に何をすべきかを **STDOUT へ出す + Slack 通知** が役割。状態を変更しない（read-only）。

### 5.2 優先順位ロジック

```
1. BLOCKED があるか？  → あれば最優先でアラート、exit
2. READY_FOR_* があるか？ → あれば最初の1件を提案、exit
3. 全タスク DONE かつ QA対象（`assigned_to == "Sora"` のタスク）すべて qa_result=APPROVED か？
                        → スプリント完了宣言、exit
4. それ以外          → 何もせず exit
```

### 5.3 出力例

**BLOCKED 時:**
```
🚧 BLOCKED タスクがあります
  - demo-task: retry limit exceeded (max=3)
オーナー（人間）の判断が必要です。
```

**READY 時:**
```
🔔 YUKI: 次のステップの提案
タスク: 実装する (b)
次の担当: riku
実行するには以下をコピーしてください:
  Use the riku agent on "b"
```

**完了時:**
```
🎉 sprint-01 完了
全タスク DONE、QA判定すべて APPROVED です。
```

### 5.4 Slack 通知

`SLACK_WEBHOOK_URL` 環境変数が設定されている場合のみ curl で投稿する。未設定なら静かにスキップ。タイムアウト 3秒、connect 2秒で個人開発の応答性を確保。

> セキュリティ: Webhook URL は `~/.zshrc` などローカル環境変数に置き、リポジトリには絶対コミットしない。`.gitignore` に `.claude/settings.local.json` を入れている理由もこれ。

### 5.5 エラー時の挙動

- `jq` が無い: `WARN: jq not found, subagent_stop hook is degraded` を stderr に出して `exit 0`（パイプライン自体は止めない）
- `_queue.json` が無い: 静かに `exit 0`
- Slack 投稿失敗: 無視（タイムアウトで自動回復）

---

## 6. リトライループと Quality Gate

### 6.1 リトライループ

```
Riku 実装 → Sora レビュー
            ├─ APPROVED              → done → 次へ
            └─ CHANGES_REQUESTED     → retry → READY_FOR_RIKU （retry_count + 1）
                                              ↓
                                       MAX_RETRY 超過
                                              ↓
                                            BLOCKED （人間判断）
```

### 6.2 Quality Gate（スプリント完了判定）

スプリントが完了とみなされる条件は **両方** 必要:

1. 全タスクの `status == "DONE"`
2. QA対象タスク（`assigned_to == "Sora"`）の `qa_result == "APPROVED"`

これにより「DONE になっているのに QA が CHANGES_REQUESTED で止まっている」状態を防ぐ。

> 注: 現状 `retry` は `READY_FOR_RIKU` 固定で戻る（Go 実装エンジニアを唯一の実装担当と仮定）。将来 Vue/Next など他スタックを足したら「直前の実装担当」へ戻す形に拡張予定。

---

## 6.3 QA モード（qa_mode）

タスクごとに QA タイミングを制御するフィールド。Yuki がタスク分解時に設定する。

> 注: 本セクションは仕様定義です。`scripts/queue.sh` での `qa_mode` フィールドの自動判定は未実装であり、現状は Yuki がタスク分解時に手動で適用します。

| 値 | 意味 |
|---|---|
| `inline` | 実装直後に Sora のレビュータスクを挟む（デフォルト） |
| `end_of_sprint` | スプリント末にまとめてレビュー |
| `null`（未設定） | `inline` と同じ扱い（安全側倒し） |

判断基準: リスクの高い変更（API追加・DB変更・認証・外部連携）は `inline`、低リスク（README修正・設定値調整・テスト追加のみ）は `end_of_sprint`。迷ったら `inline`。

---

## 7. 環境チェック（preflight）

### 7.1 目的

Riku/Sora が `go` などの必須ツール無しで「動いたフリ」をするのを防ぐ。**サイレントフォールバック禁止**。

### 7.2 動作

作業開始時:

```bash
command -v go >/dev/null 2>&1 || {
  echo "BLOCKED: missing tool: go"
  exit 1
}
```

不足時は `BLOCKED` に遷移し、notes へ詳細を記録する。Yuki / hook が拾ってオーナーへ通知。

---

## 8. ビルドシステム（build.sh）

### 8.1 何をするか

`overlays/` と `vendor/agency-agents/` から各エージェント定義を合成して `agents/*.md` を作り、`.claude/agents/` へデプロイする。

### 8.2 合成パターン

| エージェント | レシピ |
|---|---|
| Alex | `architect.header.md` + vendor `engineering-software-architect.md`（frontmatter剥ぎ） + `architect.footer.md` + `_queue_protocol.md` |
| Sora | 既存 `qa.md` に `_queue_protocol.md` + `_preflight.md` を追記 |
| Riku | 既存 `engineer-go.md` に `_queue_protocol.md` + `_preflight.md` を追記 |
| Yuki | 既存 `pm.md` に `_queue_protocol.md` を追記 |
| Mina | 既存 `ux-designer.md` に `_queue_protocol.md` を追記 |

> 補足: `_preflight.md` は **Riku / Sora のみ** 追記される（環境依存ツールを使うため）。Alex/Mina/Yuki には付かない。
> 補足2: vendor 合成は現状 Alex のみで、他エージェントは `build_agent` が header 不在で SKIP し、`append_queue_protocol_to_native` で native 経路に流れる。

### 8.3 冪等性

`build.sh` は何回実行しても同じ出力に収束する（idempotent）。実装は「マーカー行以降を awk で剥がす → 末尾の空行と `---` を掃除 → 再追記」のパターン。

検証済み: 2回実行して `md5` ハッシュが完全一致。

---

## 9. 運用モード

### 9.1 confirm モード（デフォルト）

各エージェント完了 → hook が次担当を提示 → ユーザーがコピペ承認 → 次エージェント実行。安全。各ステップで止まれる。

### 9.2 auto モード

トップレベル Claude Code に「パイプラインを進めて」と指示すれば、Claude が `_queue.json` を読んで READY 状態のタスクを自動的に次エージェントへ委譲する。

**停止条件:**
- `BLOCKED` への遷移
- `MAX_RETRY` 超過
- Quality Gate 達成（完了）

---

## 10. ディレクトリ構成

```
agent-crew/
├── agents/                  # エージェント定義（ビルド済み）
│   ├── pm.md
│   ├── architect.md
│   ├── ux-designer.md
│   ├── engineer-go.md
│   ├── qa.md
│   └── doc-reviewer.md
├── overlays/                # ビルドの素材
│   ├── _queue_protocol.md   # 全エージェント共通
│   ├── _preflight.md        # Riku/Sora 共通
│   ├── architect.header.md
│   └── architect.footer.md
├── vendor/agency-agents/    # git submodule
├── scripts/
│   └── queue.sh             # キュー操作ヘルパー
├── .claude/
│   ├── agents/              # build.sh のデプロイ先
│   ├── hooks/
│   │   └── subagent_stop.sh
│   └── _queue.json          # スプリント状態
├── docs/
│   ├── adr/
│   ├── design/
│   ├── ux/
│   └── spec/                # 本書の置き場所
├── build.sh
├── install.sh
└── README.md
```

---

## 11. 用語集

| 用語 | 意味 |
|---|---|
| **スプリント** | 1つの `_queue.json` がカバーする作業単位。`sprint` フィールドで識別 |
| **slug** | タスクの一意識別子。kebab-case 推奨 |
| **handoff** | 次の担当エージェントへの権限委譲（状態を `READY_FOR_*` に） |
| **Quality Gate** | スプリント完了の判定基準（DONE + APPROVED） |
| **冪等（idempotent）** | 何回実行しても同じ結果になる性質 |
| **preflight** | 作業開始前の環境チェック |
| **vendor** | 外部リポジトリ（`vendor/agency-agents/`）から取り込む素材。git submodule で管理 |
| **overlay** | vendor 素材に被せる agent-crew 独自の追記レイヤ（`overlays/` 配下） |

---

## 12. 既知の制約・将来検討

| 項目 | 現状 | 将来案 |
|---|---|---|
| 並列実行 | 禁止（直列のみ） | queue.sh のロックで並列も可だが、未検証のため当面は直列 |
| QAタイミング | `qa_mode` 仕様策定済み（§6.3）、Yuki が手動適用 | queue.sh での自動判定 |
| 複数スタック | Go のみ実装済み | Vue / Next 等は overlay 追加で対応予定 |
| Antigravity サポート | エージェント定義のみ | hook 未対応のため自動化は不可 |
| マルチプロジェクト | 1ワークツリー前提 | スコープ外 |
| キューアーカイブ | スプリント完了後も `_queue.json` を上書き | スプリント終了時に `docs/sprints/<sprint>.json` へコピーして履歴保全 |
| キュー履歴のバックアップ | `.claude/_queue.json` は `.gitignore` 対象 | コミットしない代わりに上記アーカイブで担保 |

---

## 13. 参考リンク

- 元ネタ: [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents)
- Claude Code Sub-agent docs: <https://docs.claude.com/claude-code>
- 本リポジトリ README: `../../README.md`
