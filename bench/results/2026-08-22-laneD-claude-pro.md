# レーンD: Claude Pro / Sonnet 5（2026-08-22 実測）

8/19 に Max → Pro へ移行した後の実力を、レーン0（Max/Opus 54/54）と
レーンC（Codex/Plus 54/54）と同じ6問で測る。
ハーネスは `claude -p`（headless, --model sonnet, --permission-mode acceptEdits）。

| タスク | 難度 | スコア | 品質減点 | 備考 |
|---|---|---|---|---|
| 01-token-dept-order | 易 | 6/6 (100%) | 0 | |
| 03-task-completed-hook | 易 | **0/9** | — | **環境要因**（後述） |
| 05-lessons-set-status | 中 | 9/9 (100%) | 0 | |
| 07-lessons-to-vault | 中 | 10/10 (100%) | 0 | |
| 10-subagent-tokens | 難 | 10/10 (100%) | 0 | 根本原因の発見を要する問題も満点 |
| 12-rule-candidates | 難 | **2/10** | — | **5時間枠に到達して中断**（後述） |
| **有効な4問の合計** | | **35/35 (100%)** | 0 | 01/05/07/10 |

## 結論

**能力の面では Sonnet は Opus と差が出なかった。** 完走できた4問（易2・中1・難1）はすべて満点で、
品質チェック（shellcheck・構文・重複定義・過剰実装）の減点もゼロ。
難問10（サブエージェント別トークン集計＝症状から根本原因を特定する問題）を満点で解いている点は
特筆に値する。

**差が出たのは能力ではなく「枠」と「権限」だった。**

## 1. 枠切れ（今回いちばん重要な発見）

6問目（難問12）の途中で `You've hit your session limit · resets 12:50pm (Asia/Tokyo)` に到達。
**Max では6問を余裕で完走できたが、Pro では5問completed + 6問目の途中で5時間枠が尽きた。**

- 枠切れの言及があったのは 12-rule-candidates のログのみ（他5問は完走）
- つまり **Pro の5時間枠 ≒ このベンチ5問強**が目安。1問あたり中〜難で 30分〜1時間相当の作業
- ADR-018 の「実装を Codex に外出しする」判断は、**能力差ではなく枠の消費速度で正当化される**
  ことが実データで確認できた

## 2. 権限（ハーネス比較として有用な副産物）

03-task-completed-hook が 0/9。ログには
`.claude/hooks/` への書き込みが拒否され、モデルが「許可設定を追加してから再試行するようご指示ください」
と述べて終了している。**モデルの能力ではなくヘッドレス実行時のツール権限の問題。**

- Codex（`--sandbox workspace-write`）と Opus（サブエージェント）では発生しなかった
- `.claude/settings.json` の permissions.allow が
  `this workspace has not been trusted` で無視されていた（33エントリ）
- **ベンチの公平性のため、レーンごとに権限設定を揃える必要がある**（今後の課題）
- 再実行は 03 のみ `--allowedTools` に `Edit(.claude/**),Write(.claude/**)` を足して行う予定
  （枠がリセットされてから）

## 3. 3レーン比較（現時点）

| レーン | 完走した問題のスコア | 枠 |
|---|---|---|
| Claude Max / Opus | 54/54 (6問) | 余裕あり |
| Codex CLI / gpt-5.6-sol (Plus) | 54/54 (6問) | 余裕あり |
| **Claude Pro / Sonnet** | **35/35 (4問)** | **5問強で5時間枠が尽きる** |

→ **「Pro に落ちて失うのは賢さではなく回数」**。実装を Codex に寄せ、Claude Pro は判断・設計・
critic・Notion/Artifact/Chrome に温存する、という ADR-018 の設計はこの数字で裏づけられる。
