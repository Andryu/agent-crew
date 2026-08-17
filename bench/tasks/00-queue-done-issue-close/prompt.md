# タスク: queue.sh done で GitHub Issue も閉じる

scripts/queue.sh はタスクキュー（.claude/_queue.json）を操作するスクリプトで、
`queue.sh done <slug> <agent> "<メッセージ>"` でタスクを DONE にする。
タスクの notes 欄には「GitHub Issue #12」のように対応する Issue 番号が
書かれていることがある。

done でタスクを完了させたとき、notes に書かれた Issue も gh コマンドで
閉じるようにしてほしい。

## 受け入れ基準

- done したタスクの notes に「#数字」があれば、その番号の Issue を gh で閉じる。
  番号が複数書かれていたら最初の1つだけ。
- Issue を閉じるときは、誰がどのタスクをどう完了したのか分かるコメント
  （エージェント名と完了メッセージを含む）を残す。
- notes に番号が無いタスクでは gh を呼ばず、タスクはこれまで通り DONE になる。
- gh コマンドが入っていない環境では何もせず正常終了する。
- Issue を閉じるのに失敗しても、done 自体は失敗にしない。
- done の今まで通りの動き（DONE への変更・events への記録・summary の更新）は
  変えないこと。
