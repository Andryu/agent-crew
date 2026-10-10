# agent-crew 共通作業契約

- 説明・コメント・連絡は日本語。技術用語と識別子は元の形式を維持する。
- Git、実ファイル、テスト結果を根拠にする。未追跡を含む他セッションの変更を上書き・破棄しない。対象外の差分は所有者と影響を確認して報告する。
- Claude CodeとCodexの両方でこの契約を使う。通常はメインが調査・設計・実装・関連テストを進める。オーナーの担当・runtime指定を優先する。起動は`scripts/crew claude`または`scripts/crew codex`。Codexでは現行の`direct-reviewer`以外の旧agent定義を利用可能と仮定しない。
- complexity M以上またはrisk medium以上では短いSPEC/PLAN、代替案、完了条件を`docs/plans`に記録する。重要な設計判断は確定前に独立反証する。具体的な判断と検証は[工程ガイド](.agents/skills/fable-class/SKILL.md)を参照する。
- 権限、外部副作用、データ送信境界、後方互換性、金融計算の意味を変える変更は、仕様準拠と品質を別々の新規コンテキストでレビューする。対象差分、受入条件、検証結果を渡す。レビュー不能なら未レビューと記録し、完了条件を満たしたと扱わない。小さな局所修正や文言変更に文書一式と二段レビューを一律要求しない。
- queue正本は`.claude/_queue.json`。repo rootから`bash scripts/queue.sh`で操作し、JSONを直接編集しない。既存タスクは`start`で着手し、独立レビュー結果をメインが`qa`で記録する。QA対象は`APPROVED`確認後に`done`。差戻しは修正と再レビューへ戻し、完了ガードを迂回しない。詳細は[Codex直接利用ガイド](docs/codex-direct/README.md#queue運用と検証)。
- `done`前に`close_issue`を確認する。Issue close/comment、通知、Vault自動処理、外部送信、commit/pushは承認された範囲でのみ行う。台帳設定の書換えで承認境界を迂回しない。承認済み範囲の作業は自走する。
- hookの原本は`config/crew-hooks.json`と`scripts/crew_hooks.py`。呼出し形式は`scripts/install_crew_hooks.py`で生成し、生成済み設定を手で分岐させない。共通hookはqueueを自動でDONEにせず、外部送信しない。
- スプリント計画・レトロ前は`~/Workspace/Obsidian/knowledge/agent-crew-failure-patterns.md`と`~/Workspace/Obsidian/decisions/agent-crew-adr-index.md`を読む。完了時は変更、関連テスト、残る制約を報告する。中断・引継ぎ時は目的、現在地、次手、承認待ち、再検証方法を`docs/plans`に短く残す。
