# Codex移行の引継ぎと再開

対象はagent-crewとwealth-advisorの**開発移行 P0〜P5**。技術的な進捗、検証、復旧コマンドの正本は各repoに置く。Obsidianの`projects/agent-crew-codex-operating-model-replan.md`は横断の目的と入口であり、版依存の手順や実装契約を複製しない。Vaultの機能仕様・PDR・採用済み業務ルールは引き続きVaultが正本。

## 節目で残す

作業終了、中断、同じ失敗の再発時に、対象repoの`docs/plans/`へ次の短い記録を残す。毎ターンの保存やStop時のLLM抽出は要求しない。未確認を「完了」に変換しない。

```markdown
## 引継ぎ（確認日時、担当）
- 目的・依頼範囲: （記入）
- 現在地: P番号、完了/進行中/未着手を分ける
- 版: repo、checkout、branch、HEAD、未コミット成果のパスと必要なSHA-256
- 検証: コマンド、結果、未実施の検証、証跡パス
- 判断: 理由、代替案、再検討条件、正本リンク
- 未解決・リスク: （記入）
- 承認境界: 許可済み操作と未許可の外部操作を分ける
- 次の一手: 対象ファイルと再検証コマンド
```

Vaultには既存のproject入口へ、匿名化した「目的、到達点、未完、次の一手、repo記録へのリンク」を追補する。横断教訓が再利用できる場合だけ「状況→失敗→原因→次回の対応→証拠」を`knowledge/`に残す。記録には観測日と確認日を区別し、事実・仮説・採用済み・失効を明示する。生会話、実セッションログ、認証情報、実資産本文は読まず保存しない。既存の検索DBや自動captureをこの手順で導入・有効化しない。

## 新規セッションの再開順

1. Vaultの`projects/agent-crew-codex-operating-model-replan.md`から目的と適用範囲を確認する。wealthの過去の状態は`projects/wealth-advisor-codex-migration-status.md`へ辿る。両ノートの更新日を現在のGit状態と混同しない。
2. agent-crewの`AGENTS.md`、`docs/plans/2026-09-21-codex-operating-model-replan.md`、最新の引継ぎ記録を読む。wealthの作業ならwealth側の`AGENTS.md`と現行planも読む。
3. 各repoで`git status --short`、`git branch --show-current`、`git rev-parse HEAD`を実行し、記録したパス・hash・レビュー証跡が現在のcheckoutに存在するか照合する。記録より実ファイルとGitを優先し、差があれば未確認として扱う。
4. 関連教訓を必要な数件だけ読み、対象テストを実行する。失敗・差分・承認待ちを整理し、記録にある次の一手を現状に合わせて進める。queue対象ならrepo契約に従って`bash scripts/queue.sh`経由で扱う。

現在地、版、今回の依頼で承認された操作は[最新の引継ぎ証跡](../plans/2026-09-21-migration-handoff-evidence.md)を入口に、実ファイルとGitで再確認する。元の移行再計画にある「提案、設定未適用」は計画作成時点の記録であり、進行中のphaseを示さない。P6/P7は今回の範囲外。開発移行完了とwealthの実データ読み取り・Notion更新は別の到達点。接続の存在を業務利用の許可と解釈しない。

## 新規セッション実証

実装者と別の新規コンテキストに、会話履歴を渡さず次だけを指定する。

> `projects/agent-crew-codex-operating-model-replan.md`を入口に、リンクされたrepoの現行計画・引継ぎ・Git状態を確認してください。現在の目的、両repoの版、P0〜P5の実際の到達点、未解決と承認境界（今回の依頼で許可されたcommit/push/PR/レビューを含む）、次の具体的なコマンドを出典付きで報告してください。実装・設定変更・資産情報アクセスはしないでください。

判定は、目的・版・未完・次手を正しく再現し、古いVault状態や未コミット成果を完了扱いせず、P6/P7へ進まないこと。実証者、日時、入力、出力証跡、判定と誤読をrepoの引継ぎ記録に追記する。実証前はP3を完了扱いしない。
