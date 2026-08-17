# レーン0: Claude Max / Opus 4.x（2026-08-17 実測）

8/18 の Max 終了前に取得した「消える基準線」。ハーネスは Claude Code サブエージェント
（general-purpose, model=opus）。holdout・元リポジトリ・GitHub 参照は禁止して隔離。
採点はシード 7 / 88 / 20260817 の3回、全シード一致。

| タスク | スコア | 備考 |
|---|---|---|
| 01-token-dept-order (PR#170) | 6/6 (100%) | 両ファイルの DEPARTMENTS 一致まで満点 |
| 03-task-completed-hook (PR#98) | 9/9 (100%) | |
| 05-lessons-set-status (PR#74) | 9/9 (100%) | |
| 07-lessons-to-vault (PR#123) | 10/10 (100%) | |
| **合計** | **34/34 (100%)** | |

含意:
- 易〜中の4問では天井=100%。上位モデル間の弁別には難問（10/11/12）が必要
- 以後のレーン（Pro/Sonnet・Codex・gemma4・GLM・Kimi）はこの 34/34 と比較する
- 注意: 厳密には「Claude Code + agent-crew」ハーネスではなく素の Claude Code サブエージェント。
  agent-crew 工程込みのレーンDを測るときは条件差を明記すること
