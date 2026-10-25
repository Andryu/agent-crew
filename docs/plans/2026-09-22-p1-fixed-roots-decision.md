# P1 権限profileの固定repo境界

2026-09-22。P1のglobal設定適用前に確定する設計判断。対象はCodexのローカルcommand権限であり、MCP・connector・Web・承認済み昇格の権限を代替しない。

## 問題と証拠

現行原本の`developer`は`:workspace`を継承し、`:workspace_roots`の`.codex`と`.agents`へwriteを明示する。公式[Permissions](https://learn.chatgpt.com/docs/permissions)では、このルールはprofile定義rootだけでなく実行時rootにも適用される。rootがホームの場合、通常profileからglobal設定へ届き、`maintenance`だけがglobal設定を編集するという境界と矛盾する。

CLI 0.155.1の一時ディレクトリ実験では、組込`:workspace`は子`.codex`へのwriteを拒否したが、名前付きprofileの`extends = ":workspace"`は、明示overrideがなくても許可した。これは公式記述と異なる観測であり、公式記述だけを安全証明にしない。`extends = ":read-only"`に絶対rootのwriteを加えた対照群は、そのroot内だけwriteでき、兄弟rootは拒否した。名前付き`maintenance → developer → :read-only`では親子のwriteが合成され、兄弟rootは拒否された。`:tmpdir = "write"`は隔離したTMPDIRをwrite可能にした。これらは一時領域でのcommand canaryであり、全業務commandの互換性検証ではない。

レビュー1回目差戻し後の隔離canary（CLI 0.155.1、`codex sandbox -P`、一時`HOME`/`CODEX_HOME`、実globalは不使用）では、次を観測した。

- `extends = ":read-only"`＋絶対repo root writeでも、root直下の`.git`、`.codex`、`.agents`は明示ruleなしでwrite拒否された（`git commit`も失敗）。子pathの明示ruleはこれを上書きし、`.git = "write"`でcommitとhook dir writeが通り、maintenanceの`.codex = "write"`はdeveloperの`.codex = "read"`を上書きした。
- 原本をcomposerで一時HOMEへ合成した設定（`:tmpdir`/`:slash_tmp`行だけ除外。一時HOMEが`/tmp`配下で交絡するため）で、developerはrepo file・commit・`.git/hooks`・cacheをwriteでき、repo `.codex`・`.agents`・global `~/.codex`・`~/.claude`・兄弟repo・`~/Workspace`直下は拒否。maintenanceは加えてrepo `.codex`とglobal保守先をwriteでき、`.agents`と保守先以外の`~/.codex`は拒否。reviewはすべて拒否。`:tmpdir`/`:slash_tmp`は別canaryで隔離TMPDIRと`/tmp`だけwrite可能、`/private/var`は拒否。
- repo root直下以外の入れ子`.codex`（例: `.worktrees/<name>/.codex`、`sub/.codex`）は、上記の原本だけではdeveloperでwrite可能だった。repoをtrust済みにした一時HOMEで、developerがrepo内worktreeの`.codex/config.toml`へdeveloper profileの追加writeを書くと、そのworktreeを起点とする次回実行で兄弟repoへのwriteが許可された（権限拡大を確認）。repo外（`/tmp`等）に作ったworktreeの`.codex`も同様にtrust済みproject設定として読まれ、権限を広げた。developerは`.git`と`:slash_tmp`/`:tmpdir`をwriteできるため、この経路を自力で作れる。
- CLIのglobは`deny`だけを受け付け、`read`指定は設定エラーになった。`"/**/.codex" = "deny"`は、入れ子・repo外での`.codex`の新規作成、rename、symlink作成を拒否した。repo直下`.codex`の正確path read、maintenanceの正確path writeとglobal保守先writeは維持された。一方、**既存の入れ子`.codex`配下のfileはwriteでき、dirの削除もできた**。`"/**/.codex/**" = "deny"`を足すと既存配下のwriteも拒否できたが、正確pathの例外が効かなくなり、developerを継承したmaintenanceのrepo `.codex`・global保守先・private台帳へのwriteがすべて拒否された。
- 親の隔離canary（`/private/tmp/p1_sibling_profile_canary.py`で再現可能）では、developerを`:read-only`＋repo root・`.git` write＋`"/**/.codex/**" = "deny"`＋repo `.codex`/`.codex/config.toml` readとし、maintenanceをdeveloper非継承の`:read-only`基底にしてrepo root・`.git`・`.codex`とglobal保守先を明示writeにすると、developerは通常repo write可、既存・新規の入れ子`.codex`、root `.codex`、global configへのwriteは拒否された。maintenanceはroot `.codex`とglobal configへwriteできた。denyはdeveloperのroot・入れ子`.codex`配下の**読取りも拒否**した。
- `extends`を省略した名前付きprofileは、`-P`で選択するとCLIがabort（exit 134、出力なし）し、制限基底として動くことを確認できなかった。非選択時は他profileの起動を妨げなかった。

## 決定

- globalの`developer`は`:read-only`を基底とし、公開repoの`~/Workspace/agent-crew`、既存のcache、`:tmpdir`、`:slash_tmp`だけをwrite可能にする。ネットワークは既存の明示設定を保つ。非公開wealth repoの物理配置は公開原本へ書かず、P4でwealth側のproject設定レイヤーに同名profileのrepo固有writeを追加・検証する。その設定を適用するまではwealthを通常profileでwrite可能と扱わない。
- `developer`はrepo内の`.git`を明示writeし（CLIの既定保護ではcommitできないため）、repo直下`.codex`を明示readにする。さらに`"/**/.codex/**" = "deny"`で、既存・新規の入れ子、repo外、root、globalの`.codex`配下を拒否する（読取りを含む）。repo `.codex`は次回起動時の権限を決めるため、通常profileから書き換えさせない。`.agents`はCLIの既定保護でread-onlyのまま（developer/maintenanceともwrite不可。必要なら別途判断）。
- `maintenance`はdeveloperのdenyを継承しないよう`:read-only`基底の兄弟profileとし、repo root・`.git`・`.codex`、既存cache、`:tmpdir`、`:slash_tmp`、既存のglobal設定・原本保守先を明示writeにする。networkは明示的に有効。
- 運用制約: developerのsandbox内commandは`.codex`配下（repo直下、入れ子、global `~/.codex`）を読めない。composerのpreview、hook stateの確認、`.codex`の内容を読むscriptはmaintenanceで実行する。Codex自身の設定ロードがsandbox起動前に行われ、denyの影響を受けないことは未確認（CLI canaryでdeveloperの起動自体は成功した）。`review`は`:read-only`を維持する。`:workspace_roots`へのwriteはこれらの原本に置かない。
- developer/maintenanceのfilesystemはcomposer実行時に固定allowlistと完全一致させ、広げる変更は原本とcomposerの同時変更・レビューを要する。
- 新しいrepoは別途明示してproject設定でopt-inする。repo外の別場所に作るworktreeは対象外で、その作業に限定した別権限を要する。隔離cloneやP5 fixtureはこのglobal profileの検証対象と混同せず、その作業に限定した権限で扱う。
- この境界はglobal設定とrepo直下・入れ子の`.codex`を通常profileから守るための決定であり、repo内の自己変更を無害と証明するものではない。残余リスク: (a) `.git/hooks`・`.git/config`（`core.hooksPath`、alias、fsmonitor等）の変更は後続のgit操作（maintenanceや利用者のsandbox外実行を含む）でコードを実行しうる。(b) hookやlauncherが実行するrepo内script（`scripts/`、`.claude/settings.json`等）と`AGENTS.md`/`CLAUDE.md`は編集でき、次回sessionの挙動を変えうる。(c) 既存の入れ子`.codex`（2026-09-22時点でagent-crew内に`.claude/worktrees/game-ideation/.codex`、`.claude/worktrees/research-ai-video/.codex`、`docs/codex-direct/backups/shared-*/.codex` 2件）への書込みは、`/**/.codex/**` denyにより隔離canaryで拒否された。ただしdir自体の削除・rename、`.codex`以外の名前で設定を読む経路、CLI更新による挙動変化は未確認で、本profileはglobal設定の保護を完全には保証しない。公開・設定変更時は独立レビューを続ける。
- 運用停止条件: 実HOMEでのprofile canary（developerの入れ子・root・global `.codex` write拒否、maintenanceの限定write）が隔離canaryと異なる場合は適用しない。developer実行後に想定外の`.codex`変更が見つかった場合、CLI更新でglob・既定保護・trust解決・設定ロード順の挙動が変わった場合も停止し、canaryを再実施する。

## 代替案

`:workspace`を維持してglobal設定だけ絶対denyする案は一時実験で有効だったが、実行時rootがホームならそれ以外のホーム領域へのwriteが広がる。起動cwdの運用規律にも依存するため採らない。すべてのrepoへ一律writeする案も、今回の対象2repoという境界に合わない。非公開wealthの配置を公開global原本に列挙する案は公開範囲に合わない。wealthのproject設定レイヤーで同名profileを拡張する案をP4の検証対象とする。

## 適用条件と未検証点

1. 既知旧原本と新原本、合成後所有区画のhashを更新し、markerなし移管のpreview・apply・recover・初回rollback拒否のfixtureを通す。公開原本自身について、`developer`の固定agent-crew root以外へのwrite、`:workspace_roots` write、global `~/.codex` write、wealthの非公開物理pathの再導入をテストで拒否する。
2. **global適用より前に**、agent-crewのGit rootとgitdirが許可root内にあることを確認し、新profileのCLI canaryでrepo内の通常write、`.git`更新、TMPDIR、cache、global設定への通常profileからのwrite拒否、repo直下`.codex`の通常profile拒否とmaintenance上書き、maintenanceでの限定global writeを確認する。隔離環境での同canaryは上記のとおり通過済み。実HOMEでの確認は管理者が行い、期待と異なれば実適用を停止する。ネットワークの実効許可は別canaryで確認する。wealthのproject設定レイヤーとそのGit rootの実機確認はP4の必須条件とする。
3. 仕様と品質を新規コンテキストで独立確認する。同一変更集合のレビュー往復は最大3回とし、差戻しが残れば実適用を止めて管理者判断へ戻す。
4. globalの直前bytes/hashを再採取し、read-only previewで既知旧区画・所有外意味木・合成後hashを確認してから、同じ期待値でapplyする。観測間にhashが変われば自動追従せず停止する。初回rollbackは禁止なので、実適用後に互換性問題が出た場合の前進修正とprivate backupによる手動復旧境界を記録する。

未検証: trust解決がworktreeを親repoへ対応付ける正確な規則（実global設定のagent-crew root自体は`trusted`と確認）、既存入れ子`.codex`以外の自己変更経路の網羅、実repoの全commandとの互換性、loopback以外のネットワーク挙動、repo外worktreeや別checkoutの権限（対象外）、CLI更新後の継承・既定保護の挙動、`extends`省略profileの正式な基底。P5の隔離比較はglobal profileを無効化しているため、その結果を本設計の実機証拠にしない。

## 2026-09-22 実適用結果

修正原本を一時`CODEX_HOME`へ読み込み、隔離HOMEと実HOMEでdeveloperのrepo・`.git` write許可、root・既存/新規入れ子`.codex`とglobal設定のwrite拒否、maintenanceのrepo `.codex`とglobal保守先write許可を確認した。実HOMEではdeveloperのloopback通信許可、reviewの通信拒否も確認した。検証には一意な一時ファイルだけを使い、既存global・project設定のhashは不変だった。仕様・品質の独立レビューは2往復でAPPROVED、関連59テスト成功。

global対象は直前全bytes SHA-256 `05b5faccf46dd8db504521428ea103c4254c4c1198fdcbad136e6ebc564186a5`で固定し、`--adopt-legacy-unmarked`のread-only preview後、同じ期待hashでapplyした。結果は`applied=true`、generation 1、適用後全bytes SHA-256 `18e71587f6f82216aab22edcc2be506eea203900e71b517f0106ac4c0741d506`、合成後所有区画 SHA-256 `9db64c8657083c7527ffc452994f7e59cd210d9da7ec910cfbda5e70e647d054`。所有外意味木hash `57310b3ba2fdb72bb31c99b794e839af9bcd29172eaeaa453db5aebc2e00727a`はpreviewとapplyで一致。再previewは`changed=false`。適用後の実globalを使うCLI canaryも同じ境界で成功した。初回rollback禁止と上記残余リスクは継続する。
