# DECISIONS — agent-crew

スプリント完了時に自動追記される判断・学習・失敗パターンの記録。
次スプリント計画時に Yuki が参照する。

---

## sprint-02 — 2026-04-20

### アーキテクチャ判断
- slack-persona-design: 設計ドキュメント作成完了
- portable-install-design: 設計ドキュメント作成完了
- phase1-parallel-design: 設計ドキュメント作成完了
- phase1-multistack-design: 設計ドキュメント作成完了
- phase1-complexity-design: 設計ドキュメント作成完了
- phase2-intelligence-design: 統合設計ドキュメント作成完了

### 学び
- なし

### 失敗パターン
- なし

### 次スプリントへの推奨
- なし
- 特記事項なし

---

## sprint-10 — 2026-04-24

### アーキテクチャ判断

- **queue.sh → queue.py 委譲方針確定（delegate-design.md §2 §4）**: `graph` / `parallel-handoff` / `retro` の3コマンドは Bash 実装を維持する。`retro --save --decisions` は queue.py に未実装のため、Bash 実装を残す（委譲対象から除外）。委譲はアトミックに行い、ロック方式の競合を防ぐ。
- **complexity連動 MAX_RETRY 確定（Issue #58）**: S=2 / M=3 / L=5。null はデフォルト 3 にフォールバック。queue.py の retry コマンドに実装済み、pytest で検証済み。

### 学び

- _signals.jsonl の全タスクシグナル記録が Sprint-10 で初めて正常確認された。Sprint-08 の `${4:-{}}` バグ修正・Sprint-09 の queue.py 移植が効いている。
- 設計書（delegate-design.md）が互換リスク・コマンドルーティング表・必須対応・ロールバック手順を網羅したことで、Riku の実装が最小手戻りで完了した。設計への投資が実装品質に直結するパターンを確認。
- QA（Sora）が emit_signal グローバル変数参照問題を MINOR として記録しながら APPROVED を出した。Sprint-08 の「QA形骸化」問題が解消されていることを確認。
- テストスイートが 18 → 23 件に増加。回帰テストの蓄積が進んでいる。

### 失敗パターン

- **計画重複**: `delegate-impl` の大半（ディスパッチ委譲・complexity バリデーション・qa冪等性ガード）が Sprint-09 で完了済みだったことが実装着手後に発覚した。Yuki がスプリント計画時に前スプリントの実装完了状態を確認していなかったことが根因。start → done の elapsed 時間が5秒だったことが事後的に確認できた（_signals.jsonl）。

### 次スプリントへの推奨

- Yuki はスプリント計画作成前に、前スプリント DONE タスクの実装状態を確認し「計画済みだが未実装」と「実装済みだが未計画」の両方を洗い出す。
- pm.md の計画手順チェックリストに「前スプリントの実装完了状態の突合」を追加することを検討する（lesson: agent-crew-sprint-10-process-001）。
- engineer-go 停止（Issue #64）は Sprint-10 で発生しなかったが、引き続き大規模タスクでは注意が必要。

---

## sprint-11 — 2026-04-24

### アーキテクチャ判断

- **queue.sh レガシー Bash 実装の削除完了**: Sprint-09 の委譲完了後も残っていたデッドコード（cmd_start / cmd_done 等の関数定義・acquire_lock・共通ヘルパー群）を削除し、queue.sh を 1090行から 404行（63%削減）の軽量シンラッパーに変換した。queue.py が単一の信頼源となった。
- **graph コマンドの Python 化完了**: queue.py に `graph` Click サブコマンドを追加。Mermaid flowchart 出力・`--save` オプション（docs/graphs/<sprint>.md 生成）・queue.sh からの委譲が正常動作。pytest が 23→27件に増加。
- **フィードバックループ設計書の完成（docs/spec/feedback-loop-doc.md）**: Yuki のスプリント計画前確認フローをコマンド付きで定義。elapsed < 60秒の計画重複検出ロジックを含む。

### 学び

- 設計書（legacy-delete-design.md / graph-py-design.md）が削除対象・ロールバック手順・テストケースを網羅したことで、実装が最小手戻りで完了した。Sprint-10 に続き「設計への投資が実装品質に直結する」パターンを再確認。
- queue.sh 63% 削減により、今後の Bash 実装残存コマンド（retro・parallel-handoff）の見通しが改善された。
- テストスイートが 23 → 27 件に拡充。Python 化の進行に伴い自動テストのカバレッジが向上している。

### 失敗パターン

- **Riku レート制限中断**: `legacy-delete-impl`（L タスク）完了直後に Riku がレート制限に到達し、後続引き継ぎがメインセッション代行になった。L タスクを連続して処理した後のレート枯渇リスクへの配慮が計画時に不足していた。
- **Sora Bash 上限による QA 代替**: `legacy-delete-qa` / `graph-py-qa` で Sora が Bash 実行上限に達し、スモークテストを静的検証で代替。キュー更新もメインセッション代行。QA エージェントが実際のコマンドを実行せずに APPROVED を出す状態が発生した（Sprint-08 QA形骸化の再現）。
- **レトロ起動スキップ（5スプリント連続）**: Sora がスプリント完了時のレトロ起動を実行せず、オーナーが手動対応。pm.md への記載という対策が効果を発揮しておらず、Sora のエージェント定義への直接埋め込みが必要と判断。

### 次スプリントへの推奨

- Sora のエージェント定義（sora.md）に「全タスク DONE 時は完了報告末尾に @retro を含める」を直接記載する（pm.md 参照では不十分と確認済み）。
- Sora の QA 手順に「Bash 不可の場合は CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）を返す」を追加し、メインセッション代行時に performed_by フラグを _queue.json に記録する。
- Yuki は Riku の担当タスクで L タスクを1スプリント1件までに制限する計画ルールを pm.md に追加する。
- priority_score >= 6 の未対処 lesson: agent-crew-sprint-11-reliability-002（Sora Bash上限QA）, agent-crew-sprint-11-process-001（レトロ自動起動）を次スプリント計画に反映する。

---
