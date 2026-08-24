# レーン0: Claude Max / Opus（2026-08-17 実測）

8/18 の Max 終了前に取得した「消える基準線」。ハーネスは Claude Code サブエージェント
（general-purpose, model=opus）。holdout・元リポジトリ・GitHub 参照は禁止して隔離。
採点はシード 7 / 88 / 20260817 の3回、全シード一致。

| タスク | 難度 | スコア |
|---|---|---|
| 01-token-dept-order (PR#170) | 易 | 6/6 (100%) |
| 03-task-completed-hook (PR#98) | 易 | 9/9 (100%) |
| 05-lessons-set-status (PR#74) | 中 | 9/9 (100%) |
| 07-lessons-to-vault (PR#123) | 中 | 10/10 (100%) |
| 10-subagent-tokens (PR#179) | 難 | 10/10 (100%)（aiohttp ボーナスは環境対象外） |
| 12-rule-candidates (PR#182) | 難 | 10/10 (100%) |
| **合計** | | **54/54 (100%)** |

含意:
- Opus は6問すべて天井。以後の全レーン（Pro/Sonnet・Codex・Prime・gemma4・GLM・Kimi）は
  この 54/54 との差分＝「安くして失うもの」として読む
- 全問 solved@1（1発）。安いレーンは best-of-N を許すので、比較時は N を明記すること
- 注意: 素の Claude Code サブエージェントでの実測。agent-crew 工程込みのレーンDとは条件が違う
