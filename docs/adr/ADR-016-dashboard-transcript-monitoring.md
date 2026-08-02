# ADR-016: STONEFISHダッシュボードのイベント収集を transcript 監視方式へ転換（B案縮小版）

- **Status**: Accepted
- **Date**: 2026-08-02
- **Issue**: なし（riku-m2aの判断依頼 → team-lead-stonefish経由でオーナー承認）

---

## 背景

STONEFISHダッシュボード（`dashboard/`）のM1実装は、`disler/claude-code-hooks-multi-agent-observability` の構成を踏襲し、各リポジトリの `.claude/settings.json`（または `.claude/settings.local.json`）に `dashboard/hooks/emit_event.py` を7イベント（SessionStart/PreToolUse/PostToolUse/SubagentStart/SubagentStop/Stop/Notification）で登録し、受信サーバへHTTP POSTする方式で構築した（M1完了）。

M2サーバ拡張（トークン会計・承認キュー配信）の実装完了後、実際にダッシュボードを表示したところ、イベントが「hooksを配線した1リポジトリのセッションだけ」しか反映されないことが判明した。調査の結果、原因は `dashboard/hooks/emit_event.py` を呼ぶhooksがこの `dashboard` ワークツリーの `.claude/settings.local.json`（gitignore対象のローカル限定設定）にしか登録されておらず、`agent-crew` 本体や `alpha-predict-jp` など他のリポジトリには一切配線されていないためだった。

オーナーから「リポジトリごとに hooks を設定するのは運用の手間・面倒。別の方法はないか、慎重に調べてほしい」との明示的な要望があり、riku-m2a が3方向で調査した。

---

## 検討した選択肢

1. **現行維持**: `install.sh --only=dashboard-hooks`（M3）を各リポジトリに対して個別実行し、hooksを配線し続ける
2. **A案**: hooksを7イベントとも `~/.claude/settings.json`（ユーザーレベル・グローバル）に1回だけ登録する。Claude Codeの設定階層は「上書きではなくマージ」であることを実データ調査（claude-code-guideエージェント経由の公式ドキュメント確認）で確認済みのため、技術的には可能
3. **B案（完全版）**: hooksを使わず、Claude Codeが自動生成する `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl` を横断監視する方式に統一。hooksでしか拾いにくい情報（承認待ち状態など）はClaude Code組み込みのOpenTelemetryテレメトリ（`CLAUDE_CODE_ENABLE_TELEMETRY`）で補完する
4. **B案（縮小版・採用）**: B案からOTelテレメトリ受信を外し、transcript監視のみで完結させる。承認待ち状態はヒューリスティックで代替する

---

## 決定事項

**B案縮小版を採用する。** hooks配線（dashboard/hooks/emit_event.py の各リポジトリ登録）を前提としたイベント収集をやめ、サーバ（`dashboard/server/server.py`）が能動的に `~/.claude/projects/` 配下の全プロジェクトの transcript JSONL をポーリング監視し、状態（誰が・どのプロジェクトで・何をしているか、トークン消費、承認待ち）を再構成する方式へ転換する。OpenTelemetryテレメトリ受信は実装しない。

### 採用理由

1. **オーナー制約を唯一完全に満たす**: 「リポジトリ毎の設定不要・運用手間ゼロ・追加コスト回避」を満たすのはB案のみ。`~/.claude/projects/` はClaude Codeがhooksの有無に関わらず自動的に全プロジェクトのtranscriptを書き続けるため、部門・リポジトリが増えても配線作業が一切発生しない。
2. **読み取り専用で観測対象に影響しない**: transcript監視は既存ファイルを読むだけであり、`settings.json` を一切変更しない。現状すでに稼働中のhooks（Stop 4件 + SubagentStop 1件など）に新たな障害面を追加しない。
3. **先行OSS実績がある**: `pixel-agents-standalone` / `AgentRoom` / `age-of-agents` は、いずれもJSONL監視のみ（hooksを介さない）で承認待ちを含むエージェント状態表示を実現している。承認待ちは「`tool_use` 出力後、対応する `tool_result` が一定時間記録されないまま経過している」というヒューリスティックで代替可能というのが先行実績の知見。
4. **転換コストが現時点で最小**: OTelを外すことで、転換規模は現行のhooks配線方式と同等以下に収まる。M1着手直後の今が、他の実装に依存が波及する前の最小コストのタイミング。

### エスカレーションパス（実証されるまで実装禁止）

ヒューリスティックによる承認待ち検知が実用に耐えないと実証された場合に限り、`~/.claude/settings.json` へ **Notificationフック1本だけ** をグローバル追加することを許可する。ADR-013（グローバル学習ログ）が確立した「`install.sh --only=global-hooks` によるシンボリックリンク配布 + jqマージ」の前例に従う。**全ツールフック（PreToolUse/PostToolUse等）の追加は不許可**（B案採用理由1・2を毀損するため）。

---

## 却下した代替案

| 代替案 | 却下理由 |
|--------|----------|
| 現行維持（各リポジトリにhooks個別配線） | オーナーが明示的に「面倒」と指摘した運用手間そのものであり、制約①（設定不要）を満たさない。部門が増えるたびに配線作業が発生し続ける。 |
| A案（hooksを`~/.claude/settings.json`へ7イベント全種グローバル登録） | 技術的には可能（設定はマージされる）だが、このマシンで動く**すべての**プロジェクト・**すべての**ツール呼び出し（PreToolUse/PostToolUse）ごとにhookが発火し続ける。無関係な個人プロジェクトの活動もダッシュボードに紛れ込み（`enrich.py` のDEPARTMENTSに一致しないため全部"other"）、`settings.json` の障害面（既存hooksとの競合・timeout累積）も拡大する。 |
| B案完全版（OTelテレメトリ受信込み） | OTelのメトリクス・イベントには**プロジェクトディレクトリ（cwd）属性が一切含まれない**ことが公式ドキュメント確認で判明。部門分類（product/invest/other）を行うには、別途 `session.id ⇔ cwd` の対応表を `~/.claude/projects/` のディレクトリ名から構築する必要があり、加えてOTLP受信エンドポイント（HTTP/JSON or gRPC）をサーバに新規実装する必要がある。exportの間隔がBRIEF.mdのMVP目標（2秒以内の反映）を満たすかも未検証。transcript監視だけで部門判定（transcriptの各行に `cwd` が直接記録されている）・トークン集計（`tokens.py` で実装済み）は完結するため、OTelを追加する投資対効果が低い。 |

---

## 段階移行計画

- **Phase 1（本タスク, riku-m2a担当）**: `dashboard/server/tokens.py` の `TranscriptAggregator`（既存実装、message.id重複排除・増分tail読みは流用）に加えて、`~/.claude/projects/` 配下を定期スキャンし「最近更新された transcript = アクティブセッション」を自動発見する仕組みを追加する。発見したセッションの transcript 内の `cwd` フィールドから部門判定・承認キュー（`<cwd>/.claude/_queue.json`）監視対象を導出し、複数プロジェクトを同時に扱えるようにする。承認待ちは「直近の `tool_use` に対応する `tool_result` が一定時間未記録」のヒューリスティックで検出する。
- **Phase 2（別タスク）**: 既存hooks配線（`dashboard/hooks/emit_event.py`、`.claude/settings.local.json` のテスト登録、M3の `install.sh --only=dashboard-hooks`）を段階的に縮小・撤去する。`POST /events` エンドポイントおよびhooks関連コードの要否をこのタイミングで再評価する（互換性のため当面は残置し、実際に使われなくなったことを確認してから削除する）。

---

## トレードオフ

**良い点**

- リポジトリごとの設定が生涯不要になる。新しいプロジェクトを作っても自動的にダッシュボードに現れる。
- 読み取り専用であり、`settings.json` に手を入れないため既存hooksとの競合リスクがゼロ。
- `tokens.py` の重複排除・増分tail読みロジックをほぼそのまま転用でき、実装コストが小さい。

**受け入れるトレードオフ**

- 承認待ち検知はヒューリスティックであり、hooksのNotificationイベントほど確実ではない（誤検知・検知漏れの可能性）。
- ポーリング方式のため、hooksによる即時プッシュと比べてわずかに反映が遅れる（BRIEF.mdのMVP目標「2秒以内」を満たせるかはPhase 1実装後に実データで検証する）。
- 複数プロジェクトの `_queue.json` を同時監視する分、サーバ側の状態管理がやや複雑になる。

---

## 将来の再検討トリガー

- ヒューリスティックによる承認待ち検知の精度が実用に耐えないと実証された場合（エスカレーションパスに従いNotificationフック1本のみ追加）。
- Claude CodeのOTelテレメトリにプロジェクトディレクトリ属性が標準で付与されるようになった場合（B案完全版の再検討）。
- ポーリング間隔を短縮してもMVP目標（2秒以内）を満たせないと判明した場合。
