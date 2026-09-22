# P2 個人4 skillのapp-server API発見証跡

2026-09-21 22:26 JST。`python3.12 /private/tmp/p2-skills-discovery.py`を実行し、exit 0。スクリプトSHA-256は`ee426f876ca414bcbf74f0887ff09da4b58979e4affcf71c86a36bc9da27806e`。新規ローカルapp-serverへ`initialize`→`initialized`→`skills/list`（`forceReload: true`、cwdは元repoとPR clone）を送った。モデルturn・業務skill実行なし。

| 対象skill | 元repo | PR clone | APIが返した配布元 |
|---|---:|---:|---|
| `agent-crew:life-plan-review` | 1件 | 1件 | 個人`user` scope、`.claude/skills`正本 |
| `agent-crew:life-planner` | 1件 | 1件 | 個人`user` scope、`.claude/skills`正本 |
| `travel-itinerary-artifact` | 1件 | 1件 | 個人`user` scope、global synced |
| `travel-plan-review` | 1件 | 1件 | 個人`user` scope、global synced |

全8結果は`enabled: true`。対象parse errorは両cwdで0件、APIの全体errorも両cwdで0件。4skillの件数・scope・有効状態・配布元にsource/clone差はない。実行後のread-only確認でも両repoの`.agents/skills`に旧4 directoryは存在しない。global skill sourceや個人global `AGENTS.md`は変更していない。

これは**app-server APIの発見結果**である。App UIの正式toolアクセスは安全理由で拒否された履歴があり、こちらのtoolではUIを確認していない。その後、ユーザー本人が**Codex App新規チャットのスキル候補**を手動確認し、`life-planner`、`life-plan-review`、`travel-itinerary-artifact`、`travel-plan-review`が各1件表示されたと回答した。これはユーザーによるApp表示確認であり、上記API結果とは別の証拠。旧17agent再生成に別セッションが関与したかについて、ユーザーの回答は「わからない」。再出現元の特定や将来の非再出現、業務skill動作は未検証。
