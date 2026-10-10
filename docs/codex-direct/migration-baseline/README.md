# P0 開発移行ベースライン（2026-09-21）

**現在地:** ユーザーがP0以降の開発移行の実行開始を明示承認し、親はP0を受入済み。元の[移行計画](../../plans/2026-09-21-codex-operating-model-replan.md)冒頭の「提案、設定未適用」は計画作成時点の記述であり、P0の調査開始を否定しない。P0は調査・記録のみ。global/wealth設定の適用、P6/P7の金融運用、24run比較は未実施。

## 固定した証跡

- [manifest.json](manifest.json): `agent-crew`は`main` / `875dd67062d7a16fc27017965066a99303e3d0a9`、`wealth-advisor`は`codex/operations-readiness` / `b63598f3d39944c73602dec76373b63a747b5d41`。全repoのtracked変更件数と、選んだ対象パスのGit状態・SHA-256・所有者を記録。未追跡の対象は各14件・12件、全repoの未追跡ファイル一覧は収集しない。globalは許可した非機密キーだけを保存し、`model=gpt-6-astra`、reasoning=`medium`、providerの明示なし、CLI=`codex-cli 0.155.1`を観測。
- [snapshot-index.json](snapshot-index.json)と`snapshot/`: 比較の開始版を再現するため、非機密のscript/test/契約17ファイルと共通hookの原本manifest 1ファイルのみをコピー。比較Aの改訂前`fable-class`本文とreferences 3件も含め、P2後にも旧指示を復元できる。未追跡・未コミットの入力もhash対応で固定。global/repoの実設定本文、認証、実資産、会話ログはコピーしていない。`fixtures/board-state.json`は非資産の合成表示台帳。
- [comparison.json](comparison.json): 6課題の入力、fixture、開始版、実行コマンド、採点と計測欄を固定。C1〜C3は既存テストが成功する**調査・検証タスク**。修正力を測るには後日、既知変異を持つ別fixtureが必要。
- [smoke-result.json](smoke-result.json): C6の手順smoke。追加LLM呼出しなし。モデル利用量・費用は`unknown`で、推測換算しない。A/B比較の結果ではない。

比較Aの旧`fable-class` 4ファイルのsnapshotは、親が退避した非公開の一時資料と全件バイト一致を確認した。P2の改修後もP0 manifestは再採取・上書きせず、現在との差を移行差分として扱う。

この公開cloneの`snapshot-index.json`は、進捗ボードREADMEの個人環境パスをrepo相対に直した**公開用派生index**である。P0の`manifest.json`と[copy時点の台帳](../pr-copy-manifest.json)は元hashの記録として不変とし、[公開変換台帳](../pr-publication-manifest.json)に元hash・公開hash・変換理由を記録する。P5の正式入力は元P0 snapshotであり、この公開派生入力から再実行すると入力hashとfingerprintが異なる。両者の結果を同一runとして扱わない。

採取初稿の`capture.py`は`git status --porcelain`の先頭空白を`.strip()`で失う不具合があった。`rstrip("\n")`へ修正して**manifestを再採取**し、tracked変更の` M`と未追跡の`??`を実出力と照合した。最終manifestは修正後の採取結果のみ。

## 所有マップと衝突点

| 区画 | 現在の原本・管理者 | 適用先・注意 |
|---|---|
| 個人global | `~/.codex/config.toml`と既存`rules/default.rules`、`rules/developer.rules` | 個人実設定。現行の権限templateはwealth側`config/codex/developer.toml`・`developer.rules`。providerの未設定をOpenAI直結の実効確認と取り違えない |
| 共通hook原本 | agent-crew `config/crew-hooks.json`、`scripts/crew_hooks.py`、`scripts/install_crew_hooks.py` | agent-crewの`.claude/settings.json`と`.codex/hooks.json`へmerge。未知handlerを保持する設計 |
| 機械固有hook信頼状態 | agent-crew `scripts/codex_hook_state.py` | agent-crew`.codex/config.toml`**全体**と`docs/codex-direct/local-hook-state.json`。生成hashで同時変更を拒否 |
| wealth権限installer | wealth `scripts/install_codex_permissions.py` | `~/.codex/config.toml`、`~/.codex/rules/developer.rules`、wealth`.codex/config.toml`へ書く。現時点ではglobal ruleとwealth project設定がtemplateと同hash |
| repo固有契約・起動 | 両repoの`AGENTS.md`、agent-crew`scripts/crew` | agent-crew launcherは自身のrootとqueueへ固定。wealthへsymlinkするだけではscopeが混線する |
| skill | repoの`.agents/skills`・`.codex/agents`、globalの`~/.codex/skills/.system` | 今回は存在と対象hashのみ。配布元と意味差の整理はP2 |

**具体的な衝突:** wealth installerの`files`は上記global 2パスとwealth`.codex/config.toml`を管理する（`scripts/install_codex_permissions.py`の`files`定義）。共通hook信頼生成器をwealthにもそのまま使うとwealth`.codex/config.toml`を全面生成し、権限profileのrepo設定と競合する。agent-crew側でも生成器は`.codex/config.toml`全体を所有する。global権限をagent-crewへ移すと、現在のwealth installerがglobalを再上書きしうる。各ファイルのhash・存在状態はmanifestの対応項目が正本。

## 比較の実施方法

P5で各課題を同じsnapshotから隔離して再開する。A=現行指示、B=短い共通契約＋必要時skill。両条件でAstra medium、`model_provider=openai`の明示override、CLI 0.155.1、安全境界・hook・レビュー工程を固定する。現行globalでproviderが省略されているため、比較runでの明示指定と現状観測を区別する。各条件2回・順序交互の24runはまだ実施していない。

採点は各課題について(1)指定fixture成功、(2)固有受入条件、(3)範囲外変更・権限違反なし、(4)引継ぎ再現の4項目。すべて合格が受入で、安全違反は即不合格。wall time、承認回数/待ち、LLM/tool時間、token/費用、再修正、review指摘、範囲外変更、引継ぎを記録する。取得不能値は`unknown`。速度改善は未測定で、中央値20%短縮は目標に留まる。

## P1の具体的変更集合（親指定の6条件で採用済み、実適用レビュー待ち）

1. **直前照合:** manifestと実ファイルのhash・既存rule・未コミット差分を再取得し、P0から変わった対象は勝手に上書きせず統合する。global既存のprovider、MCP、hooks、未知キーと承認済みruleを保持する。
2. **所有権移管:** `scripts/codex_config_composer.py`をagent-crewの単一composerとし、wealthの権限templateを移管履歴付きで`config/codex/`へ。`~/.codex/config.toml`と`rules/developer.rules`は単一の管理経路へ。TOMLの所有キーパス、共通ロック、区画保持、同時変更hash拒否、再実行一致、適用世代/rollbackをfixtureで確認してからglobal適用を判断する。
3. **旧入口の停止:** wealth installerからglobal再書込みをさせない明示停止/移管先案内を作る。旧templateの再適用でもglobal write権限が復活しないことを試験する。wealth固有`.codex/config.toml`の権限profileは保持する。
4. **hook区画との分離:** agent-crewの機械固有`.codex/config.toml`とsidecarを旧schema1の正当な全体hashから区画台帳へ移行し、launcher検証を同時改修。将来wealthへ共通hookを導入する際は、wealth repo権限profileと同じ出力ファイルを二つのinstallerが全面所有しない。launcherのwealth横展開はP4まで保留。

保持条件は他者差分、未知設定、既存`default.rules`/`developer.rules`、repo固有契約、providerの現状。余分なglobal write権限は未知設定として温存しない。rollback対象は`~/.codex/config.toml`、`~/.codex/rules/developer.rules`、wealth`.codex/config.toml`、agent-crew`.codex/config.toml`とhook sidecar、および各変更集合のbackup/manifest。秘密を含みうるglobal backupはrepo外のprivate領域のみ。非協調外部編集の完全防止は保証しない。maintenance profileを選ぶことは依頼範囲外の操作承認を意味しない。global/wealth実適用前に親へ差分・hash・rollbackを渡す。

## 再検証

```bash
python3.12 -B docs/codex-direct/migration-baseline/smoke.py
python3.12 -B -m unittest discover -s tests -p test_crew_launcher.py -v
python3.12 -B -m unittest discover -s tests -p test_install_crew_hooks.py -v
python3.12 -B -m unittest discover -s tests -p test_codex_hook_state.py -v
```

`capture.py --check`は元P0採取環境専用で、非公開のwealth-advisor repoと個人設定を参照するため、公開cloneの再検証コマンドには含めない。wealth-advisorの静的fixture 6件も非公開の別repoでの当時の結果である。

P0実測: agent-crewの3+12+8件、wealth静的fixtureの6件が成功。公開cloneのsmokeは18 snapshotと合成fixtureのhash、6課題の入力存在、C6のCLI更新/読込、実表示台帳不変を確認し、匿名化したsnapshotは公開変換台帳の元hash・公開hashも照合する。実移行の設定適用・認証・金融データ処理は行っていない。
