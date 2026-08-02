# STONEFISH Dashboard 実装ブリーフ（実データ接続）

> 新セッション用キックオフ文書。UI/UX は確定済み（`prototype/stonefish-dashboard.html`）。
> 本ブリーフの残作業は「実データ配線」のみ。ブランチ: `feature/dashboard-live`

## 決定済み事項（再議論しない）

- **管理場所**: agent-crew リポジトリ内 `dashboard/`（本社機能扱い。hooks・settings・配布機構が同居するため。将来必要なら別リポジトリへ抽出）
- **UI**: `prototype/stonefish-dashboard.html` が確定版。コマンドセンター＋組織マップ＋スプリントループ＋ピクセルオフィスの4面＋常設承認キュー。ダーク/ライト両対応、ANIMトグル（OSのreduce-motion非依存）
- **キャラ設定**: Mina設計（各エージェントのビジュアル署名・台詞・デスク小物・ヤニ猫・オフィス成長はプロトタイプに実装済み）
- **指示出し・承認アクションはスコープ外**（ハーネスタスク#1として保留中。本実装は読み取り専用の可視化まで）

## アーキテクチャ（disler/claude-code-hooks-multi-agent-observability の構成を踏襲）

```
Claude Code hooks ──HTTP POST──▶ ローカルサーバ ──WebSocket──▶ SPA（prototype改修）
(SessionStart/PreToolUse/          (状態集約・SQLiteまたは          (シミュレーションtickを
 PostToolUse/SubagentStart/         メモリ+JSONL永続化)              WSストアの購読に差し替え)
 SubagentStop/Stop/Notification)
```

- **部門マッピング**: `scripts/token-report.py` の DEPARTMENTS 辞書と同一規則（プロジェクトdir名の部分一致 → product/invest/other）
- **エージェント同定**: subagent type（pm/architect/engineer-*/qa/retro/security/coo…）→ ペルソナ（Yuki/Alex/Riku/Sora/みゆきち/Kai/Rin…）のマッピングテーブル
- **承認キュー**: Notification（permission要求）イベント＋ _queue.json のゲート状態を表示（アクションは付けない）
- **トークン会計**: token-report.py と同じ集計規則（message.id 重複排除を忘れない — 途中経過行の合算は2〜5倍水増しする既知の罠）

## マイルストーン

| M | 内容 | 完了条件 |
|---|------|----------|
| M1 | イベントパイプライン（hooks スクリプト＋受信サーバ） | 実セッションのイベントが JSONL に落ち、WS で配信される |
| M2 | SPA 実データ化 | prototype の `tick()` シミュレーションを WS ストア購読に置換。4面すべて実データ駆動 |
| M3 | 導入の仕組み | `install.sh --only=dashboard-hooks` で hooks 登録（settings.json の既存 hooks を壊さない jq マージ、Sprint-25 の enforce-retro-stop.sh の手法を踏襲） |

## プロジェクト憲章（組織憲章第4条・簡易版）

- **MVP**: 実スプリント実行中に、ダッシュボードがエージェント状態・承認待ち・部門トークンをおおむね2秒以内の遅延で反映すること
- **成功指標**: 次回スプリントをオーナーがダッシュボードだけ見て追えること（ターミナルログを開かずに済むこと）
- **撤退基準**: hooks 由来のイベントで主要状態（誰が何をしているか）が再構成できないと判明したら、方式を transcript JSONL 監視（Pixel Agents fallback方式）へピボット。それも不可なら中止して教訓化
- **注意**: hooks 変更は settings.json を触るため、必ずバックアップ→jqマージ→構文検証の手順（Sprint-25 で確立済み）。公開系操作なし（L2以内）

## 参考

- disler/claude-code-hooks-multi-agent-observability（イベント12種の収集パイプライン設計）
- rolandal/pixel-agents-standalone（~/.claude/projects JSONL 監視の fallback 実装）
- Sprint-24 教訓: ストリーミングJSONLは実データ確認必須（agent-crew-sprint-24-tooling-001）
