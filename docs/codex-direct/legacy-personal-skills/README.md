# 個人 skill の旧 repo コピー

P2（2026-09-21）で `.agents/skills` に置かれていた個人用途の4件を `repo-copies/` へ移した。元ファイル別 SHA-256、配布元の SHA-256、移動前の global 状態は [manifest.json](manifest.json) に記録した。ここは skill 自動発見対象外の保管場所であり、配布元ではない。

| skill | 現在の有効経路・管理正本 |
|---|---|
| `travel-itinerary-artifact`, `travel-plan-review` | 既存の `~/.agents/skills/synced/f7e17f12-e1d9-44d7-9c37-64ebdfa87f55_9c189045-f860-4394-8654-1d102988125f/` にある同名 skill。synced 生成物は編集しない |
| `life-planner`, `life-plan-review` | `~/.agents/skills/` の同名 directory symlink → この repo の `.claude/skills/` 同名正本。相対 `references/` も同じ directory 内で解決する |

旧 `life-plan-review` global path には `references/` のみを含む空 directory があった。ファイルがないことを直前に確認し、`preexisting-global/life-plan-review/` へそのまま移動してから symlink を設置した。既存の `~/.claude/skills/life-planner` symlink と `~/.claude/skills/life-plan-review` directory は変更していない。

退避元へ戻す場合は、現在の global symlink が上表の正本を指すこと、復元先が空いていること、[manifest.json](manifest.json) と退避ファイルの hash が一致することを先に確認する。次に global の symlink 2件だけを取り外し、`preexisting-global/life-plan-review` を元の global path へ戻す。repo の4件を戻す場合は `repo-copies/` の各 directory を `.agents/skills/` へ移す。既に同名のファイルや directory がある場合は停止し、上書きしない。

旅行2件の synced 版には、repo コピーと同じ本文の前に frontmatter がもう1つある。配布元を未確認のため今回は手を加えていない。この二重 frontmatter と runtime 表現が discovery や使用時に与える影響は別途確認する。今回確認したのは静的なファイル配置、hash、参照パスであり、新規 CLI/App context での発見や旅行・金融業務の実行成功ではない。

## 2026-09-21 20:15:31 に再出現した同一コピー

移行後、repo の元 `.agents/skills` に4件が再出現した。調査で生成元は特定できず、外部同期や別セッションが原因とは断定しない。元 directory の全ファイル集合と各 SHA-256 が [manifest.json](manifest.json) の `repo_legacy_originals` と完全一致することを移動直前に確認し、`reappeared-20260921-201531/` に別件として移動した。移動後も同じ hash を確認した。最初の `repo-copies/` と manifest はそのまま保持した。再出現分を復元する場合も、対象 path が空いていることと manifest との一致を先に確認する。

## 新規 app-server の読取り結果

同日のHerdr実装pane `wC:pV`から新しいローカルapp-serverを起動し、`initialize` → `initialized` → `skills/list`（`forceReload: true`）を元repoとPR cloneの両cwdで実行した。4件は両cwdとも**各1件、enabled、user scope**で発見され、対象のparse errorと全体のerrorはいずれも0件。life 2件はglobal directory symlinkの実体である`.claude/skills/`の正本path、旅行2件はglobal synced pathとして報告された。App UIの正式toolアクセスは安全理由で拒否されたが、その後ユーザー本人がApp新規チャットの候補4件を各1件表示と手動確認した。API結果と本人のUI確認は別の証拠で、[短い証跡](../p2-skills-app-server-evidence.md)に記録した。モデルturnと業務skill実行は未実施。新app-server終了後もrepo元`.agents/skills`の4 pathは不存在。再出現元は依然未特定で、将来の再出現がないことまでは証明しない。
