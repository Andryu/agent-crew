# P2 個人 skill 配置整理

2026-09-21。対象は `travel-itinerary-artifact`、`travel-plan-review`、`life-planner`、`life-plan-review` の4件。開発 repo の `.agents/skills` から個人用途のコピーを外し、旅行は既存 global synced 配布、life は既存 Claude 正本を global Codex へ directory symlink で渡す。Claude の公開 plugin、生成済み synced skill、`.claude/skills` 正本は変更しない。

代替案として repo コピーを残す方式は、開発 repo での常時発見と二重配布が残るため採らなかった。global の旅行 skill を repo 版で置換する方式は、生成物の管理元を確認できておらず再生成で上書きされ得るため採らなかった。life の global 実ファイルコピーも正本との再分岐を生むため symlink を選んだ。

適用前に repo の各ファイルと Claude 正本の SHA-256 一致、旅行2件の repo 本文と synced 版の追加 frontmatter より後のバイト一致を確認した。`~/.agents/skills/life-plan-review` は `references/` だけの空 directory で、`life-planner` は不存在だった。移動前に [manifest と旧コピーの退避先](../codex-direct/legacy-personal-skills/README.md) を作り、同名 global path が非空へ変わっていないことを再確認してからリンクを設置した。

適用後は4件の退避ファイルを manifest と再照合し、life の global symlink 2件が Claude 正本を指すことを確認した。各 life skill の `references/` は正本と同じ directory 内にある。元の `.agents/skills` 4件は存在せず、旅行2件は global synced にある。旧コピーの SHA-256 と復旧手順は manifest/README に固定した。

当初の残る検証は新しい Codex runtime と App surface で4件がそれぞれ一経路として発見されるかだった。後続のapp-server APIとユーザー手動App表示確認の結果は下記に記録する。旅行 synced 版の二重 frontmatter と runtime 表現は配布元を確認してから判断する。今回の発見確認を旅行プラン作成・ライフプラン計算の成功と扱わない。

## 独立レビュー証跡

親が静的配置の仕様レビュー `/root/p2_personal_spec` と品質レビュー `/root/p2_personal_quality` の `APPROVED` を確認し、採用した。レビュー対象の SHA-256 は本計画 `db2dfb80607f2f8af85a289348c55f90b5e9971514d4a4d1e931dc3e62039763`、退避 README `4c33caae727b222358fb17552cc890715b5ea723ffff28b642af6dad82b95394`、manifest `1541f15b510890084abc9260a03a52a20ec3d631db9129e9ba6e44f2da5f76f8`。本節の追記により計画ファイル自体の hash は変わる。実機発見はこのレビュー範囲に含めない。

## 実機発見の未完と配置の再変化

公式 [Codex App Server 文書](https://learn.chatgpt.com/docs/app-server) にある `initialize` → `initialized` → `skills/list` (`forceReload: true`) の手順を使い、新規 app-server プロセスで読み取り確認を試みた。sandbox 内では `~/.codex` の SQLite 状態領域を初期化できず、`initialize` 応答前に exit 1 となった。sandbox 外の再試行は承認待ちのまま中断され、`skills/list` の結果は未取得。LLM の turn、業務 skill の実行、App UI 操作はしていない。

その後、repo の `.agents/skills` に対象4 directory が同日20:15:31の timestamp で再出現した。全4件のファイル集合と SHA-256 は manifest の退避済み旧コピーと一致し、退避先も残っている。こちらの検証操作では復元しておらず、再生成元は未特定。再出現時点では repo と global に重複があり、上記静的 `APPROVED` の配置状態が一時的に成立しなくなった。新規 CLI/App の発見試験は配置を固定した後に実施する。

親の指示で、再出現した4件を移動直前に manifest の全ファイル集合・SHA-256 と再照合し、[再出現分の別退避先](../codex-direct/legacy-personal-skills/README.md#2026-09-21-201531-に再出現した同一コピー)へ移した。移動後にも hash 一致と repo 元 path の不存在を確認した。生成元は引き続き未特定。CLI/App runtime discovery は別担当へ引き渡し、この担当では再試行しない。

## 新規 app-server API の実行結果

Herdr実装pane `wC:pV`で新しいローカルapp-serverを起動し、`initialize` → `initialized` → `skills/list`（`forceReload: true`）を元repoとPR cloneの両cwdで実行した。モデルturnは開始していない。対象4件はいずれのcwdでも各1件・enabled・user scopeで、target parse errorと全体errorは0件。life 2件はglobal symlinkの実体である`.claude/skills/`正本、旅行2件はglobal synced pathとして返った。新server終了後も元repoの`.agents/skills`に対象4 directoryは戻っていない。これは**app-server API結果**。別agentのApp UI正式toolアクセスは安全理由で拒否された履歴を保持し、その後ユーザー本人が新規チャットの候補4件を各1件表示と手動確認した。本人のUI確認をAPI結果と分けて[短い証跡](../codex-direct/p2-skills-app-server-evidence.md)に記録した。業務skill実行の成功は未検証で、再出現元も未特定のまま。
