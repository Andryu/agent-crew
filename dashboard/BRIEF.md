# STONEFISH Dashboard 実装ブリーフ（実データ接続）

> 新セッション用キックオフ文書。UI/UX は確定済み（`prototype/stonefish-dashboard.html`）。
> 本ブリーフの残作業は「実データ配線」のみ。ブランチ: `feature/dashboard-live`

## 決定済み事項（再議論しない）

- **管理場所**: agent-crew リポジトリ内 `dashboard/`（本社機能扱い。hooks・settings・配布機構が同居するため。将来必要なら別リポジトリへ抽出）
- **UI**: `prototype/stonefish-dashboard.html` が確定版。コマンドセンター＋組織マップ＋スプリントループ＋ピクセルオフィスの4面＋常設承認キュー。ダーク/ライト両対応、ANIMトグル（OSのreduce-motion非依存）
- **キャラ設定**: Mina設計（各エージェントのビジュアル署名・台詞・デスク小物・ヤニ猫・オフィス成長はプロトタイプに実装済み）
- **指示出し・承認アクションはスコープ外**（ハーネスタスク#1として保留中。本実装は読み取り専用の可視化まで）

## アーキテクチャ（ADR-016で transcript 監視方式へ転換。B案縮小版）

> **2026-08-02更新**: 当初は disler/claude-code-hooks-multi-agent-observability 構成（hooks → HTTP POST → サーバ）を踏襲していたが、「各リポジトリへのhooks配線が運用の手間」というオーナー指摘を受け、**ADR-016**でtranscript監視方式へ転換した。決定の経緯・却下した代替案（グローバルhooks／OTelテレメトリ）・エスカレーション条件は ADR-016 を参照。

```
~/.claude/projects/**/*.jsonl ──定期ポーリング──▶ ローカルサーバ ──WebSocket──▶ SPA（prototype改修）
(Claude Codeがhooksの有無に               (アクティブセッション自動発見・            (シミュレーションtickを
 関わらず自動生成する全プロジェクト        transcript増分tail・部門/トークン集計・     WSストアの購読に差し替え)
 共通のtranscript。hooks配線は不要)        承認キュー複数プロジェクト監視)
```

- **セッション発見**: `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl` を定期スキャンし、最近更新されたファイル＝アクティブセッションとして自動登録する。リポジトリごとの設定は不要（新規プロジェクトも自動的に対象になる）
- **部門マッピング**: `scripts/token-report.py` の DEPARTMENTS 辞書と同一規則。transcriptの各行に直接記録されている `cwd` フィールドから判定する（プロジェクトdir名の部分一致 → product/invest/other）
- **エージェント同定**: subagent type（pm/architect/engineer-*/qa/retro/security/coo…）→ ペルソナ（Yuki/Alex/Riku/Sora/みゆきち/Kai/Rin…）のマッピングテーブル
- **承認キュー**: `_queue.json` のゲート状態を複数プロジェクト分横断監視して表示（アクションは付けない）。承認待ちの即時性が高い状態は、`tool_use` 出力後に対応する `tool_result` が一定時間未記録というヒューリスティックで代替する（Notificationフックは使わない。実用に耐えないと実証されるまではADR-016のエスカレーションパスに従い追加禁止）
- **トークン会計**: token-report.py と同じ集計規則（message.id 重複排除を忘れない — 途中経過行の合算は2〜5倍水増しする既知の罠）。`dashboard/server/tokens.py` の `TranscriptAggregator` で実装済み
- **既存hooks方式（emit_event.py, POST /events）**: 当面は互換性のため残置するが、Phase 2で段階的に縮小・撤去する（ADR-016参照）

## マイルストーン

| M | 内容 | 完了条件 |
|---|------|----------|
| M1 | イベントパイプライン（hooks スクリプト＋受信サーバ） | 実セッションのイベントが JSONL に落ち、WS で配信される（完了。ただしADR-016によりhooks依存部分はPhase 2で縮小予定） |
| M2 | SPA 実データ化 + サーバのtranscript監視方式への転換（ADR-016 Phase 1） | prototype の `tick()` シミュレーションを WS ストア購読に置換。4面すべて実データ駆動。サーバは `~/.claude/projects/` 横断監視でリポジトリ配線ゼロを実現 |
| M3 | 導入の仕組み（ADR-016によりスコープ再検討） | 当初は `install.sh --only=dashboard-hooks` で各リポジトリへhooks登録する想定だったが、ADR-016でtranscript監視方式に転換したため配線作業自体が不要になる見込み。既存hooks（互換性維持分）の撤去タイミングと合わせて再検討する |

## プロジェクト憲章（組織憲章第4条・簡易版）

- **MVP**: 実スプリント実行中に、ダッシュボードがエージェント状態・承認待ち・部門トークンをおおむね2秒以内の遅延で反映すること（transcript監視方式でも維持を目指す。ポーリング間隔での達成可否はADR-016 Phase 1実装後に実データで検証）
- **成功指標**: 次回スプリントをオーナーがダッシュボードだけ見て追えること（ターミナルログを開かずに済むこと）
- **撤退基準（更新: ADR-016）**: 当初の撤退基準（hooksで状態再構成できなければtranscript監視へピボット）は2026-08-02に実行済み。以降の撤退基準は ADR-016「将来の再検討トリガー」を参照: (1)承認待ちのヒューリスティック検知が実用に耐えないと実証された場合はNotificationフック1本のみ追加（エスカレーションパス）、(2)ポーリング間隔でも2秒以内目標を満たせないと判明した場合、(3)いずれも不可なら中止して教訓化
- **注意**: hooks 変更は settings.json を触るため、必ずバックアップ→jqマージ→構文検証の手順（Sprint-25 で確立済み）。公開系操作なし（L2以内）。ADR-016以降、hooksの新規追加は「Notificationフック1本のみ」の例外を除き禁止

## 参考

- disler/claude-code-hooks-multi-agent-observability（イベント12種の収集パイプライン設計。M1時点で参照、ADR-016以降はtranscript監視が主軸）
- rolandal/pixel-agents-standalone（~/.claude/projects JSONL 監視の fallback 実装。ADR-016で採用した方式の先行実績）
- Sprint-24 教訓: ストリーミングJSONLは実データ確認必須（agent-crew-sprint-24-tooling-001）
- **ADR-016**: イベント収集方式のtranscript監視への転換の決定・理由・却下した代替案・エスカレーション条件（`docs/adr/ADR-016-dashboard-transcript-monitoring.md`）
