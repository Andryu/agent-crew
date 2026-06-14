# ADR-012: グローバルスキルの配布にシンボリックリンクモデルを採用する

## Status

Accepted

## Context

agent-crew はエージェント定義・スキルのマスターリポジトリとして機能し、
複数のプロジェクト（alpha-predict-jp 等）で Claude Code エコシステムを利用するための
共通基盤を提供する。

スキル（`~/.claude/skills/<name>/SKILL.md`）の配布方法として以下を検討した：

| 方式 | 説明 | 採用 |
|------|------|------|
| コピー（cp） | インストール時に ~/.claude/skills/ へ複製 | ✗ |
| シンボリックリンク（ln -sf） | agent-crew のファイルを直接参照 | ✓ |
| npm/pip パッケージ | パッケージレジストリを通じて配布 | ✗ |
| Git サブモジュール | agent-crew をサブモジュールとして取り込む | ✗ |

制約：
- 個人開発者のローカル Mac 環境（複数プロジェクトを管理）
- セットアップは 1 回、更新は `git pull` だけで完結させたい
- 公開パッケージ化は現時点では不要
- 複雑な運用フローは避けたい
- `~/.claude/skills/life-planner` はすでに `ln -sf` で実装済みであり実績がある

## Decision

グローバルスキル（`~/.claude/skills/*/`）の配布にシンボリックリンクモデルを採用する。
`install.sh` の新規 `COMP_GLOBAL_SKILLS` セクションで `symlink_skill` 関数を使って
`ln -sf` でリンクを張る。

**エージェント定義（`~/.claude/agents/*.md`）はコピーモデルを維持する。**
エージェント定義はプロジェクトごとにカスタマイズ（Riku のスタック別定義など）が
あり得るため、コピーによる独立性を保つことが適切と判断した。
この非対称性（スキル=リンク、エージェント=コピー）は欠陥ではなく**意図的な設計**である。

## Consequences

### 良くなること

- `git pull` するだけで `~/.claude/skills/` 以下のスキル定義が即時更新される（再インストール不要）
- スキル定義の「正本」が agent-crew に一元化され、ドリフトが発生しない
- SKILL.md の変更履歴が agent-crew の git log に集約される

### 受け入れるトレードオフ

- agent-crew が clone されていない環境ではスキルが読み込めない（CI/CD、新規マシンの初回セットアップ前など）
- 複数マシンで clone パスが異なると symlink が壊れる（clone パス規約の遵守が必要）
  - 規約: agent-crew は `$HOME/Workspace/agent-crew` または `$HOME/workspace/agent-crew` に clone する
- スキルをプロジェクトごとにバージョン固定できない（常に最新に追従する）
- Claude Code が将来ネイティブの skill import 機能を実装した場合、このモデルは移行コストになる
  → その時点でこの ADR を Superseded に更新して移行する
