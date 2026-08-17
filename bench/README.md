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
