# タスク: 教訓レコードに status を追加し、set-status で更新できるようにする

scripts/lessons.sh は教訓を JSON ファイル（環境変数 LESSONS_FILE で指定）に
追記するスクリプトで、今は add コマンドだけがある。各教訓が「提案止まりか、
対応済みか」を追えるようにしたい。

## やること

- add で作られるレコードに status フィールドを持たせる。値は
  proposed / issue_created / implemented / verified / dismissed の5種類。
  --status オプションで指定でき、省略時は proposed。
- 新しいコマンド `lessons.sh set-status <id> <status>` を追加する。
  指定した id のレコードの status（と更新時刻）だけを書き換える。

## 受け入れ基準

- add の今まで通りの動き（必須オプションの検査、id の採番、priority_score =
  severity × frequency、既存レコードを保持したままの追記）は変わらない。
- add で --status を省略すると status は proposed になる。--status で5種類の
  どれかを指定するとその値が入る。5種類以外を渡すとエラー終了し、ファイルは
  変わらない。
- set-status は対象レコードの status だけを更新する。他のレコードや、
  対象レコードの他のフィールド（description など）は変わらない。
- set-status に5種類以外の status、または存在しない id を渡したときは
  0 以外の終了コードで終わり、ファイルは変わらない。
