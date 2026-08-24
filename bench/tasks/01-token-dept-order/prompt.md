# タスク: 部門別トークン集計にゲーム部門とビデオ部門を追加する

dashboard/server/enrich.py と scripts/token-report.py は、プロジェクトのパス
（または ~/.claude/projects/ 配下のエンコード済みディレクトリ名）から
部門（product / invest / other）を判定し、トークン消費を部門別に集計している。

組織にゲーム部門とビデオ部門が増えたので、この2部門も判定できるようにしたい。
ただし、ゲーム部門の作業ディレクトリは agent-crew リポジトリの下
（例: /Users/benchuser/orca/workspaces/agent-crew/game-department）にあるため、
うまく追加しないと product に吸われてしまう点に注意すること。

## 受け入れ基準

- パスに game-department を含むものは、agent-crew の配下にあっても game と
  判定される。
- パスに stonefish-video を含むものは video と判定される。
- これまで product / invest / other と判定されていたパスの結果は変わらない。
- enrich.py と token-report.py の判定規則は同じに保つ（片方だけ直すのは不可）。
