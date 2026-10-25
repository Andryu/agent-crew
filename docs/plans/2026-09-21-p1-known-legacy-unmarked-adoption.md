# P1 markerなし既知旧権限の限定移管

2026-09-21、親Astraの設計判断。2026-09-22に実globalへ限定適用済み。旧wealthのmarkerがない設定でも、所有するtop3と`permissions.developer`の**全意味木**（`description`、`extends`を含む）が`config/codex/legacy-developer.toml`と厳密一致し、`maintenance`/`review`が不存在の場合だけ初回移管を明示的に許す。これは既承認の旧広権限からdeveloper/maintenance/review分離への移行であり、汎用adopt・force・未知制約のmergeではない。

## 受入条件と停止条件

- `--adopt-legacy-unmarked --apply`を明示する。globalの`~/.codex/config.toml`と固定private `~/.codex/config-composer`に限定し、対象path、対象全bytes、新原本、既知旧原本、合成後所有区画の各hashを指定する。全照合は共通lock取得後、実際に合成する同じbytesで行う。既存ledgerは状態を問わず拒否し、自動でexpected hashを更新しない。
- `--apply`なしの`--adopt-legacy-unmarked`はread-only previewで、同じ固定hash・既存ledger拒否・全意味木照合・所有外意味木一致検査を通す。lock、private台帳dir/file、backup、tempを作らず対象bytesも変えない。出力は`target`/`changed`/`generation`/`applied=false`/before・after全体hash/`after_owned_sha256`/所有外意味木canonical SHA-256の`unowned_sha256`だけで、設定本文は出さない。lockを取らないため、preview後に対象が変われば`--apply`側のlock内照合で停止する。`--recover`/`--rollback`との併用は拒否する。
- 旧原本ファイルのSHA-256は`17081a191d7766934a755dcab6e2d1ecb27a3ac79045399780742a73c4aaf61a`に固定。未知の所有key、所有値1件の差、maintenance/reviewの存在、旧marker、未知profileのglobal write（`~/.codex`領域へ届かないと証明できなければ拒否。`extends`は`:read-only`で終わる鎖だけを評価し、`:workspace`継承・`extends`なし（CLI 0.155.1の隔離canaryで選択時abortし制限基底を確認できない）・循環・不明親・型不正は拒否。accessは`read`/`deny`を非write、`none`等の不明値を拒否。実行時workspace rootが未知のため`:workspace_roots`へのwriteは明示rootの有無によらず拒否。相対path/root、`$`、解決失敗・symlink loopは拒否。絶対pathはcasefold比較で同一・祖先・子孫を拒否し、globは`*`・`**`・`{a,b}`が`/`を跨ぎうるとみなす。過剰拒否と仕様の不確実性は`p1-config-composer.md`に記録）、legacy sandbox、symlink、別filesystemを拒否する。所有外の意味木は合成前後で一致させる。
- 初回世代には独立した`legacy_unmarked`フラグとbefore/after/不存在、固定hash、private backup、pendingを残す。書込み前失敗は既知旧区画を再確認して前進復旧し、書込み後の台帳確定失敗はafter区画を照合して確定する。初回rollback、および初回の`rollback_pending`復旧は拒否する。後続の安全な通常世代だけ通常rollbackを許す。
- 一時ファイルはglobal親dirではなく固定private台帳dirに置き、同じfilesystemであることを確認する。元bytesの直前照合、mode、fsync、backup/pending、cleanup失敗の併記を維持する。非協調writerが直前照合とrenameの間に編集する競合は保証できない。

## read-only観測と実適用gate

global対象全bytesのSHA-256は観測ごとに変化しており、**以下はすべて観測時点の値で現在値ではない**。本文書の改訂時（2026-09-22）はglobal設定を読んでおらず、現在値は未確認。作成起源は推測しない。

| 観測時点 | 対象全bytes SHA-256 | 状態 |
|---|---|---|
| 2026-09-21 初回観測 | `48886bb204431ef8934017d2d60fe23c2237e114399121d504c25d0eac73341f` | 失効 |
| 2026-09-21 read-only snapshot | `70d4a51960bac409abf7856a517a7dc72b57ec0ff80405ae6302d756eda0bdb3` | 失効。全意味木の既知旧一致、maintenance/review・marker・ledger・legacy sandbox・未知profileのglobal write不存在を確認 |
| 2026-09-21 レビュー提出直前 | `c659c9de9c39ebb0ee00900ccf91dfe59e205e718f7b400379e03379c301b864` | 最新観測値だが現在値の保証なし。上記一致・不存在条件は維持 |

対象hashが観測間で変わるため、固定値として事前に採用できる対象hashはなく**実適用gateは閉じたまま**。expected hashは自動更新しない。

変化しない固定値は、新原本SHA-256 `7675f876d4097e7a04787d9d889ba7eab92a7888bfba923422e76b61981df76d`、旧原本SHA-256 `17081a191d7766934a755dcab6e2d1ecb27a3ac79045399780742a73c4aaf61a`、合成後所有区画のcanonical SHA-256 `9db64c8657083c7527ffc452994f7e59cd210d9da7ec910cfbda5e70e647d054`（いずれもrepo内fileから再計算可能）。新原本と合成後所有区画は2026-09-22の固定repo権限profile（developerは`:read-only`基底でagent-crew rootとその`.git`・cache・`:tmpdir`・`:slash_tmp`だけwrite、`/**/.codex/**` deny、maintenanceはdeveloper非継承の`:read-only`基底でrepo・`.codex`・cache・tmp・global保守先を明示write、`:workspace_roots` writeなし）へ更新した値で、それ以前の`b6778934…`/`68f5a0f0…`/`04e2b92f…`/`4a585569…`/`6dcbed22…`/`d4e6f8b3…`/`ec23c871…`/`5c9af6b1…`は失効。実適用前に新profileのCLI canaryを行う。適用時は親判断のもとでread-onlyに対象hashを再採取し、その値を`--expected-target-sha256`に与えて`--adopt-legacy-unmarked`のpreviewを実行する。previewの`after_owned_sha256`が上記固定値と一致し、所有外保持検査が通った場合だけ、同じ引数へ`--apply`を足して適用する。previewとapplyの間に対象hashが変われば停止して親が再判断する。秘密値、設定全文、backupはrepoへ保存しない。

fixtureで明示opt-in、read-only previewの無変更（lock・台帳dir・backup未作成、apply結果とhash一致）、未知key/変更値/`extends`変更/maintenance・review存在/旧marker混在/不正hashの拒否（preview・apply双方）、所有外意味木の`policy_unowned`一致、書込み前後失敗の前進復旧、初回rollback拒否、2回目通常apply不変、既存pending拒否を確認する。関連テストと対象hashを[`p1-config-composer.md`](../codex-direct/p1-config-composer.md)へ記録し、新差分の仕様・品質レビュー後にのみ実global適用へ進む。既存の同一bytes maintenance canary成功はこの限定移管の実適用証拠ではない。P5の固定24run条件、個人global skills/AGENTS、元wealth、元repo旧17 agentを変更しない。

P1の仕様・品質レビューは2往復でAPPROVED。適用直前のglobal全bytes SHA-256は`05b5faccf46dd8db504521428ea103c4254c4c1198fdcbad136e6ebc564186a5`、適用後は`18e71587f6f82216aab22edcc2be506eea203900e71b517f0106ac4c0741d506`。previewとapplyの合成後所有区画および所有外意味木hashは一致し、台帳generation 1の再previewは`changed=false`。公開cloneへはレビュー済みsourceだけ統合し、P5未完走の事実はdraft PRに明記する。個人global設定・private台帳・backup・機械固有snapshotを公開差分に含めない。
