# agent-crew 共通作業契約

- 説明・コメント・連絡は日本語。技術用語と識別子は元の形式を維持する。
- Git、実ファイル、テスト結果を根拠にする。未追跡を含む他セッションの変更を上書き・破棄しない。
- Claude CodeとCodexのどちらでもこの共通契約を使う。通常はメインが調査・設計・実装・関連テストを行う。役割は工程として維持し、小作業でPM→設計→実装の多段委任を強制しない。起動は `scripts/crew claude` または `scripts/crew codex`。
- complexity M以上またはrisk medium以上ではSPEC/PLAN、代替案、完了条件をdocs/plansに記録する。重要な設計判断は確定前に独立反証を行う。スプリント計画・レトロ前は `~/Workspace/Obsidian/knowledge/agent-crew-failure-patterns.md` と `~/Workspace/Obsidian/decisions/agent-crew-adr-index.md` を読む。
- 独立レビューが必要な変更は、Codexではdirect-reviewer、Claudeではnativeのqa/doc-reviewer等に対象・受入条件・検証結果を渡す。仕様準拠と品質は別の新規コンテキストで確認する。レビュー不能なら未レビューと記録し、完了条件を満たしたと扱わない。
- Codexの旧agentコピーには未移植のClaude手順があるため通常はメインとdirect-reviewerを使う。Claudeはnativeの役割定義を使える。スキルの固有委譲方式より、オーナーが指定したランタイムと直接実装の方針を優先する。
- queue正本は `.claude/_queue.json`。repo rootから `bash scripts/queue.sh` 経由で操作する。別cwdでは入口と`QUEUE_FILE`を絶対パスにする。JSONを直接書き換えない。
- 既存タスクがある場合、着手は`start`、独立レビュー結果はメインが`qa`で記録する。QA対象は`APPROVED`確認後に`done`。差戻しは修正と再レビューへ戻す。完了ガードを迂回しない。
- `qa`の台帳名義は既存実装でSoraになるため、summaryに実際のレビュアー名、対象ファイルや差分の識別情報、判定、証跡パスを残す。direct-reviewerの判定を既存Soraの実行結果と混同しない。
- `done`前にタスクの`close_issue`を確認する。Issue close/commentは外部操作として承認された範囲でのみ行う。承認がなければその操作を保留し、台帳設定の書換えで迂回しない。
- hookの原本は `config/crew-hooks.json` と `scripts/crew_hooks.py`。呼出し形式は `scripts/install_crew_hooks.py` で生成する。生成済み設定を手でコピーして分岐させない。
- 担当タスクを終了時に確認する場合は `scripts/crew --task <slug> claude|codex`。repoとtaskのscopeをその起動に限定する。Stopは一度だけ継続を求め、再入時には未完了の警告を残す。台帳判定をテスト実行・独立レビューそのものの代わりにしない。
- 通知・Vault自動処理は個別承認。共通hookはqueueを自動でDONEにせず、外部送信しない。Hermes、他pane、commit/pushはhook共通化の承認に含めない。
- 完了時は変更内容、関連テスト結果、残る制約を報告する。中断・引継ぎ時は目的、現在地、次の一手、承認待ち、再検証コマンドをdocs/plansに短く残す。
