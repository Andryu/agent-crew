# ADR-013: グローバル学習ログアーキテクチャ

- **Status**: Accepted
- **Date**: 2026-06-14
- **Issue**: #112

---

## 背景

agent-crew はスプリント管理・教訓収集（`~/.claude/_lessons.json`）の仕組みを持つが、
クロスリポジトリでの活動情報は収集されていない。別リポジトリ（例: alpha-predict-jp）で
得た知見を agent-crew に自動フィードバックする「自律成長ループ」を実現するためには、
**どのリポジトリでエージェントが動作したか**を記録する仕組みが必要。

---

## 調査結果: Cron フック不在

Sprint-21 の調査（Issue #114, claude-code-guide エージェント確認）で、
**Claude Code に Cron フックは存在しない**ことが確認済み。

代替候補の比較:

| 手法 | 実装コスト | 信頼性 | 全プロジェクト対応 |
|------|-----------|--------|------------------|
| launchd (macOS) | 高 | 高 | ○ |
| GitHub Actions scheduled | 高 | 中 | ✗（リポジトリ依存）|
| SessionStart フック | 低 | 中 | ○（グローバル設定で可） |
| **SubagentStop フック** | **低** | **高** | **○（グローバル設定で可）** |
| Stop フック | 低 | 高 | ○（グローバル設定で可） |

→ **SubagentStop + Stop フックをグローバル `~/.claude/settings.json` に登録する方式**を採用。

---

## 決定事項

### アーキテクチャ

```
全プロジェクト共通 (~/.claude/settings.json グローバル):
  SubagentStop → ~/.claude/hooks/capture-learning.sh
                 └─ ~/.claude/learning-logs.jsonl に JSONL 追記
  Stop         → ~/.claude/hooks/aggregate-learnings.sh
                 └─ 当日の外部リポジトリ活動サマリーを stderr 出力
```

### learning-logs.jsonl スキーマ

```json
{
  "ts":         "2026-06-14T10:00:00Z",
  "repo":       "alpha-predict-jp",
  "repo_url":   "git@github.com:Andryu/alpha-predict-jp.git",
  "agent_type": "pm",
  "cwd":        "/Users/.../alpha-predict-jp",
  "session_id": "abc123"
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `ts` | ISO 8601 UTC | イベント発生時刻 |
| `repo` | string | `git remote get-url origin` のベース名（`.git` 除去） |
| `repo_url` | string | フルリモート URL（`local` の場合はローカル判定） |
| `agent_type` | string | SubagentStop ペイロードの `agent_type` フィールド |
| `cwd` | string | エージェント実行時の作業ディレクトリ |
| `session_id` | string | セッション識別子（空の場合あり） |

### セットアップ方法

```bash
# agent-crew リポジトリで一度だけ実行
bash install.sh --only=global-hooks go .

# または
bash install.sh --global-hooks go .
```

実行内容:
1. `~/.claude/hooks/capture-learning.sh` → `scripts/capture-learning.sh` のシンボリックリンク作成
2. `~/.claude/hooks/aggregate-learnings.sh` → `scripts/aggregate-learnings.sh` のシンボリックリンク作成
3. `~/.claude/settings.json` に SubagentStop / Stop フックを jq でマージ追記

### スクリプトの更新フロー

```bash
# agent-crew で scripts/ 以下を編集・コミット・push
git commit -am "fix: capture-learning.sh を改善"
git push

# 別マシン・別セッションでは
cd ~/Workspace/agent-crew && git pull
# → シンボリックリンク経由で ~/.claude/hooks/*.sh が自動更新
```

---

## トレードオフ

**良い点**:
- `git pull` だけでフック更新が全プロジェクトに反映（シンボリックリンクの恩恵）
- launchd 設定不要、追加デーモンなし
- `bash -n` でバリデーション可能な純粋な bash スクリプト

**制約**:
- SubagentStop はサブエージェント停止時のみ発火。メインセッションのみの場合は記録されない
- Stop フックは集約サマリー出力のみ（永続化は SubagentStop 側で行う）
- **CI/CD・クラウドセッションでは `~/.claude/` が存在しないため silent fail**（ローカル Mac 専用）
- 複数マシン間では agent-crew を同じパスに clone する規約が必要（dangling symlink 防止）

---

## 将来の再検討トリガー

- Claude Code にネイティブの Cron/Schedule フック機能が実装された場合
- クラウドセッションでの学習収集が要件になった場合（launchd 等への移行を検討）
- `learning-logs.jsonl` のサイズが問題になった場合（ローテーション戦略の追加）
