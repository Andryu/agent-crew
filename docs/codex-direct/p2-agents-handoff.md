# P2 旧Codex agent定義の引継ぎ境界

2026-09-21。P2検証とPRの採用対象は移行用のPR clone。cloneの`.codex/agents/`で有効な定義は`direct-reviewer.toml`のみ。旧17件は`docs/codex-direct/legacy-agents/`へ退避した開始版で、現行の有効定義ではない。

元repoの作業treeには同日20:15:31に旧17件が再出現し、現在も保持されている。退避manifestとのSHA-256照合では15件一致、次の2件は差分がある。**元repoの現在定義を退避版と同一とは扱わない。**

| path | 元repo現在SHA-256 | clone退避版SHA-256 |
|---|---|---|
| `.codex/agents/critic.toml` | `44f3f93b7b904751b44e57387f686d4e9079e15e1fcefb8cf57d5fce4d19455c` | `7a0ba028d51c75de568fa70beab6a791476428e2fd841996e9794d462076e420` |
| `.codex/agents/pm.toml` | `e47740c9eff6da60fb9e18fa20c07859a9552ba80484279c544a91d06a179ff9` | `448a9b71ca56625941b3be2ba33fcfac2fe3c21f00cffa21034d49eda8fffbce` |

生成元は限定調査で未特定。ユーザーは別paneでの更新有無について「わからない」と回答しており、生成元の証明や旧17件削除の新しい許可ではない。元repoの旧17件（差分のある2件を含む）は変更・削除せず保持し、cloneのactiveへ再コピーしない。元repoで旧17件が除去されたと報告しない。P2のruntime/PR判定はcloneの採用定義を対象とし、この元作業treeとの差異を添える。業務agentの実行成功はこの照合から推定しない。
