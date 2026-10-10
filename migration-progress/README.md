# 移行進捗ボード

`state.json`を読むだけのターミナル表示です。**表示専用台帳であり、`.claude/_queue.json`の正本ではありません。** queueは自動更新しません。追加のLLM、Webサーバー、DB、AI監視も使いません。

```bash
python3.12 migration-progress/progress.py
python3.12 migration-progress/progress.py --once
```

表示は約3秒ごとに再描画します。Ctrl+Cで終了します。状態ファイルが不正・読取不能なら全taskを「未確認」と表示し、更新コマンドは状態を上書きしません。

## 実装agent共通手順

着手・検証・完了・ブロックの節目で、担当taskの`--status`、`--current`、`--next`、`--blocker`をCLIで更新してください。`--task`付きの作業・次・判断待ちは、task欄と全体欄の両方に反映されます。受入未確認を「完了」にせず、親の受入確認後だけ`--accepted`を付けます。全体計画と採否は親Astraが決めます。

```bash
python3.12 migration-progress/progress.py set --task P0 --status 進行中 --current '現状を確認' --next '比較基準を記録' --blocker 'なし'
python3.12 migration-progress/progress.py set --task P0 --status 検証中 --current 'fixtureを検証' --next '親の受入確認' --blocker 'なし'
python3.12 migration-progress/progress.py set --task P0 --status 完了 --accepted --current '受入確認済み' --next 'P1の範囲判断' --blocker 'なし'
python3.12 migration-progress/progress.py set --task P0 --status 判断待ち --current '判断を待機' --next '親の指示を反映' --blocker '親の判断待ち'
```

全体欄だけを変える場合は`--task`なしで`--overall`、`--current`、`--next`、`--blocker`を指定します。書込先はこのディレクトリの`state.json`のみで、同じディレクトリの一時ファイルから原子的に置換します。実移行のqueueや設定には触れません。
