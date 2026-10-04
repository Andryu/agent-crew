# Phase1 Step4 パイロット — PR #191への追加

mode: pro（session hook: team-lead=gpt-6-astra effort=high）
complexity: S / risk_level: low

## SPEC

doc-reviewer（Hana、読み取り中心）と engineer-go（Riku、実装）の再利用手順を、Codex が発見できる2スキルとして追加する。既存の役割定義、設定、他のペルソナは変更・削除しない。軽い質問を新規 codex exec セッションで実行し、一覧への登録・本文の読み取り・回答への反映をログで区別して確かめる。指定ブランチへコミット・pushする。

前提: スキルは必要時に読む作業指示であり、人格の自動注入、system promptへの昇格、ツール権限の強制、別コンテキストの生成を意味しない。
テーゼ: 作業判断を再利用し、起動・権限・運用状態をハーネスのアダプターに残す。

## PLAN・ミニADR

背景: PR #190で問題になった優先度の誤説明とハーネス固有本文の混入を避ける。
採用: 自己完結した2つのSKILL.mdと本記録を追加。人格正本の新設は今回は見送る。既存アダプターを変更できないため、新たな正本を宣言すると実際の参照関係と食い違う。
代替: 2つの共有人格正本とスキル参照を追加する案は、ファイル・参照管理が増え、Claude側から参照できない暫定重複が増えるため不採用。

| 5層 | 今回の仕分け |
|---|---|
| AGENTS.md | 言語、Gitを根拠にすること、変更・検証・スコープ等は既存の共通規約に任せ、変更しない |
| .agents/skills/ | Hanaの観点・判定・指摘形式、RikuのGo/Vue3規約・実装/検証手順を抽出 |
| .codex/agents/*.toml | 別コンテキストや権限等の役割設定。今回の変更・監査対象外 |
| .claude/agents/*.md | tools/model、呼び出し記法、キュー更新、ハーネス固有の履歴ルールを保持、変更しない |
| 共有人格・責務の正本 | 今回は新設しない。名前・経歴・人格の宣言は既存定義に保持。共有参照の接続は後続工程 |

迷った点:
- 読み取り専用はHanaの作業上の約束として残すが、スキル単独の権限制御とは呼ばない。
- Rikuの3ファイル・200行・2,000トークン制限は旧環境の無応答対策。固定値を移植せず、必要部分の検索・読み取りと、合意した範囲を超える場合の分割相談へ一般化する。
- feature-spec更新は再利用するが、Go/Vueの既存機能に適用する。手順の質問だけでファイル作成を始めない。
- 過去lessonのキュー/フック固有手順は転載せず、要件照合・実測による検証という判断を抽出する。

作業順序（各S/low、直列）:
1. このSPEC/PLANを確定する。
2. `/Users/ando_shunsuke/orca/workspaces/agent-crew/dual-harness-foundation/.agents/skills/doc-reviewer/SKILL.md` と同 `engineer-go/SKILL.md` を作成する。frontmatterはname/descriptionのみ、本文にハーネス固有の記法を含めない。
3. quick_validate.pyとcodex execによる質問を各1回実行する。ログの該当箇所と結果を本ファイルに追記する。
4. 別コンテキストで仕様・品質を分けて確認し、対象ファイルだけコミット・pushする。

本セッション自体がユーザーから任されたCodex実装担当であり、herdrへの追加移送は行わない。新規セッションによる動作検証を行う。criticはlowのため不要。

## DoD

- frontmatter検証2件合格。新規スキルへのClaude固有記法の混入なし。
- 2セッションでskills_instructionsへの列挙とスキル本文を反映した回答を確認し、ログパス・行番号を記録。
- 既存ファイル変更・削除なし。選定した2役以外に変更なし（本計画・検証記録を除く）。
- コミットメッセージに「PR #191への追加、Phase1 Step4パイロット」を含め、指定ブランチへpush。

## 検証記録

着手時: `git status --short` は出力なし。`git branch --show-current` は `Andryu/dual-harness-foundation`。HEADは `9d3da93`。`codex --version` は `codex-cli 0.154.0`。
`rg --files` により既存スキルは `.agents/skills/dual-harness/SKILL.md`、関連する既存テストは `tests/test_codex_hooks.py` を確認。今回フックや実行コードは変更しないため、スキルの構造と実際の発見・適用を検証する。


### 構造・スコープ

```text
$ python3 /Users/ando_shunsuke/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/doc-reviewer
Skill is valid!
(exit 0)
$ python3 /Users/ando_shunsuke/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/engineer-go
Skill is valid!
(exit 0)
$ rg -n 'Agent|fable-class|\.claude/|queue\.sh|Read|Grep|Glob|sonnet' .agents/skills/doc-reviewer .agents/skills/engineer-go
(出力なし、exit 1 = 一致なし)
$ git status --short
?? .agents/skills/doc-reviewer/
?? .agents/skills/engineer-go/
?? docs/plans/2026-09-12-phase1-step4-pilot.md
```

Goの `context.Context` 第一引数という規約は「受け取る場合」に限定した。原文の自己チェックを字義通りに適用して全関数へ不要なcontext引数を追加することを避けるための明示的な一般化であり、原文の完全コピーではない。

### 実セッションの発見・読み取り・回答

実行日は2026-09-12（Asia/Tokyo）。通常のユーザー設定・プロジェクト設定で実行し、スキル本文や期待する回答をプロンプトへ埋め込んでいない。初回は外側sandboxによる `failed to initialize in-process app-server client: Operation not permitted (os error 1)` でexit 1。承認を得て外側sandboxの制限を解除し、子Codexは `--sandbox read-only` のまま再実行した。両方exit 0、イベント末尾 `turn.completed`。

公式の[Build skills](https://learn.chatgpt.com/docs/build-skills)も参照したが、この環境の発見名・メッセージrole・動作の根拠は以下の実測ログとする。

#### doc-reviewer

```sh
codex exec --sandbox read-only --json -o /tmp/phase1-step4-doc-answer.txt '日本語ドキュメントをレビューするとき、このリポジトリではどんな順序・判定基準・報告形式で進めますか。利用できるスキルを確認して回答してください。今回は手順の質問だけです。ファイル編集、キュー更新、追加エージェントの起動はしないでください。' > /tmp/phase1-step4-doc-events.jsonl 2> /tmp/phase1-step4-doc-stderr.txt
```

- セッションログ: `/Users/ando_shunsuke/.codex/sessions/2026/09/12/rollout-2026-09-12T16-26-44-01a09482-ef52-7440-a98e-73ecd4d2a4f1.jsonl`
- JSONL 3行目: `payload.role=developer` の `<skills_instructions>` に `agent-crew:doc-reviewer` を列挙。パスは `r8/doc-reviewer/SKILL.md`（同メッセージのr8はこのリポジトリの `.agents/skills`）。
- 15行目: SKILL.mdを読むツール呼び出し。18行目: 本文を返すツール結果。21行目: 最終回答。
- イベントログ: `/tmp/phase1-step4-doc-events.jsonl`、回答全文: `/tmp/phase1-step4-doc-answer.txt`。

最終回答の生出力抜粋:

```text
2. **正確性**：根拠となるコード・スクリプト・設定を実際に読みます。参照できない記述は「未検証」とし、一致を推測しません。
- MUSTが1件でもあれば `CHANGES_REQUESTED`、なければ `APPROVED`。
- 正確性など重要事項が曖昧で承認できない場合は、未確認事項と解消方法をMUSTに記載します。
- [問題] @ [ファイル・見出しまたは行] → [修正案]
```

#### engineer-go

```sh
codex exec --sandbox read-only --json -o /tmp/phase1-step4-go-answer.txt 'このリポジトリでGoとVue3の機能を実装するとき、どんな実装規約・テスト方針・完了条件で進めますか。利用できるスキルを確認して回答してください。今回は手順の質問だけです。ファイル編集、キュー更新、追加エージェントの起動はしないでください。' > /tmp/phase1-step4-go-events.jsonl 2> /tmp/phase1-step4-go-stderr.txt
```

- セッションログ: `/Users/ando_shunsuke/.codex/sessions/2026/09/12/rollout-2026-09-12T16-27-18-01a09483-7681-7d72-8862-d0f239d99009.jsonl`
- JSONL 3行目: `payload.role=developer` の `<skills_instructions>` に `agent-crew:engineer-go` を列挙。パスは `r8/engineer-go/SKILL.md`（同メッセージのr8はこのリポジトリの `.agents/skills`）。
- 15行目: SKILL.mdを読むツール呼び出し。19行目: 本文を返すツール結果。28行目: 最終回答。
- イベントログ: `/tmp/phase1-step4-go-events.jsonl`、回答全文: `/tmp/phase1-step4-go-answer.txt`。

最終回答の生出力抜粋:

```text
- Goは `internal/` を基本とし、公開が必要なものだけ `pkg/` に配置。エラーは `%w` で原因と文脈を保持し、`context.Context` は第一引数にします。インターフェースは利用側で定義し、外部依存を差し替え可能にします。goroutineには終了責任を持たせます。
- Goはテーブルドリブンテストを基本とし、外部依存はインターフェース経由でモック化。カバレッジ数値より境界値・エラーパスを優先します。
- 自己確認と独立レビューを区別し、仕様準拠と品質を別々に確認します。現在の工程規約ではfresh Sonnetによるレビュー、risk highではcriticが必要です。
- 完了報告には、変更ファイル・変更内容、**検証コマンドと生出力**、仕様・設計からの逸脱、未解決事項、次のレビュアーへの確認点を含めます。
```

一覧はこの実行環境ではdeveloperメッセージに含まれるが、スキル本文はツールによるファイル読み取り結果である。これをsystem prompt注入・権限昇格・独立エージェント化とは解釈しない。

Go側は追加で既存の工程規約と補助スキルも読んでおり、回答にfable-class等への言及がある。新SKILL.mdへの混入とは別で、統合環境での発見・適用を確認した結果である。各1回の手順質問であり、実装能力・自動選択の安定性・書き込み拒否の強制力までは未検証。

### 後続9役への見通し

手順、人格、起動設定、共通契約、ハーネス固有運用を区別する方式は展開可能と判断する。ただし今回、他役の本文監査は行っていない。共有人格正本と各アダプターを実際に接続する仕組み、抽出後の原文との二重管理、同名スキルと役割の選択競合、PM等の状態更新・権限・外部副作用は個別検証が必要。旧コンテキスト上限や蓄積lessonは機械コピーせず、成立条件ごとに見直す。


### 独立レビュー・工程上の差異

このセッションで提供されているサブエージェントモデルにはSonnetがないため、別コンテキストのCodexレビュアーを使用した（fresh Sonnetという既存ルーティングからの差異）。仕様準拠と品質は別セッションに分離。実装前の仕様ドライランは未実施であり、実装後の仕様レビューで代替した。これらはユーザーの受入仕様の変更ではなく、工程上の差異として残す。

仕様準拠: `/root/pilot_spec_review` の生出力:

```text
APPROVED — 仕様上の欠落・違反はありません。

- 2スキルのfrontmatterは `name` / `description` のみ。
- 元定義の再利用可能な手順・判断基準を抽出し、Claude固有の呼び出し・キュー・スキル参照は混入していません。
- 5層の責務分離と、スキルがsystem prompt注入・権限強制ではない点を正しく説明しています。
- `git status --short` は対象の新規3項目のみ。既存定義・他役の変更はありません。

必須修正・推奨修正・任意指摘：なし。
```


品質: `/root/pilot_quality_review` の生出力:

```text
APPROVED — 品質上の修正事項はありません。

- 発火条件と対象外が明示され、手順の質問から編集・状態更新を開始する指示はありません。
- 再利用手順とハーネス固有の権限・起動設定を区別できています。
- 計画記載のログ行番号、developerメッセージへの列挙、本文の読み取り、回答抜粋、`turn.completed` を実ログで確認しました。
- 現在の2スキル本文は、検証セッションが読んだ本文と完全一致しました。
- Go回答への既存工程規約の混入と検証範囲の限界も正確に記録されています。
- `git status --short` は対象の追加3件のみでした。

編集・追加エージェント起動は行っていません。
```

指摘採否: 両レビューとも指摘なし。ユーザーの受入仕様からの逸脱なし。既存工程からの差異は上記に明記した。

最終スコープ検証:

```text
$ git diff --exit-code -- .claude/agents .codex AGENTS.md
(出力なし、exit 0)
$ git diff --cached --check
(出力なし、exit 0)
```

新規3ファイルのみを明示してステージした。Git indexがworkspace外のため、初回は `index.lock: Operation not permitted`（exit 128）となり、承認後に同じ対象で成功（exit 0）。ファイル削除・既存役割定義の変更はない。
