# P2a 指示・agent整理

## SPEC

Codexの通常開発をメイン主体にし、重要な設計と変更だけに計画・独立検証を求める。既存のqueue、完了ガード、外部操作の承認境界、他セッションの差分保持を維持する。Claude側のagent/skillとhook実装は対象外。

## PLANと代替案

- 旧routingを残してAGENTSで上書きする案: 二重の指示が続き、skill自動発動時に再び強制委譲するため不採用。
- Codex側skillを短い工程ガイドに改訂し、旧agentをhash付きで退避する案: 安全条件を残しつつ自動発見の誤用を防げるため採用。復元にはmanifestを使える。

完了条件: 常設指示とskillが同じ適用基準を示す。旧17 agentが退避され、direct-reviewerは残る。重要変更の二観点レビュー、SPEC/PLAN、承認境界、queue guard、他者差分保持が読める。内部リンクが実在する。親による独立レビューを受ける。

## 作業と検証

対象は`AGENTS.md`、Codex側`.agents/skills/fable-class`の4文書、`docs/codex-direct/README.md`の指示・agent節、旧agent退避先。旧4文書は編集前に`/private/tmp/p2-original-fable/`へ保存した。Claude版、scripts、config、hooks、queue、global設定は編集しない。

検証はskill validator、旧routing文脈、内部リンク、hash一致と件数、差分の安全条件を確認する。実行後の結果と未検証範囲を追記する。

## 実施結果

- `quick_validate.py .agents/skills/fable-class`: `Skill is valid!`
- 退避manifestの17件すべてSHA256一致。`.codex/agents/*.toml`は`direct-reviewer.toml`のみ。
- 旧routing語は現行指示では否定・解除の文脈に限定。旧調査記録のREADME本文には当時の記述を残し、冒頭に現在との区別を追加。
- 本P2aの実行時動作とCLI/Appの新規contextでの発見結果は未検証。親の独立レビューとP2統合検証を待つ。

## 起動入口のPython要件（2026-09-22追記）

- `scripts/crew`とそれがimportする`codex_hook_state.py`は`tomllib`を使うため**Python 3.11以上**が必要。関連テストはPython 3.12で実行する。
- shebangは`#!/usr/bin/env python3`のまま。macOS標準`python3`（3.9.6）で直接起動された場合は、PATH上の`python3.13`→`python3.12`→`python3.11`へ一度だけ再実行する（環境変数`CREW_PYTHON_REEXEC`で再帰を防ぎ、起動するclaude/codexへは渡さない）。見つからなければimport前に`crew: Python 3.11以上が必要です`でexit 1。
- 検証: 直接の`scripts/crew --print-command codex`と`claude`が成功。`tests/test_crew_launcher.py`に3.9からの直接起動（claude分岐の成功で切替を証明。codex分岐はrepo固有のhook state sidecarに依存し公開cloneには含めないため、`launch_spec`のunit testで検査）と、3.11+がないPATHでの明示停止のtestを追加（3.11未満のpython3がない環境ではskip）。
