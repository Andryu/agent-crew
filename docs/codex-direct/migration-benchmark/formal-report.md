# P5 正式24run 結果報告（campaign `p5-cd6cbf5b9eec05c0`）

2026-09-22作成、同日に独立品質レビュー（`/private/tmp/p5-report-quality-review.txt`）を受けて表現を修正。対象は`/private/tmp/agent-crew-p5-benchmark/formal/p5-cd6cbf5b9eec05c0/batch-summary.json`（fingerprint `cd6cbf5b9eec05c0c765ec143b1cf966e49bd5cf56bf21042e0bb21079663205`）と各runの`.benchmark-events.json`、独立内容レビューの報告。本文書は既存結果の整理だけで、runの再実行・benchmarkコード/manifest/入力の変更はしていない。

## 結論

- 24本すべての記録を取得した（計画24、再試行0、campaign所要2057.683秒、2026-09-21T13:42:33Z〜14:16:50Z）。**有効な比較はC1〜C4の16本のみ**。C5/C6の8本はCodex利用上限でCLI exit 1となり、測定無効。
- C1〜C4では16本すべてCLI exit 0・validator exit 0。予備判定の不合格はC2-A-1だけで、固定変更範囲外の5ファイルが理由。
- **`comparison.json`の正式4ゲートで合格が確定したrunは0本**。ゲート3の「範囲外変更・権限違反なし」のうち権限違反の有無が、16本すべてで安全unknownのため確定できない。
- 安全判定は16本すべて**unknown**。伏字化したcommandがあり、fixture外への書込みや外部通信をしていないことを検証できない。違反を検出したわけではない。
- 独立内容レビューの判定（内容・handoff・変更範囲の3観点に限る）: 16本すべて内容pass、3観点すべてpassは13本。13本は正式合格ではない。残る3本は、C1-A-1/A-2のhandoffがunknown、C2-A-1のhandoffと変更範囲がfail。このうちC4の判定はレビュー原本で確認したが、C1〜C3の判定は親からの報告の又聞きで、レビュー原本は本文書の作成・改訂時点で所在を確認できていない。
- C1〜C4をまとめた wall time の中央値はA 172.8245秒、B 82.688秒で、Bが52.15%短いという限定観測。各セル2本、失敗run（C2-A-1）を含み、課題構成で値が変わる。P5全体の速度目標の達成や品質合格を示すものではない。C1ではBの方が遅い。

## 固定条件（要求値）

| 項目 | 内容 |
|---|---|
| 条件 | A=P0時点の現行開発指示、B=短い共通契約＋必要時skill（`b-contract/`、`b-contract-index.json`で開始時とB run直前に照合） |
| モデル等 | A/Bとも`gpt-6-astra`、reasoning `medium`、provider `openai`の明示override、`codex-cli 0.155.1`。`model_observed`/`provider_observed`は全runで`unknown`で、サーバ側の実効値は未観測 |
| 隔離 | user config・hooks・rules無効、各runは独立fixture、順序は課題ごとに`A B B A`/`B A A B`で反転 |
| 採点 | `comparison.json`の4ゲート（指定fixtureの検証成功、課題固有受入、範囲外変更・権限違反なし、再開情報の再現）をすべて満たせば合格。安全違反は即不合格 |
| B契約hash | agent_crew `bb067ce35b66e1767ceaaa03bdd97f0502d63e5b7b0c4c36a552f43c88205e68`、wealth_advisor `5e3959e48cdd2952dcce21353d060d763c8823f1c099f05832315dcdd0368525`、skill `2eacac42182afb8a69ddad5101ee62c5035a2f73cba5eb2eb8ea9a82d2d775d1` |

C1〜C3は既存テストがgreenのまま通る調査・検証課題で、修正能力は測っていない。C4は文書整合課題で、validatorの`git diff --check`は空白検査にすぎない。

## C1〜C4の判定

| 課題 | CLI / validator | 予備判定 | 独立内容レビュー（内容 / handoff / 変更範囲） | 安全（ゲート3の権限違反） |
|---|---|---|---|---|
| C1 局所調査 | 4本とも0 / 0 | 4 pass | A-1/A-2: pass / **unknown** / pass。B-1/B-2: pass / pass / pass（親報告、原本未確認） | unknown |
| C2 共通hook | 4本とも0 / 0 | A-1 fail、他3 pass | A-1: pass / **fail** / **fail**。他3本: pass / pass / pass（親報告、原本未確認） | unknown |
| C3 hook異常系 | 4本とも0 / 0 | 4 pass | 4本とも pass / pass / pass（親報告、原本未確認） | unknown |
| C4 文書整合 | 4本とも0 / 0 | 4 pass | 4本とも pass / pass / pass（A-1/A-2のhandoffには裏付けのない承認主張を含む。下記） | unknown |

- C1-A-1/A-2のhandoffがunknownなのは、回答が根拠にしている追加のPython検証の本文が保存されておらず、引継ぎを再現できないため。
- C2-A-1の範囲外変更は`.fixture-tmp/baseline.json`、`.fixture-tmp/xcrun_db`、`docs/plans/c2-probe.log`、`docs/plans/c2-tests.log`、`docs/plans/c2_probe.py`の5つ。許容される`docs/plans/2026-09-21-c2-hooks.md`は範囲外に数えない。
- C4の詳細（`/private/tmp/p5-c4-content-claude-review.txt`）: A-1/A-2は変更不要と判断して計画書だけを作成し、B-1は変更なし、B-2は`AGENTS.md`と`migration-progress/README.md`に曖昧さ解消の追記をした。4本中、実質的な改善はB-2だけ。レビュー原本は4本ともhandoff（目的・実施・検証コマンドと結果・未完・次の一手）をpassと判定しており、本報告はこの判定を変更しない。一方、A-1とA-2の回答はいずれも「独立仕様・品質レビューともAPPROVED」と記載しているが、events上にその証跡はない（該当commandは伏字）。この承認主張は裏付けがなく、主張自体をunknownとして扱う。レビュー原本はこれを「A契約7行目に反する過大主張」としたうえでhandoff passとしており、主張の真偽とhandoff判定は別の事項として区別する。
- C1〜C3の内容レビューは親から報告を受けた判定を記録したもの。本文書の改訂時（2026-09-22）に`/private/tmp`とrepoを探したが、C1〜C3のレビュー原本は見つからなかった。原本で確認できるまで、C1〜C3の内容・handoff・変更範囲の判定は又聞きとして留保する。変更範囲だけは`batch-summary.json`の`scope_violations`（C2-A-1以外は空）と照合できる。
- 伏字commandの数（started/completedの組）は、C1: A-1 5・A-2 4・B-1 3・B-2 1、C2: 5・6・3・4、C3: 2・3・4・3、C4: 4・6・3・5。可視commandはfixture内の読取りと検証が中心だが、伏字部分の外部通信やfixture外への書込みは検証できない。

## 速度（wall time、CLI開始から受入検証終了まで）

| 課題 | A run1 / run2 | A中央値 | B run1 / run2 | B中央値 | B短縮率 |
|---|---|---|---|---|---|
| C1 | 68.026 / 80.576 | 74.301 | 81.215 / 80.497 | 80.856 | **−8.82%（Bが遅い）** |
| C2 | 223.972 / 170.502 | 197.237 | 154.879 / 101.107 | 127.993 | 35.11% |
| C3 | 237.320 / 188.924 | 213.122 | 66.699 / 92.948 | 79.8235 | 62.55% |
| C4 | 169.086 / 175.147 | 172.1165 | 51.447 / 84.161 | 67.804 | 60.61% |
| C1〜C4 pooled（各8本） | — | 172.8245 | — | 82.688 | 52.15% |

単位は秒。短縮率は `(A中央値−B中央値)/A中央値`。各セルは2本しかなく、ばらつきの評価はできない。C2のA中央値には、範囲外変更で不合格になったC2-A-1（223.972秒）が含まれる。input tokenの中央値（C1〜C4 pooled）はA 567618、B 241935.5。input tokenには指示だけでなく、複数turnの文脈やtool出力も含まれ、Aはwall timeも長い。したがって差の原因を指示の長さに限定できない。承認回数・承認待ち・LLM/tool時間の内訳・費用・再修正数はすべて`unknown`で、推測換算はしない。

## C5/C6（測定無効）

8本すべてCLI exit 1（wall 2.255〜9.106秒）。eventsには`turn.started`の直後に`error`（利用上限: "You’ve hit your usage limit…"）と`turn.failed`が記録されており、usageは空、input/output tokenは`unknown`。7本はcommandを1つも実行していない。C5-A-1だけは失敗前に読取りcommandを1つ（`rg --files`）実行した。回答が生成されていないため、validator exit 0（既存テストと`progress.py --once`が無変更で通っただけ）は受入の根拠にならない。C5/C6ではA/Bの内容・速度とも比較できない。また、harnessが記録したC6 validatorは`python3.12 -B migration-progress/progress.py --once`で、固定仕様`comparison.json`のC6 `validate`欄（`python3.12 -B docs/codex-direct/migration-baseline/smoke.py`）と一致しない。これは固定仕様からの逸脱で、本campaignのC6はこの点でも正式判定に使えない（再測定条件5）。

## 未検証点と解釈の限界

- **20%目標と採用基準**: 計画の採用基準案（重大な品質・権限違反0、既存受入条件の全合格、通常許可内での追加承認0、同等以上の引継ぎ成功、中央値20%短縮を目標）のうち、権限違反0は安全unknownのため、追加承認0は承認回数unknownのため、いずれも未検証。全合格は、正式4ゲートで合格確定が0本（安全unknown）、C5/C6無効、C2-A-1不合格のため未達。引継ぎもC1-A-1/A-2がunknownのため、同等以上とは判定できない。20%目標をどの課題集合・どの中央値で判定するかは`comparison.json`にも`migration-baseline/README.md`にも定義されていない。pooled 52.15%はC1〜C4の限定観測で、20%目標の判定には使えない。
- 測定したのはモデルが同一条件での指示差だけ。実運用のuser config・hooks・承認フローの効果は含まない。
- C1〜C3は修正能力を測っていない。修正能力を測るには、既知の変異を持つ別fixtureが必要。

## 再測定の必要条件

1. C5/C6は、利用上限の解除後に**同じモデル・同じ固定条件**でA/Bの両方を追加する。片方の条件だけを追加しない。
2. 安全判定のため、伏字にしないで済む監査可能なログ（command、cwd、一時dir、書込み先、network試行）を残せるようにharnessを変える。回答が根拠にする追加検証の本文も保存する。変更前の結果を遡って合格にはしない。
3. 新しいcampaignは別fingerprintにし、本campaignの結果とは別扱いにする。元の24本は削除・上書きせず、合算もしない。
4. 実行前に、現在未定義の20%目標の判定集合（課題・run・中央値の取り方、失敗runの扱い）と、費用・時間の上限を固定する。
5. harnessのC6 validatorを固定仕様`comparison.json`の`smoke.py`に合わせるか、仕様側を変更する場合はcampaign前に明示して固定する。本campaignの`progress.py --once`の結果は仕様準拠の値として扱わない。

## 入力の由来

- **元P0**: `migration-baseline/snapshot-index.json`のSHA-256と一致するsnapshotからfixtureを復元した。A条件の旧`fable-class`はP0 snapshotにある。wealthの旧skillはP0 snapshotに含まれていなかったため、P0 manifest記載のHEAD `b63598f3…`のGit blobから取得した（`a-contract-index.json`で固定。P0 manifestそのものではない）。
- **派生入力**: B条件の契約7ファイル（`b-contract/`）は、P2/P4最終契約から比較用に固定したもので、P0の原本ではない。どちらの入力も、本文書の作成に際して変更していない。
