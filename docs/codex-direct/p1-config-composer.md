# P1 設定所有権統合: fixture実装と実適用前レビュー資料

2026-09-21作成、2026-09-22更新。親Astraの6受入条件を採用。P0は親受入済み。P1のglobal権限区画は下記の限定移管で適用済み。wealthのproject設定とP2のrepo hook生成設定は未適用で、統合動作の判定は残る。前版8ファイル集合`74a2500030f3cbdc00e5ceb3c34c4ac8b594698d4788ef47277dbecc46fad79c`は仕様・品質ともAPPROVED、親採用済み。

## 所有と変更順

| 所有者 | TOML key path / ファイル | 既存の兄弟区画 |
|---|---|---|
| agent-crew composer | global `approval_policy`, `approvals_reviewer`, `default_permissions`, `permissions.developer`, `permissions.maintenance`, `permissions.review` | `model`, provider, MCP, marketplace, desktop, projects,未知profileなどは保持 |
| agent-crew hook state | repo `notify`, `features.hooks`, **台帳に載せたkeyのみ**の`hooks.state.<quoted-key>` | `features.js_repl`, 未知hook entry、配列/引用符keyは保持 |
| P2共通hook | `config/crew-hooks.json`のCodex登録は`SessionStart`, `Stop`, `SubagentStop` | 旧稼働sessionの`UserPromptSubmit`はparserのno-op互換。新manifestに登録せず、旧project登録がhooks/listに残ればP1 snapshot検証は拒否 |
| wealth旧入口 | `scripts/install_codex_permissions.py`の書込み前停止 | 別clone `/private/tmp/wealth-codex-migration` のPR #13へ反映済み。元wealth repoは未変更。marker付き旧設定の移管に加え、既知のmarkerなし旧設定だけを明示移管する |

適用順: (1) wealth旧installerを停止し再実行書込みを遮断、(2) P2 installerでrepo hooks.jsonを新3件へ合成、(3) 実機の新しいhooks/list snapshotを取得、(4) 新profileの隔離・実HOME CLI canary（下記「固定repo権限profile差分」）を通過後に共通composerでglobal権限区画、(5) hook stateでrepo区画を旧schema1正当hashからschema2へ移行、(6) 新CLI contextの実効profileとhook動作を無害なcanaryで確認。各段階の対象hashを直前照合する。旧登録が残る間はhook stateが拒否し、古いsnapshotを流用しない。

## 停止・保持・復旧

- 所有区画の独自変更、TOML重複、親子所有競合、未知profileのglobal write、legacy `sandbox_mode`/`sandbox_workspace_write`を拒否する。合成とrollbackの前後で**所有外のTOML意味木が一致**することを検査する。未知multilineの内部を誤認して編集する場合も無変更で拒否する。
- 権限原本は`config/codex/permissions.toml`。developerは`:read-only`を基底に`~/Workspace/agent-crew`（repo内`.git`の明示writeを含む）、既存cache、`:tmpdir`、`:slash_tmp`だけをwriteし、repo直下`.codex`は明示readだが`"/**/.codex/**" = "deny"`で`.codex`配下は読取りも拒否、networkは明示的に有効。maintenanceはdeveloperを継承しない`:read-only`基底の兄弟profileで、repo root・`.git`・`.codex`、既存cache、`:tmpdir`、`:slash_tmp`、`~/.codex/config.toml`、`~/.codex/config-composer`などの既存global保守対象を明示writeにする。reviewは`:read-only`を継承。3profileとも`:workspace_roots`へのwriteを持たない。private repoのrootは公開原本へ書かず、そのrepoの同名developer profile layerで追加する（P4）。developerへprivate台帳の書込みは与えない。旧wealth広権限templateは移管照合専用で、新profileへコピーしない。
- 対応writerは同じ`~/.codex/config-composer/composer.lock`を取得後に再読込し、書込直前に元bytesを再照合する。`--check`/previewはロックdir・fileを作らず、対象も変更しない。非協調writerが直前照合とrenameの間に編集する競合はOS側で完全には防げないため、実適用では再照合と後続検証を行う。
- 対象`config.toml`がsymlinkなら適用・復旧・rollbackを開始前に拒否する。途中でsymlinkへ差し替わった場合もatomic writeが置換前に拒否する。台帳の対象識別と置換先がずれたまま次世代へ進ませない。
- private台帳は世代、区画before/after/不存在、変更前の全文backup（globalは秘密を含みうるためprivateのみ）、pendingを記録。pendingとrollback途中からbefore/after照合で復旧する。rollbackは所有区画が適用後と一致する場合のみ行い、他区画を保持する。**旧wealth広権限を戻す初回世代rollbackは禁止**し、途中失敗は`--recover`で新しい安全区画への適用を完了する。後続の安全な世代rollbackはfixture検証済み。旧hook schema1へ戻した場合は区画台帳schema2へ変換し、実機snapshotを更新するまでlauncherを拒否する。
- `~/.codex/rules/default.rules`（73 prefix、SHA-256 `d6a76fa25b245d084d67e1c7abb756c9a3a8c405e81aea339c1e6b9527e84ff4`）と`developer.rules`（6 prefix、SHA-256 `afdf43f48be2f2a780be0c8967e5f0cb9e97b37559c64d71618f31aa06542fd2`）は削除・上書きしない。後者はHerdr/Git/worktree/ps等の個別コマンド承認であり、named profileのglobal書込権限とは別の昇格経路。許可済みprefixでも依頼範囲外操作を認める意味ではない。

## 照合hashとfixture結果

| 対象 | SHA-256 / 結果 |
|---|---|
| global config 旧preview時の観測値 | `fd2f62102cb84114786d35075f847d6e7206db5f12afb5c5b4ba275a0cf57c53`。現在値として使わない |
| global config 旧preview結果 | `95ea995db0b18f48821b981708951341099c01a6371024035769a81323e6a57e`。dry-runはprivate台帳dir/fileも作らないことを確認。適用前に再採取・再previewする |
| global config 以前のread-only hash確認時の観測値 | `34ab515a78147a4fab6f2f2b56b75bf2977751446df8faefbca11bbb435fab10`。観測時点の値で失効。本文は出力しない。markerなし移管用の観測履歴は下記の限定移管節と計画書の表を参照 |
| agent-crew repo hook config / schema1 sidecar現状 | `4f8f3a3124dc62d9005710ff06a7b174eeb708bf1524efd07d599c5c01f96e17` / `aa1f5632ac19e23b32762151c21c949c4d2be0331a20f6294ff22f7f652f5fb0`。旧schema1の全体hash一致を確認 |
| wealth旧installer現状 | `9b89101a8f4feec6a9c74cedf3ebb8010ceaebf7040ea1c7863e96ccb42fa3c7` |
| 停止案 `/private/tmp/wealth-codex-installer-stopper.py` | `9fcde561f68941cf239a5e6a2a257da1a5d37cb622183050ab9e0fa1e16e3726`。実repoへ未反映 |

P1仕様レビュー`/root/p1_spec_review`の最初の2件（高: 未知profileの絶対path/祖先write、中: schema1移行の新user hook keyを含む復旧）は修正済み。品質レビュー`/root/p1_quality_review`の最初の3件（高: recoverの再読込による編集消失、中: symlink対象で台帳を見失う、中: project専用snapshotで未作成user hooks.jsonを要求）も修正済み。前回8ファイル集合SHA-256 `64bf47ec06be57ae9d0582c01f74b8392ed9c7353eb89d1a0ee326791b4fd778`は両review APPROVED・親採用。独立反証`/root/p1_atomic_challenge`の4条件を実装した集合`5c669cb38e307fbbdf1df29fc1acf7c8f3337a2424028092ab0807982c0f39f1`は品質reviewで新repo初回applyの回帰1件が差戻された。回帰を直した集合`74a2500030f3cbdc00e5ceb3c34c4ac8b594698d4788ef47277dbecc46fad79c`は仕様・品質の両APPROVED、親採用。以下はその後の**markerなし既知旧設定の限定移管差分**と**固定repo権限profile差分**（下記節）を含む現在の個別hashで、新たな二観点review待ち。

| path | SHA-256 |
|---|---|
| `scripts/codex_config_composer.py` | `18cb9e3aa3c057ebff07c0fcf6c08c9b36fb89437df4fee796c45a99fda987c7` |
| `scripts/codex_hook_state.py` | `5d3961c79d884d574c03759fa76be8cb505eb42d1b5117e3770b715b804c2d9e` |
| `config/codex/permissions.toml` | `7675f876d4097e7a04787d9d889ba7eab92a7888bfba923422e76b61981df76d` |
| `config/codex/legacy-developer.toml` | `17081a191d7766934a755dcab6e2d1ecb27a3ac79045399780742a73c4aaf61a` |
| `tests/test_codex_config_composer.py` | `41772af679c3f8c7c834efc6b19f24218d64e1ad5311aba06f4ba24552dd73f2` |
| `tests/test_codex_hook_state.py` | `7093f79763c3a44b731e4bdbc4ded295b084f8e3a7dcb5c5a3227d59302c3c6d` |
| `tests/fixtures/legacy_wealth_install_codex_permissions.py` | `9b89101a8f4feec6a9c74cedf3ebb8010ceaebf7040ea1c7863e96ccb42fa3c7`（移管前の旧installer本体とバイト一致） |

変更前wealth installer**そのもの**を隔離HOME/repoで`--apply`実行: exit 0、global marker・広い`~/.codex/config.toml` write・rule・repo configを生成。同じ本体を**移管後config**へ`--apply`実行: `approval_policy`競合で書込み前に拒否し、global config bytes不変、rule/repo config未作成。停止案を隔離fixtureで実行: exit 2、同じく書込みなし。実資産・認証・外部送信なし。

P1単独テストは`test_codex_config_composer.py`と`test_codex_hook_state.py`。未知兄弟/配列/引用符keyの保持、multiline/inline/dottedの競合拒否、旧schema1移行、schema2 launcher区画検証、所有改変拒否、private世代復旧、旧広権限rollback拒否、後続世代rollbackを確認。P2イベント集合については新3件snapshot受入、旧project `UserPromptSubmit`と未知project hook拒否を別testで確認。実機profileの保証はtemplateだけで完了扱いしない。`--sandbox`やconfigのlegacy sandboxがnamed permissionsを上書きし得るため、実機canaryを後続工程に残す。

差戻し修正fixture（未知profileのglobal write判定、仕様・品質final3差戻し後の現行規則）: 移行gateはfalse negativeを避けるため、未知profileの実効writeが`~/.codex`領域へ届かないと**証明できなければ拒否**する。(1) `extends`を辿り、親の明示rule・間接継承・所有profileへの継承（合成前の現値と合成後の原本の両方）を評価する。基底が`:read-only`で終わる鎖だけを評価対象とし、`:workspace`継承（直接・間接、合成前の旧`developer`経由を含む）、`extends`なし（CLI 0.155.1で選択時abortし制限基底を確認できない）、循環・不明親・未知の組込親・型不正は拒否する。新`developer`経由は`:tmpdir`等の特殊base writeを継承するため従来どおり拒否側になる。(2) 公式Permissions（利用者提示の要旨。本作業では外部取得していない）では`:workspace_roots`はprofile指定rootに加えて実行時workspace rootにも適用され、実行時rootは移行時点で未知（`~/.codex`自身や`~`もありうる）。そのため`:workspace_roots`へのwriteはflat形・nested形とも、明示rootの有無・内容（`false`、類似名、project rootを含む）によらず拒否し、`:workspace`の組込保護（workspace内`.codex`をread-onlyにする等のレビュー推測）も許可の根拠にしない。(3) pathは絶対path（`~`展開後）だけを判定し、相対base/subpath前の相対base、相対root、`$`を含むpath、`~user`展開失敗、symlink loop（`RuntimeError`）、その他の解決失敗は拒否する。絶対pathは`resolve`後に部品ごとcasefoldで比較し、`~/.codex`と同一・祖先・子孫なら拒否。nested `:root`は`/`+subpath、その他の特殊baseは拒否。`*`・`**`・`{a,b}`は`/`を跨ぎうるとみなし前方literalが矛盾しなければ拒否、1文字の`?`/`[]`は同じ深さで照合する。(4) 保持するのは`:read-only`基底で絶対pathのglobal外writeだけ（例: `~/.codex-extra`、`~/Workspace/*.md`、`/tmp/...`、`~/Workspace`配下のnested subpath、`review`継承）。**過剰拒否の想定**: 実在して安全な未知profileでも、`:workspace`継承、`developer`/`maintenance`継承、`extends`なし、workspace root相対write、相対path、`:tmpdir`等の特殊base、`~/*.md`のような広いglob、公式access（`read`/`write`/`deny`）以外の値（`none`を含む）を持てば停止する。`deny`は非writeとして扱う。実global設定の過去snapshotはより緩い判定での確認であり、限定移管のread-only previewで停止した場合は親が判断する。**仕様の不確実性**: `:workspace_roots`の実行時root集合、glob方言（`*`が`/`を跨ぐか、`{a,b}`の有無）、相対pathの基準、は公式要旨から確定できず、いずれも拒否側に倒した。accessは公式の`read`/`write`/`deny`に従う（本作業では外部取得していない）。glob部品とsymlink別名の組合せ（例: `~/c?`が`~/.codex`へのlinkに一致）と、`~/.codex`内から外へのsymlinkは検出しない。schema1からの移行で新user hook indexを追加し、sidecar pending記録後のconfig書込み前失敗とconfig書込み後のsidecar確定前失敗の両方から復旧を検証。権限writerとhook writerを同一lockで並行起動し、双方の区画と未知`model`が最終configに残ることも検証した。

品質差戻し修正fixture: recoverで読んだ同一bytesを解析・合成・書込直前照合まで使用し、解析直後に外部編集を注入すると復旧が停止して編集が残ることを検証。対象config symlinkは適用・復旧・rollbackのいずれも台帳作成やリンク置換より前に拒否。user由来管理stateがないproject専用snapshotを適用した後、user `hooks.json`が存在しなくてもlauncher引数を構築できることを検証した。

仕様最終差戻し修正fixture: hook writerのrepo configとsidecarがsymlinkの場合、`--check`/`--apply`/`--recover`/`--rollback`とlauncherの読取りをすべて拒否する。書込みモードではlock directory、backup、pending sidecarの作成前に停止し、リンク先bytesを保持することを確認した。

再実行コマンドと件数（Python 3.12、すべて成功）:

```bash
python3.12 -B -m unittest discover -s tests -p test_codex_config_composer.py -v  # 28件
python3.12 -B -m unittest discover -s tests -p test_codex_hook_state.py -v       # 14件
python3.12 -B -m unittest discover -s tests -p test_install_crew_hooks.py -v    # 14件
python3.12 -B -m unittest discover -s tests -p test_crew_launcher.py -v         # 3件
```

計59件。最初の42件がP1本体、残る17件はP2登録集合とlauncherの関連確認。旧installer停止案はwealth別cloneへ反映済み。global/repo実設定適用は未実施。別作業の個人global `AGENTS.md`文書追記は完了したが、P1権限templateの適用ではない。

前回実機canaryはprivate台帳への書込みに成功し、`~/.codex`直下の一時ファイル作成をerrno 1で拒否された。global configは置換せずbefore/after hash同一。証跡は[`p1-maintenance-canary.md`](p1-maintenance-canary.md)。親は独立反証`/root/p1_atomic_challenge`を受け、global対象だけ固定private台帳内tempを採用した。

今回の4条件: (1) globalのapply/recover/rollbackは共通入口で固定`~/.codex/config-composer`とtempをlock前に検証・選択し、台帳を分岐しない。repo対象は従来の対象親directoryを使う。(2) private dir自身のsymlinkはchmod/temp前に拒否し、temp配置先と対象親の`st_dev`差があれば停止する。(3)元bytesの直前照合、mode、fsync、pending/backupを維持する。cleanup失敗は主エラーにnoteで併記し、置換前失敗では対象bytes不変、置換後の台帳確定失敗ではpendingから復旧し、未確認の`applied`を記録しない。(4) maintenance profileで**変更した`atomic_write`そのもの**を同じlock/元bytes照合下で呼び、global configを同一bytesでrenameする。失敗時のcopy/直接上書きfallback、親dirの権限拡大は行わない。この同一bytes実機canaryは成功済みで、前後global hash`4856f85e592d77d2323346e7b80e44481c8713a1a1b88c4de0909162da4dd70f`、mode `0600`を確認した。後続previewは台帳なしの所有区画を安全に拒否した。

追加fixtureはglobal apply/recover/rollbackの固定state・symlink事前拒否、temp配置、別filesystem停止、cleanup二重失敗、置換後台帳失敗からの復旧を確認した。品質差戻しに対して、非globalの事前device検査を省き、従来どおり`atomic_write`が未作成の対象親directoryを作ってからdevice検査する。新repoの`.codex/config.toml`が未作成でもpreviewは無変更、初回applyは成功して台帳が`applied`になるfixtureを追加した。globalの別temp事前device検査は維持する。

P5正式比較は固定CLI overrideでhooks/user configを無効化する別条件で、campaign `p5-cd6cbf5b9eec05c0`が14/24まで進行確認済み。12/24時点でC1〜C3各4、予備11pass/C2A1 scopefail1。独立内容採点は継続中。redaction由来の安全unknownは違反検出と区別し、補足検証を別途設計する。現24runの途中条件は変えない。品質目標とmedian20%は未測定。比較中の個人global skills/source/AGENTSと実験コード・manifestは変更しない。P1 composer/profileの変更が比較条件へ入らないことはP5証跡にも残す。

限定移管差分は二観点の独立レビューを2往復でAPPROVEDとし、固定profileの隔離HOME・実HOME canary、global hash再採取、`--adopt-legacy-unmarked`のread-only previewを経て適用した。適用直前の対象hashは`05b5faccf46dd8db504521428ea103c4254c4c1198fdcbad136e6ebc564186a5`。previewとapplyの`after_owned_sha256`および`unowned_sha256`は一致した。適用後の実global hashは`18e71587f6f82216aab22edcc2be506eea203900e71b517f0106ac4c0741d506`、台帳generation 1、再previewは`changed=false`。適用後の実profile canaryでも同じ境界を確認した。実設定本文・backupはrepoへ保存しない。

PRには原本template、composer、関連テスト、手順のみ含める。個人global設定/backup、機械固有hooks/list snapshot、信頼hash sidecar、絶対checkout pathを埋め込んだ`.codex/config.toml`は含めない。新cloneでは共通hook installer→新snapshot取得→hook state合成のsetupを再実行し、生成物を公開sourceと扱わず動作することを検証する。既存tracked`.claude/settings.json`はP2共通hook移行に必要な所有handler差分だけを確認し、未知handlerや他者差分を残す。

## markerなし既知旧権限の限定移管差分

親Astraの採用判断と独立反証の条件は[`2026-09-21-p1-known-legacy-unmarked-adoption.md`](../plans/2026-09-21-p1-known-legacy-unmarked-adoption.md)に固定した。`--apply`なしの`--adopt-legacy-unmarked`は同じ照合をすべて通すread-only previewで、lock・台帳・backup・tempを作らず、`applied=false`と全体/所有区画/所有外意味木のhashだけを出力する。適用のopt-inは`--adopt-legacy-unmarked --apply`と対象path/対象全bytes/新原本/旧原本/合成後所有区画の固定hashを必須にする。`permissions.developer`の`description`と`extends`を含む全意味木が既知旧原本と一致し、maintenance/reviewがない場合だけ進む。未知1key/変更1値、既存ledger/pending、旧marker、未知profileのglobal write、legacy sandboxは拒否する。所有外区画の意味木は維持し、旧広権限を新developerへ継承しない。

private台帳には`legacy_unmarked`の独立フラグとexpected hash、before/after、backup/pendingを残す。書込み前と後の注入失敗から`--recover`で安全な新権限へ前進する。初回`--rollback`と`rollback_pending`復旧は拒否し、後続の通常世代rollbackだけを許す。通常2回目applyは対象bytesを変えない。CLIのpreview→apply、両失敗位置、変更値/未知key/`extends`変更/maintenance・review存在/旧marker混在/不正hash/既存pendingの拒否（preview・apply双方で対象bytes・台帳不変）、previewとapplyの出力hash一致、所有外意味木の`policy_unowned`一致はfixtureで確認した。previewはlockを取らないので、その後の変化は`--apply`のlock内照合で停止する。

固定値は新原本SHA-256 `7675f876d4097e7a04787d9d889ba7eab92a7888bfba923422e76b61981df76d`、旧原本SHA-256 `17081a191d7766934a755dcab6e2d1ecb27a3ac79045399780742a73c4aaf61a`、合成後所有区画SHA-256 `9db64c8657083c7527ffc452994f7e59cd210d9da7ec910cfbda5e70e647d054`。global対象全bytesのhashは観測ごとに変化しており（`48886bb2…`→`70d4a519…`→`c659c9de…`、全値と各時点の状態は計画書の表）、**いずれも観測時点の値で現在値ではない**。最新観測`c659c9de9c39ebb0ee00900ccf91dfe59e205e718f7b400379e03379c301b864`でも全意味木の既知旧一致とmaintenance/review・marker・ledger・legacy sandbox・未知profileのglobal write不存在は維持されたが、本packet改訂時（2026-09-22）はglobalを読んでおらず現在値は未確認。作成起源は不明。実適用gateは閉じたままで、適用時は再採取した対象hashでpreviewを行い、`after_owned_sha256`が固定値と一致した場合だけ同じ引数で`--apply`する。global設定全文や秘密値は証跡に出さない。

新限定差分を含む関連テストは`python3.12 -B -m unittest tests.test_codex_config_composer tests.test_codex_hook_state tests.test_install_crew_hooks tests.test_crew_launcher`で59件成功（composer 28件。preview・拒否fixtureは既存testへ追加し、継承・特殊base・型不正の境界testを1件新設。固定repo権限profile差分で原本不変条件testを2件新設）。二観点のレビューは2往復でAPPROVED。公開cloneには検証済みsourceだけ統合し、P5未完走の事実はdraft PRに明記する。P5最終判定は正式比較の完走後に行う。

## 固定repo権限profile差分

2026-09-22の管理者決定（[`2026-09-22-p1-fixed-roots-decision.md`](../plans/2026-09-22-p1-fixed-roots-decision.md)）を原本へ反映した。旧原本`developer`は`:workspace`を継承し`:workspace_roots`の`.git`/`.agents`/`.codex`へwriteしていたため、実行時rootがホームならglobal設定へ届いた。新原本は次のとおり。

- `developer`: `extends = ":read-only"`。writeは`~/Workspace/agent-crew`とその`.git`、既存cache（`~/.cache`、`~/.npm`、`~/.local/share/uv`、`~/Library/Caches`）、`:tmpdir`、`:slash_tmp`だけ。repo直下`.codex`と`.codex/config.toml`は`read`、`"/**/.codex/**" = "deny"`。`network.enabled = true`を維持。
- `maintenance`: `extends = ":read-only"`（developerのdenyを継承しない兄弟）。repo root・`.git`・`.codex`、既存cache、`:tmpdir`、`:slash_tmp`と、既存のglobal保守先（`~/.codex/config.toml`、`~/.codex/config-composer`、`~/.codex/AGENTS.md`、`~/.codex/rules`、`~/.codex/skills`、`~/.codex/agents`、`~/.agents/skills`、`~/.claude/settings.json`、`~/.claude/skills`、`~/.claude/agents`）だけを明示writeにし、`network.enabled = true`を明示。
- `review`: `:read-only`のまま。3profileとも`:workspace_roots`を持たない。
- 公開repoの原本にはprivate repoの物理配置を書かない。private repoのrootはP4でそのrepoの同名developer profile layerに追加する。旧`legacy-developer.toml`は移管照合専用で不変（SHA-256 `17081a19…`一致をtestで確認）。

原本の退行は二段で止める。composerは`desired_policy`で原本を検査し、`developer`/`maintenance`/`review`が`:read-only`基底の兄弟でない（maintenanceのdeveloper継承を含む）、`:workspace_roots`へのwrite、nested形access、不明access（`none`を含む）、`developer`の`:tmpdir`/`:slash_tmp`以外の特殊baseや`~/.codex`の同一・祖先・子孫・交差glob・相対pathへのwrite、`review`のwriteを、lock・台帳作成より前に拒否する。developer（8 write、repo `.codex`・`.codex/config.toml` read、`/**/.codex/**` deny）とmaintenance（19 write）のfilesystem、profile key、networkはcomposer実行時にも固定allowlistと完全一致を検査し、cache以外のhome dir、`~/.claude`、`~/Workspace`全体、他repoの追加、repo `.codex`のwrite化・保護削除、network無効化、maintenance追加先の拡張を拒否する（test済み）。ユーザー名入り絶対pathとprivate repo名の不在、原本・合成後所有区画の固定hashもtestで固定する。

未知profile判定の`extends`なしは、公式記述上は制限基底だが隔離canaryで選択時にCLIがabortし確認できなかったため、保守的拒否へ戻した。accessは公式の`read`/`write`/`deny`に合わせ、`deny`は非write、`none`など他の値は不明として拒否する。未知profileの継承評価、実行時root、相対path、`:root`、globの保守判定は維持した。新`developer`/`maintenance`を継承する未知profileは`:tmpdir`等の特殊base writeを継承するため拒否される（過剰拒否）。

隔離CLI canary（CLI 0.155.1、一時HOME/CODEX_HOME、実global不使用）の結果と残余リスクは判断docの「問題と証拠」「決定」に記録した。要点: CLIはwrite root直下の`.git`/`.codex`/`.agents`を既定でread-onlyにするため`.git`を明示writeにした。入れ子・repo外worktreeの`.codex`がtrust済みproject設定として次回権限を広げることを確認し、`/**/.codex/**` denyで既存・新規の入れ子とroot・globalの`.codex`配下を拒否する。このdenyは同profileの正確path例外より優先されるため、maintenanceは継承しない兄弟profileにした（親canary `/private/tmp/p1_sibling_profile_canary.py`）。運用制約として、developerは`.codex`配下を読めないため、`.codex`を読むpreview・scriptはmaintenanceで実行する。設定ロードがsandbox前であることは未確認。`.git/hooks`・`.git/config`、hook実行script、`AGENTS.md`は残余リスクとして残り、global保護は完全には保証しない。repo外worktreeは対象外で別権限を要する。

新原本SHA-256 `7675f876d4097e7a04787d9d889ba7eab92a7888bfba923422e76b61981df76d`、合成後所有区画SHA-256 `9db64c8657083c7527ffc452994f7e59cd210d9da7ec910cfbda5e70e647d054`。markerなし移管の旧原本hashは不変で、preview・apply・recover・初回rollback拒否のfixtureは新原本で成功した。実HOMEのCLI canaryは適用前後に実施し、developerの通常repo writeと`.codex`・global write拒否、maintenanceの限定write、developerのloopback通信許可、reviewの通信拒否を確認した。上記のglobal適用結果をP1の実機証拠とする。

## P2レビューとの統合境界

P2a/P2bの別contextレビューは親報告どおり仕様`/root/p2_spec_review` APPROVED（33file集合SHA-256 `473c0688080cfc0619582535bcdf816c0d2f9a0a6d24ec2a20c7e36f96225942`、path NUL filehash LF）、品質`/root/p2_quality_review` APPROVED（32file集合SHA-256 `1a09d32ba7e2779bbb5a014105c65df9f7b6cd2e4914cc7922f8e53ac4773634`、path TAB filehash LF）。共通対象の`crew_hooks.py`は`9be5d7db348f19f2a575986141276398d9c6b039bba85252bc16a23b42661339`、`install_crew_hooks.py`は`49eb0f581e5f10768bf2a46f5deceff7b0db9818f75faf28f28d8a95547251e0`。P1は別差分で未レビュー。P2全体のCLI開始context、Stop継続1回と再入終了、発見確認、全テスト、個人skill整理、およびP1/P2統合の実機E2Eは未検証。

公式のnamed permissionsとlegacy sandbox優先順は[OpenAI Permissions](https://learn.chatgpt.com/docs/permissions)と[Config basics](https://learn.chatgpt.com/docs/config-file/config-basic)に基づく。実機の権限結果はレビュー後に別途記録する。
