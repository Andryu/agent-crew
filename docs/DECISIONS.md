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
