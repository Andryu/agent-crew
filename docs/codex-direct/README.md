# Codex直接利用ガイド

## 現行の指示とagent

常設の共通契約はrepo rootの[AGENTS.md](../../AGENTS.md)、複雑な開発の工程ガイドは[fable-class](../../.agents/skills/fable-class/SKILL.md)を参照する。通常はメインが調査・設計・実装・関連テストを進める。特定モデルやHerdrへの委譲を必須としない。独立レビューが必要な変更では、`.codex/agents/direct-reviewer.toml`を使用し、仕様準拠と品質を別々の新規コンテキストで確認する。

旧17 agent定義は[hash台帳付き退避先](legacy-agents/manifest.json)へ移動した。Codexの自動発見範囲には`direct-reviewer`だけを残す。Claude側のagent定義は変更していない。以下は2026-09-20の適用・調査時点の記録であり、現在の起動設定やagent件数を示すものではない。

2026-09-20、オーナー承認後に**3点を適用済み**。切替計画と有効化記録は非公開の過去資料で、この公開cloneには含めない。このディレクトリは自動読込位置ではなく、`.candidate` は適用した版の控えである。

## 現在の起動方法

```bash
cd "$(git rev-parse --show-toplevel)"
codex --disable hooks
```

ユーザー共通の `~/.codex/hooks.json` に通知・Vault処理等が残っているため、直接利用の初回構成ではこの起動オプションを使う。repoのhookを空にするだけでは共通hookは止まらない。これは全レイヤーのhookをその起動だけ無効化する公式機能であり、ユーザー設定やtrust情報を書き換えない。[Hooks: Turn hooks off](https://learn.chatgpt.com/docs/hooks#turn-hooks-off)

`codex --disable hooks features list` で `hooks stable false` を確認済み。外部通知・Vault自動処理を個別承認・検証するまでは、オプションなしの起動を受入済みと扱わない。以下の「確認したこと」「既存設定との差分」は適用前の調査記録。

## 確認したこと

| 対象 | 確認結果 | 残る確認 |
|---|---|---|
| CLI | `codex-cli 0.154.0`、`exec --help`に`--ephemeral`、`--ignore-user-config`、`--strict-config`あり | 新規CLIの認証とモデル応答 |
| AGENTS.md | ルートには未配置。旧stageに共通契約候補あり | 新規セッションで実際に読み込む規約 |
| agents | 当時`.codex/agents/`に旧17 TOMLが存在。現在は退避済み | 実務では`direct-reviewer`を使用 |
| skills | `.agents/skills/` に6件。このセッションの利用可能スキル一覧にも提示されている | 個々の実務フロー。名前重複やClaude固有の委譲手順が残る |
| hooks | `.codex/hooks.json` に7イベント・15 command handler | 各handlerのCodexでの入力/終了制御、現在の全レイヤーのtrust |
| queue | 実体は `.claude/_queue.json`、操作入口は `scripts/queue.sh` → `queue.py` | 実台帳の更新は今回行わない |

公式仕様はプロジェクトの `.codex/agents/*.toml` をサポートし、必須項目は `name`、`description`、`developer_instructions`。モデルを省略すると親や既定の設定を継承するため、今回の候補ではモデルを固定しない。[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)

repo skillの読込位置はcwdからrepo rootまでの `.agents/skills`。ファイルの存在とフローの検証成功は別に扱う。[Build skills](https://learn.chatgpt.com/docs/build-skills)

project hookにはproject trustとhook定義のtrustが関係する。`/hooks`で定義元を確認する。空のrepo hookはユーザー・システム・pluginのhookを消さない。[Hooks](https://learn.chatgpt.com/docs/hooks)

AGENTS.mdは作業ディレクトリまでの階層や上位の規約と併せて読むため、この候補だけが唯一の指示になるとは限らない。[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

## 既存設定との差分

- 既存hook: `CLAUDE_PROJECT_DIR`依存のdashboard送信6件、絶対パスのsubagent_stop呼出し2件。subagent_stopは条件付きSlack POSTとスプリント完了時のVault転記を行う。`task_completed.sh`はsignalに書くが現行hooks.jsonには未登録。
- 旧stage hook: 通知を取り除いてもClaudeのsession_start/model-mode、Stopの`|| true`が残る。コマンドの成功は品質ゲートが強制された証拠にならない。そのまま移植しない。
- 旧agent: `.Codex/_queue.json`等の大文字パス参照があったため、hashを保持して自動発見範囲から退避した。現在はdirect-reviewerとメインの直接実装を基本にする。
- skill: Codex側fable-classはP2で改訂し、モデル名依存のroutingと一律委譲を解除した。

## 承認対象（3ファイル）

| 候補 | 適用先 | 変更 |
|---|---|---|
| `AGENTS.md.candidate` | repo rootの`AGENTS.md` | 新規。直接実装、品質工程、queue、再開メモの契約 |
| `hooks.json.candidate` | `.codex/hooks.json` | 既存定義をバックアップ後、repo hookを空にする |
| `direct-reviewer.toml.candidate` | `.codex/agents/direct-reviewer.toml` | 新規。独立レビューのみ、queue更新なし |

既存の17 agent、6 skill、Claude環境は編集しない。新しいproject configやモデル指定も追加しない。初回に保証するのは**手動の工程**であり、Stopによる完了阻止や通知の自動化はない。

適用前に対象3ファイルの現在の存在・ハッシュを再確認する。既存hooks.jsonは日時付きの退避先（`.codex/`の外）へ内容を保存し、ハッシュ一致を確認する。既存ファイルが変わっていたり、新規対象が既に存在した場合は上書きせず差分を再提示する。承認後だけ候補を配置する。戻す場合は自分が適用した版とのハッシュ一致を確認してからhooksを復元し、新規2ファイルを退避する。他セッションの後続変更があれば自動復元しない。

## 承認後の新規セッション確認

1. 起動前にユーザー・システム・pluginの有効hookを点検する。`--ignore-user-config`は資格情報や全hookの隔離ではない。現在のtrust状態が不明なら通常のrepo起動を安全確認の代わりに使わない。trust bypassは使わない。
2. repo rootで新規Codexを起動し、`/status`でモデルと権限、`/hooks`で全定義元、`/skills`で一覧を確認する。認証はCLIの状態表示で確認し、authファイルは開かない。
3. 「読み込んだ共通契約のパス、queue正本、通常の実装担当、独立レビューの条件を挙げて」と依頼。候補どおりかを確認する。
4. direct-reviewerを明示して小さな差分をレビューさせる。存在するだけでは読込成功としない。子の実効権限とモデルを確認する。読み取り専用sandboxでもMCPの外部書込み禁止の代わりにはならない。
5. 小さな修正を依頼→編集→関連テスト→独立レビュー→再開メモまで通す。まず一時queueを使い、実台帳は対象タスクと副作用を確認してから操作する。

再開依頼例:

> docs/codex-direct/README.mdの候補を承認した範囲で適用し、新規セッションの読込を確認してください。小さな実務を直接実装し、direct-reviewerで独立レビューしてください。外部通知・Vault・commit/pushは含めません。

## queue運用と検証

repo rootで`bash scripts/queue.sh show`によりタスクを確認する。cwdが異なるときは入口と`QUEUE_FILE`を絶対パスで指定する。queueのJSONを直接編集しない。

SessionStartのqueue要約は起動時のsnapshot。着手・完了時は`bash scripts/queue.sh show`で現値を確認する。Stopは毎回現値を検査する。通常のStopではprivacy/lesson検査を自動実行しない。公開前や対象変更時に`bash scripts/privacy-check.sh --summary`を明示実行し、教訓候補が必要な節目では`bash scripts/lessons.sh list-rule-candidates --min-priority 4`で確認する。

既存タスクは`start`で着手する。独立レビュー結果はメインが`qa`で記録し、QA対象は`APPROVED`を確認してから`done`にする。`qa`の台帳名義は実装上Soraになるため、summaryに実際のレビュアー名、対象差分の識別情報、判定、証跡パスを残す。direct-reviewerの判定をSoraの実行結果と混同しない。担当taskの終了確認には`scripts/crew --task <slug> claude|codex`を使用し、repoとtaskのscopeをその起動に限定する。Stopは一度だけ継続を求め、再入時は未完了の警告を残す。

`done`は`close_issue`が設定されていると`gh issue close --comment`を実行する。実タスクを完了させる前にその設定と外部操作の承認範囲を確認する。`qa_mode=inline/end_of_sprint`の未判定doneは拒否されるが、`CHANGES_REQUESTED`を包括的に拒否する実装ではない。工程では必ず`qa_result == APPROVED`を確認する。`--skip-qa-guard`を通常の完了手順に含めない。

隔離スモーク:

```bash
python3 -m unittest discover -s tests -p test_codex_direct_queue.py -v
```

Python 3.12+と既存queue.pyの依存（typer/pydantic）が必要。テストは一時ディレクトリ・限定環境変数で実入口を呼ぶ。実台帳、hook、Codex新規セッションは実行しない。これはqueueの接続確認であり、全Codex機能のE2E成功を意味しない。

この実機では通常の`python3`で起動した子プロセスがtyperを読めなかったため、既存uvキャッシュのアクセス承認を受け、次のオフライン環境で3件成功した。

```bash
uv --offline run --no-project --with pytest --with typer --with pydantic --python 3.12 python -m unittest discover -s tests -p test_codex_direct_queue.py -v
```
