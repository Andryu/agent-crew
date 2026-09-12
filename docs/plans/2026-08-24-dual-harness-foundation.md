# Dual-harness foundation plan

Date: 2026-08-24  
Status: implemented

## Context

Claude Code と Codex を同じ `agent-crew` で運用するための最初の共通基盤を置く。個人ベンチの
実測では両者の能力差は検出できず、Claude Pro では利用枠が先に制約になった。したがって、
役割分担は能力の序列ではなく、工程と利用枠に基づける。

Obsidian の `hybrid-ai-stack` と `handoff-design` を参照した。会話履歴ではなく短い作業状態
（6節）と機械生成 Evidence を引き渡し、repo / Git / テスト結果を真実源とする。

## Decision

1. ルート `AGENTS.md` を Claude Code と Codex の共通作業契約にする。
2. `.agents/skills/dual-harness/SKILL.md` を両ハーネスで共有する手順の正本にする。
3. Codex の hook は Git root を解決して既存の安全なスクリプトを呼ぶ。`CLAUDE_PROJECT_DIR` へは依存しない。
4. hook 定義は nested directory から実行する回帰テストで検証する。
5. 利用枠を契機とする自動フェイルオーバー、ベンチランナー統合、ダッシュボード送信は導入しない。

## Alternatives

- Claude 設定を Codex 用に複製する: 実行形態と権限モデルが異なり、環境変数依存が再発するため採らない。
- 最初から自動フェイルオーバーする: quota、認証、ネットワーク、timeout の誤分類が危険であり、手動承認の実証後まで保留する。

## Scope

1. `AGENTS.md` の共通契約
2. 共通 `dual-harness` skill
3. `.codex/hooks.json` とその回帰テスト
4. README の Codex 起動・trust 手順
5. この計画書

PR #188 が main に入る前提となる bench の実行・handoff runner は含めない。

## Verification

- `jq empty .codex/hooks.json`
- `uv run pytest -q tests/test_codex_hooks.py tests/test_dashboard_emit_event.py tests/test_dashboard_scripts.py`
- `git diff --check`

## Risks and guardrails

- 規約だけでは守られないため、root 解決は静的検査と実行テストで保証する。
- Bash の失敗を隠さないよう、hook の安全策は既存の best-effort 終了処理に限定する。
- 未実証の機能を稼働中として README に記載しない。
- ADR-012 に従い、運用手順の正本は `.agents/skills/dual-harness/` の一箇所に置く。
