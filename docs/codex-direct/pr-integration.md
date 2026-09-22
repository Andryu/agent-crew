# Codex開発移行 PR統合準備

2026-09-21時点。元repo HEADとclone開始版はいずれも`875dd67062d7a16fc27017965066a99303e3d0a9`。作業cloneは`/private/tmp/agent-crew-codex-migration`、branchは`codex/runtime-migration-p5`、`origin`は元repoの`git@github.com:Andryu/agent-crew.git`。commit/pushは未実施。P1のglobal/repo実設定適用も未実施。

## 明示allowlistと依存

元repoの未コミット成果から106ファイルを個別指定でコピーした。各source相対path、コピー時SHA-256、clone相対path、区分は[`pr-copy-manifest.json`](pr-copy-manifest.json)に固定する。後から更新された個人skill README/plan、P1限定修正、P2 API証跡の現行hash・理由は[`pr-runtime-sync-manifest.json`](pr-runtime-sync-manifest.json)に別記した。公開用の個人path変換対象は別担当の`pr-publication-manifest.json`でpublished hashを管理し、元repo版を再コピーしない。tracked差分全体の一括移植は行っていない。

| 区分 | 件数 | PRに必要な依存 |
|---|---:|---|
| contract | 6 | 共通AGENTS、fable-class原本とreferences、direct-reviewer定義 |
| runtime | 9 | P1 composer/hook state、P2共通hook manifest・launcher・installer・inspect、P1権限template |
| tests | 6 | P1 fixture/回帰、P2 launcher/hook/installer回帰 |
| plans_and_guides | 7 | 移行計画、独立レビュー記録、P3 handoff、P2計画、P1適用前packet |
| progress_board | 3 | 専用表示台帳とCLI。queue正本への自動反映はない |
| p0_baseline | 26 | P0 manifest、比較手順、非機密snapshotとsmoke fixture |
| p2_retired_agents | 18 | 旧Codex agent退避。新たな起動定義として使わない |
| tests_dependency | 1 | `scripts/privacy-check.sh`のcommon hook summary APIとmacOS Bash 3互換 |
| p2_personal_skills | 12 | 静的二観点APPROVED済みの旧skill退避9ファイル、manifest、README、plan |
| p2_global_contract | 2 | 個人global契約のtemplateと適用記録。AGENTS文書へ追記済み、P1権限設定は未適用 |
| p2_reappeared_archive | 9 | 再出現した旧4 skillの別退避。元manifestと全hash一致 |
| p1_canary | 1 | 初回拒否と修正版同一bytes成功、preview停止の証拠 |
| p2_runtime_evidence | 1 | 個人4skillのAPI結果とユーザー手動App表示確認を区別 |
| p2_agents_handoff | 1 | 旧17件の元repo再出現とclone採用定義の差を記録 |
| p5_formal_report | 1 | P5正式24run結果報告（独立品質レビューAPPROVED版）。benchmarkコード・契約・入力はコピーしない |
| p1_final | 2 | P1既知旧無印区画の採用判断、固定root・兄弟profile決定 |
| p2_final | 1 | tracked`.claude/settings.json`を置換し、Claude hook登録を共通`crew_hooks.py`の4イベントへ統合 |

P1前回8ファイル集合SHA-256 `64bf47ec06be57ae9d0582c01f74b8392ed9c7353eb89d1a0ee326791b4fd778`（path NUL filehash LF、path順）は仕様`/root/p1_spec_review`・品質`/root/p1_quality_review`の両APPROVEDで親採用済み。独立反証`/root/p1_atomic_challenge`を受けたprivate temp限定修正の集合`5c669cb38e307fbbdf1df29fc1acf7c8f3337a2424028092ab0807982c0f39f1`は品質reviewで新repo初回apply回帰1件を差戻された。修正版の新8ファイル集合`74a2500030f3cbdc00e5ceb3c34c4ac8b594698d4788ef47277dbecc46fad79c`は仕様・品質ともAPPROVED、親採用。更新した3ファイルのcopy時hashと現在hashは[`pr-runtime-sync-manifest.json`](pr-runtime-sync-manifest.json)で区別する。実機canary証跡は8ファイル集合に含めない。

## 除外と追加待ち

- 個人global設定、backup、実機hooks/list snapshot、`docs/codex-direct/local-hook-state.json`、信頼hash台帳、絶対checkout path入りの生成`.codex/config.toml`/`.codex/hooks.json`をコピーしていない。生成設定は新cloneのsetupで原本から再生成し、公開sourceにはしない。
- 既存tracked`.claude/settings.json`は2026-09-22にP2最終版へ置換した。旧登録（`UserPromptSubmit`の`model-mode.sh`、Stopの`privacy-check.sh`・`propose-lesson-rules.sh`・`enforce-retro-stop.sh`、SubagentStopの`enforce-queue-done-stop.sh`、Obsidian必読echo等）は削除され、SessionStart/Stop/SubagentStop/TaskCompletedの4件が`crew_hooks.py`経由になる。旧hookの機能が共通hookで同等に保たれるかはレビュー対象。
- P2個人skillの初回退避9ファイルに加え、再出現した同一hashの9ファイルを別archiveとしてコピーした。旧global空directoryはGitに保存できるファイルを含まない。README/planは新規app-server API結果を追記した版へ限定同期し、元copy hashは保持した。個人global `AGENTS.md`は承認済み候補を追記し、before/after hashとprivate backupをplanに記録した。P1権限設定の適用は別工程。P5は正式報告1ファイルのみコピー済み（下記）。P4は別cloneとPR13で扱う。wealth旧installer停止案は元repoにもこのcloneにも未適用。
- 元repoの`.codex/agents`には20:15:31に旧17件が再出現し、現在も17件すべて存在する。退避manifestとのhash照合は15件一致、`critic.toml`と`pm.toml`の2件は内容差分あり。生成元の限定調査では未特定で、ユーザーは別pane更新有無を「わからない」と回答した。これらの実ファイルは変更・削除せず、元repoのP2旧agent除去を完了扱いにしない。cloneでは旧17件は退避開始版のままで、active定義は`direct-reviewer.toml`のみ。**P2検証/PRの採用対象はclone**とし、元repoの現在定義を退避版と偽らない。差分hashと引継ぎ条件は[`p2-agents-handoff.md`](p2-agents-handoff.md)に記録した。
- ゲーム、個人memory DB、Hermes、research、`.signals`、backup、`node_modules`、Sites独立repo、金融資産、認証ファイルは移していない。

## 検証と残る依存

- 元repoで`python3.12 -B -m unittest tests.test_codex_config_composer tests.test_codex_hook_state tests.test_install_crew_hooks tests.test_crew_launcher -q`が新repo初回apply fixtureを含む50件成功。cloneにもP1限定修正の3ファイルだけを再同期した。P0 smokeは前回成功。
- cloneの`python3.12 -B -m unittest tests.test_crew_hooks.AdapterTests.test_privacy_summary_redacts_values_and_file_names -v`は1件成功、`python3.12 -B -m unittest tests.test_crew_hooks -q`は15件成功。元repoの`scripts/privacy-check.sh`既存diff全体がsummary APIとBash 3互換の必要依存と親が判断したため、**この1ファイルのみ**cloneへコピーした。source SHA-256は`ce9c26bd5b6d860f0e18efa014b953432d9b316c674dd7810f88efaf5b6e05c6`。理由もcopy manifestに記録した。
- P1前回maintenance実機canaryは`~/.codex`直下の一時ファイル作成を拒否された。親採用版の変更済`atomic_write`を同じlock/元bytes照合で使った同一bytes renameはmaintenance profile内で成功し、global configの前後hashは`4856f85e592d77d2323346e7b80e44481c8713a1a1b88c4de0909162da4dd70f`、modeは`0600`で一致。続くread-only previewは**台帳なしの所有区画**を検出して停止し、所有外保持結果は未取得。実global適用と後続の順次反映は停止。詳細は[`p1-maintenance-canary.md`](p1-maintenance-canary.md)。
- P2個人4skillは新規app-serverの`skills/list(forceReload)`で元repo/cloneの両cwdに各1件・enabled・user scope、対象parse errorと全体errorは0件。再実行exit 0とsource/clone差は[`p2-skills-app-server-evidence.md`](p2-skills-app-server-evidence.md)に固定した。App UIの正式toolアクセスは安全理由で拒否された履歴を保持し、ユーザー本人がApp新規チャットの候補4件を各1件表示と手動確認した事実を別の証拠として追記した。モデルturn・業務skill実行はしていない。新server終了後も両repoの旧4 pathは不存在。再出現元は未特定。
- P5正式24runのcampaign `p5-cd6cbf5b9eec05c0`は完了し、正式報告[`migration-benchmark/formal-report.md`](migration-benchmark/formal-report.md)（SHA-256 `43526472a70a3ff51ef1eaaa729b7872c449aad0c4045565824ff1068b3b63c1`、独立品質レビューAPPROVED）を元repoからbytes一致でコピーした。有効比較はC1〜C4の16本のみ、正式4ゲート合格確定0本、安全判定は16本すべてunknown、C5/C6は利用上限で測定無効、20%目標は未検証。報告が参照する`/private/tmp`の実行記録・レビュー原本とbenchmarkコード・契約（`b-contract/`等）は公開cloneに含めない。固定CLI overrideでhooks/user configを無効化する比較条件のため、P1 composer/profile変更を比較条件から除外したことをP5証跡へ記録する。比較中の個人global skills/source/AGENTSと実験コード・manifestは変更しない。
- 2026-09-22、P1最終4ファイル（permissions/composer/test/packet）と新plan2件、P2最終3ファイル（`scripts/crew`・launcher test・instructions）と`.claude/settings.json`を元repoからbytes一致で同期した。既存copy entryの7件は原copy hashを保持し現hashをruntime-sync manifestへ記録、新規3件はcopy manifestへ追加。初回同期時は`test_direct_launch_from_old_python_reexecs_or_stops_clearly`のcodex subtestが公開しない`local-hook-state.json`に依存し新cloneで失敗したため、P2担当修正版（launcher test `5b9729b6…`、instructions `0db7923d…`）を再同期した。直接起動はclaude分岐で3.11+切替を検証し、codex分岐は`launch_spec`のunit testで検査する。公開cloneで関連60件すべて成功。
- PR作成前にP1の既存所有区画への対応判断、新cloneからの生成手順、P1/P2統合E2Eを確認する。公開変換担当所有のREADME/計画/P0派生文書は元repoから再同期しない。現段階では実適用・commit/pushを停止する。

## 公開cloneの最新引継ぎ追補と台帳整合

公開用[handoff evidence](../plans/2026-09-21-migration-handoff-evidence.md)は匿名化済みの前時点snapshotとして保持する。元repoの新追補はそのままコピーしない。現在の必要事実は上記P1/P2/P5に加え、wealth別cloneのdraft PR #13がHEAD `e7fb40ab32a138e23b254043de976f3c46594342`、stopperを含む9ファイル、限定34テスト成功、作業tree cleanであること。元wealth repoと元repo旧17 agentは変更しない。P0元入力と公開派生snapshotは別hashであり、P5正式campaignは元入力を使う。

`pr-copy-manifest.json`の変化は実装担当が末尾へ`p2_runtime_evidence`と`p2_agents_handoff`を各1件追加したため。100→101件時にJSON全体を再シリアライズし、101件版SHA-256は`77a57bb7e7f3a353ac3c65696c77fbfb915aef28f180c5d7f9717d461fdd2e0f`。さらにhandoff追加で102件版は`77e3056b30372499a3d27addd72f24a48824dc1286f20f67f90f118efbdbd686`。101件prefixを再シリアライズしたhashは公開変換台帳の参照値と一致し、元101件のentry値は維持。全102件のtarget重複なし、runtime更新8件の元copy hash・現hash一致、公開変換8件の元hash・公開hash一致を確認した。2026-09-22、元102件のentry/hash（直接一致86件、runtime更新8件、公開変換8件）を再検証後、末尾へ`p5_formal_report`1件を追加した。先頭102件のentry値は不変。103件版SHA-256は`a0cbc526cf5433e874dcb895efc5faabbf9a12bf3e364ecc97568f97c74d3c3b`で、公開変換台帳の`copy_manifest_sha256`をこの値へ更新し参照不一致を解消した（`transforms`と`p5_input`は不変）。更新後にP0 smoke exit 0、関連65テスト成功。P1 4ファイルの最終同期で台帳が再変化した場合は同じ手順で再照合する。並行review中の公開変換8ファイルと元P0は変更しない。

106件版copy manifest SHA-256は`755fa8f6e3b06bd2ba094fc788e29c33c4adba16d37b386b0f08172bff7ec275`。公開変換台帳の`copy_manifest_sha256`をこの値へ更新し、先頭103件のentry値は不変。全106件がcopy/runtime-sync/公開変換いずれかのhashと一致し、target重複なし。
