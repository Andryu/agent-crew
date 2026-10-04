# タスク: ルール書き出し対象の抽出条件を1か所にまとめる

scripts/lessons.sh は教訓（環境変数 LESSONS_FILE のJSON）を管理し、
scripts/propose-lesson-rules.sh は「優先度が高く未対処」の教訓をエージェント設定への
追記案として提案する。現在この抽出条件が propose 側に直書きされており、他の手順と
条件がずれるドリフトが起きている。さらに、外部リポジトリ由来の教訓を無条件に
自リポジトリの行動ルールへ昇格させないための「信頼境界」も必要になった。

## やること

- lessons.sh に読み取り専用サブコマンド list-rule-candidates を追加する。
  ルール書き出し対象の教訓を1行1JSONで出力し、この条件判定を唯一の実装にする。
  対象の条件:
  - priority_score が最小値（--min-priority、省略時 3）以上
  - status が未確定（proposed / issue_created / implemented / open / 未設定）
  - enforcement が code のものは除く（コード側で強制済みのため）
  - 信頼境界: 自リポジトリ由来（source_repo が自分の origin と同一。SSH/HTTPS や
    末尾 .git の表記ゆれは同一視）・source_repo 未設定・owner_approved の
    いずれかを満たすものだけ
- --excluded を付けると「信頼境界だけで落ちた」教訓を代わりに出力する。
  優先度や status や enforcement で落ちたものは出さない。
- --min-priority に数値以外を渡したらエラー終了する。
- add に --owner-approved フラグを追加し、レコードに真偽値で保存する。
- add の --supersedes は、存在しない教訓IDを渡したらエラー終了して何も書かない。
- propose-lesson-rules.sh の抽出処理を list-rule-candidates の呼び出しに
  置き換え、両者が常に同じ対象を選ぶようにする。

## 受け入れ基準

- list-rule-candidates が上記条件の組み合わせを正しく判定する。
- --excluded は信頼境界のみで除外された教訓だけを出す。
- propose-lesson-rules.sh --dry-run が提案する教訓の集合は、同じ条件の
  list-rule-candidates の出力と完全に一致する。
- add / set-status / promote など既存サブコマンドの動きは変わらない。
