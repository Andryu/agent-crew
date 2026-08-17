# レーンC: Codex CLI（ChatGPT Plus / gpt-5.6-sol）2026-08-17 実測

ハーネス: codex exec（headless, sandbox=workspace-write, reasoning=medium, model=gpt-5.6-sol）。
CODEX_HOME はクリーン環境（auth.json のみ）。holdout・元リポジトリ・GitHub 参照なし。
採点シード 7 / 88 / 20260817、全一致。solved@1（1発、best-of-N なし）。

| タスク | 難度 | Codex | 参考: Max/Opus |
|---|---|---|---|
| 01-token-dept-order | 易 | 6/6 | 6/6 |
| 03-task-completed-hook | 易 | 9/9 | 9/9 |
| 05-lessons-set-status | 中 | 9/9 | 9/9 |
| 07-lessons-to-vault | 中 | 10/10 | 10/10 |
| 10-subagent-tokens | 難 | 10/10 | 10/10 |
| 12-rule-candidates | 難 | 10/10 | 10/10 |
| **合計** | | **54/54 (100%)** | **54/54 (100%)** |

含意:
- **この6問では Codex(Plus, $0=定額枠内) は Max/Opus と同点**。→ 実装をこの難度帯で Codex に
  寄せても品質は落ちない、が実データで裏づけられた（Artifact の「実装=Codex に外出し」方針を支持）
- 天井に張り付いているため、Codex と Opus の差はこの問題セットでは測れない。差を出すには
  さらに難しい問題（数日級の #33/#37/#142 系の分割、または探索的デバッグ主体の問題）が要る
- 次に効く比較は「安いレーン」= gemma4 ローカル(A)・GLM(F)・Kimi K3(G)。ここで初めて差が出るはず

セットアップ記録: Codex は Homebrew cask 0.147.0。code-mode-host が com.apple.quarantine で
起動不可 → `xattr -dr com.apple.quarantine` ＋ /opt/homebrew/bin への symlink で解消。
model は設定の gpt-5-codex が ChatGPT アカウント非対応 → 現行 gpt-5.6-sol を使用。
