# Codex移行 P3 引継ぎ証跡

確認日: 2026-09-21。状態: **P3完了、親受入済み**。対象は開発移行P0〜P5。P6/P7は対象外。P3完了は移行全体の完了を意味しない。

## 目的と現状

新規セッションが目的、実際の進捗、最新証跡、未解決、承認境界、次コマンドを再構成できる入口を作る。親がP0のREADME、manifest、snapshot-index、comparison、smokeを確認して受入済み。P1は実装済み・レビュー前。P2a/bは仕様準拠と品質の二観点レビューがAPPROVED、実機検証未完。P3は独立再開追試APPROVEDを親が受入済み。P4はwealth-advisorの非公開別clone `codex/development-migration-p5`で実装済み・限定34テスト成功、独立レビュー待ち。元repoは保持し、P1依存は未完。P5ハーネスはレビュー差戻し修正中で、正式24run未実施。速度改善・wealth実データ運用を完了と主張しない。次の更新では親の統合結果と実Git・検証記録を優先する。

技術正本は[移行再計画](2026-09-21-codex-operating-model-replan.md)、[P0受入証跡](../codex-direct/migration-baseline/README.md)、各repoのGit・plan・テスト記録。手順は[引継ぎ](../codex-direct/handoff.md)。横断入口は非公開Vault資料で、目的とリンクを持つ。元の移行再計画の「提案、設定未適用」は計画作成時点の状態であり、現在のphase進捗はこの証跡と現行Gitを優先する。過去のwealth運用準備記録は実資産運用済みの証拠ではない。

## この担当の回復確認

親からの作業範囲を受けた別コンテキストで、既存のVault入口、共有保存契約、repoの移行再計画8・9章、repo AGENTS、Git statusから、目的と当時のP0〜P5の状態、P6/P7境界、Vaultとrepoの役割を復元した。その後のP0受入を親の連絡とrepoのP0受入証跡で確認した。資産本文・会話ログ・認証情報は参照していない。この確認は**独立fresh-session受入試験の代替ではない**。実証入力・判定条件は引継ぎ手順に記した。

## 更新・検証欄

- 引継ぎ文書: 作成済み。固定phase状態を置かず、この証跡へ誘導する。
- Vault追補: 既存の横断入口、agent-crewの過去移行状態、wealthの過去移行状態へ匿名化した参照を追補済み。Vaultの旧「設定未適用」は過去観測として維持する。
- 独立新規セッション実証: `/root/p3_recovery_check`（実装担当と別の新規context）が[引継ぎ手順](../codex-direct/handoff.md#新規セッション実証)の旧入力に沿ってVault入口、repo計画、Gitを確認。agent-crew `875dd67062d7a16fc27017965066a99303e3d0a9`、wealth-advisor `b63598f3d39944c73602dec76373b63a747b5d41`の時点で、目的・版・未完・次手は再現成功。ただし当時の引継ぎに今回のcommit/push/PR/レビュー承認がなく、それらを未許可と解釈しうるため、親は部分採用とした。承認境界追補後、別のfresh context `/root/p3_scope_recheck`が目的・両repo版・未完・承認済みcommit/push/PR/レビュー・mergeと金融P6/P7の除外・次手を正しく再現し、**APPROVED**。親も結果を受入れ、P3を完了と判定した。追試の入力全文・出力の永続証跡パスは未記録であり、親から受領した判定要約を証跡とする。
- 承認境界: ユーザーは両repoのP0〜P5について、実装・関連検証・対象を限定した差分のcommit/push・PR作成・独立レビューまで明示承認済み。これは今回の移行作業の依頼範囲であり、旧計画の一般運用案より優先する。merge、金融データを扱うP6/P7、実資産読取り、Notion更新は含まない。指定Vaultへの匿名化した引継ぎ保存も依頼済み。個々の操作では現行Git差分と対象を照合し、他者変更を混ぜない。
- 再開コマンド: `git status --short`、`git branch --show-current`、`git rev-parse HEAD`。対象テストは担当Pの最新planに記したコマンドを使う。

## 確認した版と証跡

| repo | checkout / branch / HEAD | 未コミット成果とhash | 検証・レビュー証跡 | 未解決・次の一手 |
|---|---|---|---|---|
| agent-crew（元repo、非公開） | `main` / `875dd67062d7a16fc27017965066a99303e3d0a9` | P0対象のパス別状態・SHA-256は[manifest](../codex-direct/migration-baseline/manifest.json)。P0記録自体も未追跡 | [P0 README](../codex-direct/migration-baseline/README.md)に親受入と3+12+8件成功、[smoke結果](../codex-direct/migration-baseline/smoke-result.json)。`p3_scope_recheck`はAPPROVED・親受入済み | P1レビュー前、P2実機未完、P3完了、P5正式比較未実施。統合時に再照合 |
| wealth-advisor（非公開の別repo） | `codex/operations-readiness` / `b63598f3d39944c73602dec76373b63a747b5d41` | P0対象のパス別状態・SHA-256は同じ[manifest](../codex-direct/migration-baseline/manifest.json)。README変更と複数未追跡成果あり。P4作業先は別clone | [P0 README](../codex-direct/migration-baseline/README.md)に静的fixture 6件成功。実資産・接続検証は対象外 | P4は別cloneの`codex/development-migration-p5`で実装済み・限定34テスト成功、独立レビュー待ち。元repo保持、P1依存未完 |

P0元基準ファイルのSHA-256は`manifest.json`=`db7f4406505cb5879207c1ae7889946cdfbb9f4217ab551c8ec69ae311b6d4ee`、`snapshot-index.json`=`273b627b173605014a4061e964d744fd53bc4567b70c78811993fa575a8d9e3f`、`comparison.json`=`3214b75d3a6f37cf474d167a358d5f1ed24344dfe88f6e6e11ead220b0d823e5`、`smoke-result.json`=`495e13e6aa3bc72ba71e2277a07aba110336ec48695c9827ea57de64ec0e4959`。公開cloneの匿名化派生ファイルは[公開変換台帳](../codex-direct/pr-publication-manifest.json)で元hashと公開hashを区別する。P0のC6 smokeはA/B比較ではなく、P5の24runは未実施。
