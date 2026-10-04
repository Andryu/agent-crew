# bench — 個人ベンチ（ものさし）

agent-crew の実 PR を題材に、「あるハーネス／モデル／スキル構成がどれだけ解けるか」を
定点観測するための個人ベンチマーク。各タスクは squash merge された PR の
**マージコミットの親**（= 着手時点）のスナップショットから始まり、holdout テストの
振る舞いだけで採点する。

## 構成

```
bench/
├── README.md          # 本ファイル（実行手順・採点式・設計方針）
├── run_task.sh        # 1タスク実行: setup → prompt 表示 → (解く) → score
├── score.py           # holdout を pytest/bash で実行し rubric.yaml で部分点集計
├── lib/
│   ├── common.sh      # setup.sh 共通ヘルパー（スナップショット展開）
│   └── testlib.sh     # テスト共通ヘルパー（乱数注入・PATH制限・fail）
└── tasks/NN-<slug>/
    ├── meta.yaml      # 出典 PR・正解/親コミット（記録用。採点には使わない）
    ├── prompt.md      # 解答者に見せる課題文（setup 時に作業dirへ TASK.md としてコピー）
    ├── setup.sh       # 作業ディレクトリの準備
    ├── visible_test/  # 解答者が見てよい簡易確認（setup 時に作業dirへコピー）
    ├── holdout_test/  # 採点用テスト（解答者には見せない）
    └── rubric.yaml    # チェック一覧と配点
```

## 使い方

```bash
# 1. セットアップ + 課題文表示（作業ディレクトリ既定: /tmp/bench-work/<task>）
bench/run_task.sh bench/tasks/00-queue-done-issue-close

# 2. 作業ディレクトリで解く（手動、またはハーネスに TASK.md を渡す）

# 3. 採点
bench/run_task.sh bench/tasks/00-queue-done-issue-close --score
#   （--seed N で再現、--json result.json で結果保存、--verbose で失敗ログ表示）
```

pytest は リポジトリ直下の `.venv`（python3.12 + pytest）を自動検出する。
無い環境では `BENCH_PYTEST="python3 -m pytest"` のように指定する。
pytest をどうしても用意できない環境向けのタスクは bash ベースの holdout に倒す。

## 採点式

- 各チェック（rubric.yaml の checks 1項目）は pass で配点ぶん加点、fail で 0。
- **`regression: true` のチェックが1つでも落ちたら、そのタスクは 0 点**
  （既存機能を壊した解答に部分点を与えない）。
- タスクスコア = 獲得点 / 満点。ベンチ全体はタスクスコアの単純平均で見る。

## 設計ルール

1. **採点は holdout の振る舞いのみ**で行う（exit code・生成物・JSON のキー/値）。
   正解 PR の diff・関数名・出力文言には依存しない。文言チェックが必要な場合は
   prompt.md で仕様として明示したキー/ファイル名に限る。
2. **setup.sh は該当親 SHA を fetch → checkout → `.git` 削除 → `git init` +
   initial commit** する。git 操作を前提とするタスクがあるため、履歴1件の
   新規リポジトリから始める。clone に `--single-branch` は使わない
   （対象 SHA が取得できず setup が壊れた #153 対策の前例）。
3. **回帰テスト（既存機能の非破壊）を各タスクに1項目**入れる。
   落ちたらそのタスクは 0 点（rubric.yaml の `regression: true`）。
4. **ランダム値注入**: ハーネス実行ごとに `BENCH_SEED` を乱数生成し、
   fixture の値（Issue 番号・slug・しきい値・パス接頭辞など）はシードから
   テスト内で生成する。期待値もテスト側で独立に計算し、値の丸暗記や
   ハードコードでは通らないようにする（`--seed` 指定で再現可能）。
5. **prompt.md は PR 本文から実装手段・ファイル一覧・Test Plan を削り**、
   受け入れ基準を振る舞いの言葉で 3〜6 行にまとめる。Claude 由来の語彙
   （冪等・非ブロッキング等）は平易な日本語に言い換える。
6. **秘密情報・実トークンは fixture に置かない**。実ユーザーのパス
   `/Users/andryu/` は `benchuser` に置換する。
7. **「〜しない」系チェックには機能存在の前提確認を入れる**。未実装の解答が
   ネガティブチェック（gh を呼ばない・不正値を拒否する等）だけを空虚に通して
   部分点を稼ぐのを防ぐため、ネガティブチェックは冒頭で正常系が動くことを
   確認してから本題を検証する。

## rubric.yaml の書式

PyYAML に依存しない限定サブセット（行頭コメントのみ可・ネスト不可）:

```yaml
checks:
  - id: some_check
    type: bash            # bash | pytest
    file: holdout_test/test_00.sh
    node: test_name       # pytest のみ
    points: 1             # 省略時 1
    regression: true      # 省略時 false
    optional: true        # 省略時 false。加点項目。pytest が skip した場合
                          # （依存ライブラリ不在等）は分母からも除外される
```

テストスクリプト/pytest が受け取る環境変数:

| 変数 | 内容 |
|---|---|
| `BENCH_WORK_DIR` | 解答済み作業ディレクトリ |
| `BENCH_TASK_DIR` | タスクディレクトリ（fixture 参照用） |
| `BENCH_SEED` | 乱数シード（整数） |
| `BENCH_TMP` | チェックごとの空の一時ディレクトリ |

## タスク一覧

| # | slug | 出典 PR | 題材 |
|---|---|---|---|
| 00 | queue-done-issue-close | #8 | スモーク: queue.sh done の Issue 自動クローズ（+12行） |
| 01 | token-dept-order | #170 | 部門トークン会計の分類順序バグ |
| 03 | task-completed-hook | #98 | TaskCompleted フックの新規作成 |
| 05 | lessons-set-status | #74 | lessons.sh の status フィールドと set-status |
| 07 | lessons-to-vault | #123 | 教訓の vault 自動転記スクリプト |
| 10 | subagent-tokens | #179 | サブエージェント別トークン集計（難問。server 検証は加点） |
| 12 | rule-candidates | #182 | 抽出条件の一元化と信頼境界（難問） |

## 残タスク（未構築）

選定レポートで候補に挙がった 02 / 04 / 06 / 08 / 09 は未構築。
11（PR #153）は親コミットが main の履歴外にあるため対象外とした。
追加する際は既存タスクの構成（meta.yaml / prompt.md / setup.sh / visible_test /
holdout_test / rubric.yaml）に合わせ、**holdout を正解実装（マージコミットの
該当ファイル）に対して実行し全チェックが通ることを確認**してから追加すること。
グリーンでない holdout は採点器として無効。

## 品質チェック（減点方式・2026-08-19 実装）

laiso の実測（2026-07-18, https://blog.lai.so/kimi-k3/）で、Kimi K3 は ReactBench の
全課題でテスト合格したが**静的解析（React Doctor）では全て不合格**。Opus 4.8 は両方合格。
「テストが通る」と「コード品質が保たれる」は乖離し、**安いモデルほど乖離が大きい**。

holdout は振る舞い（exit code・生成物・戻り値）のみを見るため、この乖離を検出できない。
そこで `bench/quality/check.sh <workdir> [task-dir]` を用意した（減点方式）:

- **Bash**: 変更した `.sh` に `shellcheck -S warning` が出たら -1/ファイル
- **Python**: 構文エラー -2、同名関数の重複定義 -1
- **過剰実装**: 追加行が `meta.yaml` の `ref_lines` の3倍超なら -1

```bash
bench/quality/check.sh /path/to/workdir bench/tasks/05-lessons-set-status
# → PENALTY 1 shellcheck: ... / QUALITY_PENALTY_TOTAL 2
```

検証済み: Opus・Codex の満点解答6件すべてで減点0（偽陽性なし）、意図的に壊したコードで
shellcheck 警告と重複定義を検出（偽陰性なし）。

注意: macOS の bash 3.2 には `mapfile` が無い。この環境で動く形に書いてある。

## 引き継ぎ（handoff）モード

使用量上限・障害・コスト最適化でハーネスを交代するとき、**会話履歴を渡さずに作業を継続**
できるかを測る。仕様は `bench/handoff/PACKET.md`、実行は `bench/run_handoff.sh`。

```bash
bench/run_handoff.sh bench/tasks/05-lessons-set-status \
  --first codex:gpt-5.6-sol --second claude:sonnet --budget-min 6
```

- 前半は「半分で止めて `docs/handoff/handoff.md` を書け」と指示され、中間スコアを記録
- 後半は**会話履歴なし**でパケットとリポジトリの現状だけを受け取り、続きを解く
- 単独実行時のスコア（レーン0/C は 54/54）との差が「引き継ぎで失った点」

ハーネスは `bench/harness/<name>.sh <workdir> <prompt-file> <model>` の統一インターフェース。
新しいハーネスは1ファイル足すだけで追加できる（claude / codex / hermes を実装済み）。

**なぜ会話を渡さないか**: 実測で入力トークンの約96%が cache_read。会話を引き継ごうとすると
その瞬間に全再送となり最も高くつく。モデルを替えればキャッシュは必ず失効する
（Anthropic は `/model` 切替でリセットと明記、Hermes の fallback も同様）。

### Hermes（ローカル）を使う準備

```bash
# 1) 64k コンテキスト版を作る（Hermes は 64k 未満を起動時に拒否。レイヤ共有で容量増は僅少）
printf 'FROM gemma4:12b\nPARAMETER num_ctx 65536\nPARAMETER temperature 0.3\n' > Modelfile.gemma4-64k
ollama create gemma4-64k -f Modelfile.gemma4-64k

# 2) ~/.hermes/config.yaml に named provider を足す（既存の model: は変えない）
#    providers:
#      local:
#        api: "http://localhost:11434/v1"
#        key_env: "OLLAMA_API_KEY"
#        transport: chat_completions
#        context_length: 65536
#    → ~/.hermes/.env に OLLAMA_API_KEY=ollama

# 3) 疎通（非対話は chat -q。--yolo で承認を出さない、--in で作業ディレクトリ指定）
hermes chat -q "..." --provider custom:local --model gemma4-64k --in "$PWD" --yolo --cli --max-turns 8
```

注意: 12B を 64k で回すと初回ロードに数分かかる。`OLLAMA_KEEP_ALIVE=30m` を推奨。
`export` はシェルからの起動時のみ有効で、Ollama.app（launchd 起動）には効かないため、
常用するなら LaunchAgent で `launchctl setenv` する。

## トラックと分割（v4.1・2026-08-22）

各タスクの `meta.yaml` に2つのフィールドを持たせる。

```yaml
track: historical   # historical(過去PR由来) | fresh(実務の新規issue由来) | adversarial(弁別用の難問)
split: dev          # train(自己改善の入力) | dev(accept/rejectの判定) | hidden(最終評価のみ)
```

| split | いつ実行するか | 用途 | ログを渡すか |
|---|---|---|---|
| `train` | ラウンドごと | 自己改善の入力（失敗分析） | 渡す |
| `dev` | ラウンドごと | **accept / reject の判定** | 渡す |
| **`hidden`** | **実験終了後に1回だけ** | **最終評価のみ** | **一切渡さない** |

### hidden は accept/reject に使わない（重要）

hidden のスコアを採否判断に使うと、**その判断を通じて hidden にも overfit する**
（採用される変更は hidden で良かった変更だけになり、hidden が第2の dev に化ける）。
したがって hidden は実験期間中は開封しない。

**事故防止の実装**:
- `lib/select.sh` の `bench_tasks split=hidden` は `--unseal` なしでは拒否する
- `run_task.sh` は `split: hidden` のタスクを `BENCH_UNSEAL_HIDDEN=1` なしでは実行しない
- `accept_change.sh`（後述）は hidden を参照しない

### タスクの選び方

```bash
export BENCH_ROOT=/path/to/bench
source "$BENCH_ROOT/lib/select.sh"
bench_tasks split=dev            # dev のタスクディレクトリ一覧
bench_tasks track=adversarial    # 弁別用の難問だけ
bench_tasks split=hidden --unseal  # 最終評価のときだけ
```

### 問題の増やし方

新規に大量作成はしない（作成コストが高く、問題は repo の変化で腐るため）。次の2経路のみ:

1. **fresh**: 実務で「30分〜2時間かかった」作業を月2問だけ切り出す。
   **配分は3問に1問を dev、残りを train**（現在の dev 7問は ceiling しているため dev も育てる）。
   **hidden は固定**（追加も差し替えもしない）
2. **adversarial**: **ベンチで満点なのに実務で失敗した事例**を問題化する。
   机上で難問を設計するより、実際に破れた場所から採る方が確実

目安は3ヶ月で 15〜20問。

## 指標（v4.1）

`metrics/record.sh` が1実行を1行 JSON で `results/metrics.jsonl` に追記し、
`metrics/summarize.py` が主要指標3つに集計する。

```bash
metrics/record.sh --lane codex --model gpt-5.6-sol --task 05-lessons-set-status \
  --score 9 --max 9 --penalty 0 --seconds 412 --log <harness-log> [--interventions 1]
python3 metrics/summarize.py
```

| 指標 | 取り方 |
|---|---|
| **$ / solved task** | ハーネスのログからトークンを抽出（Codex の `tokens used`、Claude Code の `usage` JSON）×単価 ÷ 満点タスク数 |
| **wall-clock / task** | ランナーが記録 |
| **人間の介入回数** | **手で記録する**（`--interventions N`）。自動計測しない |

`token/request` は記録するが**指標にはしない**（「同じ枠で何回回せるか」に翻訳して初めて意味を持つ）。
人間の介入「時間」を測らないのは、計測の仕組み自体が運用の重荷になるため。
介入回数が2以上のレーンは、時間を測るまでもなく「安くない」と判断できる。

## 変更の採否（accept_change.sh）

ハーネスが自分の skill / memory / prompt を書き換えたとき、その変更を採用してよいかを判定する。

```bash
accept_change.sh --harness hermes --before baseline.jsonl --after candidate.jsonl
# exit 0 = ACCEPT / exit 1 = REJECT
```

すべて満たしたら accept、1つでも欠けたら reject:

1. **dev のスコアが下がっていない**（同点は可）
2. **regression チェックがゼロ**
3. **コスト増が +20% 以内**（`--cost-tolerance` で変更可）
4. **品質減点が増えていない**

**hidden は参照しない**（`split: hidden` のレコードは自動で除外する）。
hidden を採否に使うと、その判断を通じて hidden にも overfit するため。

## ハーネスの自己変更を Git で追跡（adaptation/snapshot.sh）

Hermes / Prime / pi は skill・memory・prompt を自分で書き換える。その差分を Git に残し、
**failure → proposed change → benchmark → accept/reject** を追跡できるようにする。

```bash
adaptation/snapshot.sh hermes "round-3 proposed"
# → ~/Workspace/harness-state/ に許可リストのパスだけをコピーしてコミット
adaptation/snapshot.sh agent-crew "round-3 proposed"   # 既に Git 管理下なので SHA を記録
```

保存先は `$HARNESS_STATE_REPO`（既定 `~/Workspace/harness-state`）。

### 安全設計（重要）

`~/.hermes` を丸ごと `git init` すると **`auth.json` や `.env` まで追跡してしまう**。
そのため許可リスト方式にしてある。

| ハーネス | 追跡するパス |
|---|---|
| hermes | `skills/` `memories/` `SOUL.md` `config.yaml` |
| pi | `agent/skills/` `agent/extensions/` `agent/models.json` |
| prime | `agent/skills/` `agent/memory/` `agent/models.json` |
| agent-crew | （Git 管理下なので HEAD の SHA・ブランチ・dirty 状態だけ記録） |

さらにコミット前に秘密情報を走査し、見つかったら**コピーごと削除して中断**する。
検出はプレースホルダを除外する（`ghp_xxxxxxxx` や `YOUR_TOKEN` は誤検知しない）。
実在しうる形のトークンのみ検出することを、偽陽性・偽陰性の両方で確認済み。

### ラウンドの型

```
failure（train/dev の失敗ログ）
  → proposed change（ハーネスが自分の state を書き換える）
  → snapshot.sh <harness> "round-N proposed"
  → accept_change.sh（dev のみで判定。hidden は見ない）
  → accept: そのまま / reject: git revert して「何を試して何がダメだったか」を残す
```

reject した変更も履歴に残すのは、それ自体が③（将来の LoRA）の教材になるため。
