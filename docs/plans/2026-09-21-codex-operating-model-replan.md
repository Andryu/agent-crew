# Codex中心の個人開発への移行再計画

作成・調査日: 2026-09-21。対象: agent-crew / wealth-advisor。状態: **提案、設定未適用**。
complexity: M / risk: medium（横断設定・権限・学習保存の設計）。メイン: gpt-6-astra（hook観測）。
この文書は既存計画の現在地を統合する実行計画であり、過去の成果や承認履歴を削除しない。

## 1. 目指す状態と今回の範囲

一般運用案では、Codexに目的と完了条件を渡せば、メインが通常の調査・設計・実装・関連テスト・修正まで自走する。Astraの判断力を使い、小作業の多段委任と不要な承認待ちを減らす。重要な設計と変更には独立した検証を残す。別セッションから再開できるよう、技術的な正本と教訓への入口を保存する。

**この移行プロジェクトの当該セッションでは、ユーザー指定の分担を適用する。** 親Astraは要求整理・設計判断・優先順位・モデル選定・レビュー採否・統合管理を担当し、別agentが実装・編集・テスト・修正を担当する。これは上記の一般運用案に対する当該セッションの指定であり、他repoや将来すべての個人開発に強制委譲を設定するものではない。分業による速度改善は未測定である。

元の計画作成フェーズで実施したのは現状監査、公式情報との照合、計画作成、計画の独立反証・レビュー、Vercel AI Gatewayの別paneでの説明。ランタイム設定・既存skill・業務契約の変更、commit/push、実資産アクセス、自動Vault保存の有効化はその計画作成に含めない。

移行の完了を次の3つに分ける。

1. **開発移行**: 両repoで通常開発・テスト・必要なレビュー・引継ぎができる。
2. **wealth読み取り運用**: 対象・情報経路を確定し、実データ取得・集計を検証する。開発移行とは別の到達点。
3. **wealth更新運用**: Notion更新・月次履歴を検証する。読み取り成功から自動的に進めない。

## 2. 調査で確認した現在地

### Gitと設定

| 対象 | 観測した状態 | 計画への影響 |
|---|---|---|
| agent-crew | `main` / `875dd67062d7a16fc27017965066a99303e3d0a9`。AGENTS、.agents、.codex、共通hooks等が未追跡。既存tracked変更もある | 一括add・reset・cleanは禁止。移行対象の差分を限定して統合する |
| wealth-advisor（非公開の別repo） | `codex/operations-readiness` / `b63598f3d39944c73602dec76373b63a747b5d41`。README変更、設定・準備文書・scripts・テストは未コミット | 既存パイロットを作り直さず、運用準備と共通権限部分を分けて扱う |
| グローバルAGENTS | 日本語の指定のみ | 共通の自律範囲はrepo間で統一されていない |
| グローバルCodex config | `gpt-6-astra` / `medium`、`on-request`、`approvals_reviewer=user`、`default_permissions=developer` | 初期モデル変更は不要。速度の比較はこれを基準にする |
| 接続先 | 調査時のglobal configに`model_provider`と`model_providers`の明示なし。Gateway keyは環境に存在（値は読まず出力せず）。両repo configにもprovider指定なし | 過去ノートの「Vercelが既定」は現在ファイルの証拠にならない。起動済みpaneのproviderは別途実効値で確認する |
| CLI | `codex-cli 0.155.1` | 最新Web文書と実装差は新規セッションで確認する |
| global権限 | 作業repo/cacheに加え、`~/.codex/config.toml`、rules/skills/agents、Claude設定までwrite可 | 普通の開発から別paneへ影響を及ぼせる。操作の権限とタスク上の許可を分ける |
| repo権限 | wealthの`.codex/config.toml`はglobalと同名developer profileに合成する設計 | repo設定だけ見て実効範囲を判断しない |

### 指示・hook・知識

- agent-crewのAGENTSは既に「メイン直接実装、必要な独立レビュー」を採用。一方、Codex側`fable-class`は13,826 bytesでSonnet/Opus前提の委譲・API critic指定を含む。Claude側6,842 bytesと内容hashが違う。同じ名前でも同じ契約ではない。
- `.codex/agents`は旧17定義にdirect-reviewerを加えた18ファイル。工程補助用pm-estimation/pm-protocolも含む。一覧への出現を実務互換の証拠にしない。
- repoに旅行・ライフプランskillも存在し、旅行skillはglobal synced版とも併存、hashが異なる。削除前に意味差と利用元を確認する必要がある。
- 共通hook実装は再利用可能。原本は`config/crew-hooks.json`と`scripts/crew_hooks.py`。Codex入口は`./scripts/crew codex`。現状の入口は**自身のrepoへ固定**されており、wealthから呼んでもwealth用起動にはならない。
- `scripts/codex_hook_state.py`は`.codex/config.toml`全体を生成・hash検証する。wealthの権限installerも同じファイルを管理する。両者をそのまま横展開すると競合するため、所有区画の設計が先。
- global hookにSerena起動が2件、Claude由来の学び集計・Vault captureが残る。agent-crew入口は対象user hook 7件を無効化するが、他のuser hookは保持する。wealthの同等の実効状態は未検証。
- Vaultのcapture-sessionはheadless Claudeを起動する実装を含む。「Codexへ移したから学び抽出もOpenAIになった」とは言えない。今回は起動していない。
- 共通hookのStopはprivacy/lesson候補の確認に最大約6秒の待ちを設計している。実測の通常遅延ではない。全検査を毎ターン実行する必要性を見直す。
- このセッションではSessionStart/UserPromptSubmit相当の共通context注入を受信。古い「Codexで全く未確認」からは進展があるが、制御した新規CLIのStop E2Eの代用にはしない。
- QA未承認DONE 3件は既存問題。移行完了のために承認状態を書き換えない。

### 今回再確認した検証

| コマンド（repo root） | 結果 | 意味 |
|---|---|---|
| agent-crew: `python3.12 -m unittest discover -s tests -p 'test_crew*.py' -v` | 18件成功 | 共通core/adapter/launcherのfixture |
| agent-crew: `python3.12 -m unittest discover -s tests -p test_codex_hook_state.py -v` | 8件成功 | hook状態生成・衝突検出 |
| agent-crew: `python3.12 -m unittest discover -s tests -p test_install_crew_hooks.py -v` | 12件成功 | 設定生成・保持・復旧用backup |
| agent-crew: `python3.12 scripts/install_crew_hooks.py --check` | exit 0 | 生成hookと配置の一致 |
| agent-crew: `./scripts/crew --print-command codex` | exit 0 | 現在のlocal hook stateから起動引数を構築可能 |
| wealth: `python3.12 -B -m unittest discover -s tests -p test_operational_readiness.py -v` | 6件成功 | 静的確認プログラム。計算精度・実接続は対象外 |
| wealth: `python3.12 -B scripts/check_operational_readiness.py` | 基準一致、運用未許可・未検証 | パイロット境界維持 |
| wealth: `git diff --check` | exit 0 | tracked差分の空白検査 |

既存ノートにあるsandbox実機検証、過去review承認は過去証跡として扱う。今回は有料の比較実験、実資産計算、Notionアクセス、全機能E2Eは行っていない。

## 3. 最新AIに合わせて何を変えるか

「skillはあるほど悪い」「Astraなら規約不要」のどちらも採らない。

- 公式仕様ではskillは名前・説明から選ばれ、本文は必要時に読む。初期一覧にも予算があり、増えすぎると説明短縮・一部省略が起き得る。同名skillはマージされない。[公式Skills](https://learn.chatgpt.com/docs/build-skills)
- AGENTS.mdの研究には、成功率の一般的改善を認めず推論費用が平均20%以上増えた報告と、実行時間・出力token削減を観測した報告がある。対象モデル・タスク・指示が異なる。これらは**Astra上の当方のskill群の実測ではない**。適用先で比較する必要がある。[Gloaguenほか v2](https://arxiv.org/abs/2602.11988) / [Lullaほか v2](https://arxiv.org/abs/2601.20404)
- 短く正確な常設指示、実際に繰り返す仕事に限定したskill、難度に合わせたreasoningが公式の推奨。工程を増やすより、目的・制約・実行可能な検証コマンドを明確にする。[公式Best practices](https://learn.chatgpt.com/guides/best-practices)
- Astraは`low/medium/high/xhigh/max`のreasoningに対応。通常mediumを基準に、難しい設計でhigh以上を検討する。APIの対応値、Codex UIの設定、Gatewayの対応は区別する。[Astraモデル](https://developers.openai.com/api/docs/models/gpt-6-astra)
- ChatGPTログインのFast modeとAPI Priority/Gateway料金は同一でない。速度設定を盲目的に移植せず、実際の経路で機能・料金・遅延を確認する。[公式Speed](https://learn.chatgpt.com/docs/agent-configuration/speed)

今回の仮説は、**汎用モデル向けの細かい思考手順を減らし、この環境でしか分からない制約・検証・知識への入口に絞ると、品質を維持して完了までの時間を短縮できる**、というもの。実測前に成果とは主張しない。

## 4. グローバル・共通資産・repo・セッションの境界

管理元と適用範囲は別である。agent-crewで管理するファイルがすべてグローバル適用になるわけではない。

| 管理するもの | 正本・管理主体 | 適用先 | 内容 |
|---|---|---|---|
| 個人共通作業契約 | agent-crew内の短いテンプレート（新設案） | `~/.codex/AGENTS.md`、Claude用adapter | 日本語、依頼範囲の自走、既存変更保持、確認境界、証拠付き報告 |
| 個人実設定 | `~/.codex/config.toml` | このPCの各Codex起動 | モデル既定、アカウント固有設定。秘密情報はrepoへコピーしない |
| 共通開発権限・profiles | agent-crew内のversion管理テンプレート（wealthから移管案） | 指定した個人config/profile/rules | 通常開発・保守・読み取りreviewの用途別範囲 |
| 共通hook core/adapter | agent-crewの既存manifest/scripts | **opt-inしたrepoのみ** | 小さな機械判定、task scope、状態通知 |
| agent-crew固有契約 | agent-crew/AGENTS.md、docs、queue | agent-crewのみ | queue/QA、共通基盤変更、テスト、移行手順 |
| wealth固有契約 | wealth/AGENTS.md、分析skill、src/tests、ADR | wealthのみ | 資産の意味、計算、欠損、金融実行禁止、許可されたデータ経路 |
| 個人の旅行等skill | 管理元を1つ選んだ個人skill配布 | 必要な個人環境 | 開発repoで常時発動させない。既存版の差を先に確認 |
| 外部接続 | 個人認証＋repoの利用契約 | タスクが許可する対象だけ | MCPが存在することと利用権限を分離 |
| 1回のモデル/経路/担当 | profile/CLI・セッション指示 | 当該起動のみ | Gateway比較、担当task、レビュー観点、予算 |
| 技術的な進行・検証記録 | 対象repo/docs/plans | 対象変更 | HEAD、未コミット差分、テスト、未解決、再開コマンド |
| 横断の教訓・目的・入口 | Obsidianの既存契約に従う | 次回の関連作業 | 出典・適用条件・確認日・次の一手。技術原本を複製しない |

設定優先順位はCLI override、trusted repo設定、選択profile、user設定等のレイヤーがある。profileに書いたから必ず勝つと考えず、新規セッションの実効値を確認する。[公式Config](https://learn.chatgpt.com/docs/config-file/config-basic)

### 設定生成の所有権

提案: 共通テンプレートの管理はagent-crewに寄せ、**1つの出力ファイルを複数installerが全面所有しない**。最初は既存のglobal権限導入成果を保存し、wealth側からglobalを書き換える運用を停止する。repo固有設定、機械固有hook state、個人providerは独立区画として扱う。

比較した方式は「単一composerが全管理区画を合成」または「各installerが明示区画のみ更新」。本計画の採用提案は単一composer＋各区画の入力を分離。未知キー保持、dry-run、hashによる同時変更検出、再実行の一致、区画単位rollbackを受入条件にする。現在の全体hashを無視して別ツールが追記する実装は採らない。

移管時にはwealthの旧installerをglobal設定更新に使えない状態にし、移管先への案内またはversion不一致の明示停止を実装する。旧テンプレート再適用でglobal write権限が復活しないことを試験する。既存`~/.codex/rules/default.rules`・`developer.rules`も棚卸し対象に含め、別作業の承認済みルールを一括削除しない。maintenance profileの選択はOS権限の選択であり、依頼範囲外の操作承認を意味しない。

共通launcherの横展開は後段。`scripts/crew`へのsymlinkだけでwealth対応したことにしない。対象repoの明示引数・信頼済みmanifest・cwd・queue rootの一致を設計し、別repoへの混線をfixtureで検証する。queueを持たないrepoではqueue工程を適用せず、勝手に台帳を新設しない。それまではwealthは自身のCodex入口を使う。P4で共通launcherを選ぶ場合は、この検証完了を必須の前提とする。

## 5. 自律範囲と確認する範囲（採用案）

これは今後の常設契約案。今回の計画作成だけで永続的な権限拡大にはしない。個別の依頼で既に許可された操作は再確認しない。

| 操作 | 既定の扱い |
|---|---|
| 対象repo内の調査、編集、関連テスト、失敗修正、ローカル起動 | 依頼の目的に必要なら自走 |
| 既存lockfileに従う依存復元、公開公式情報の検索、cache書込み | 通常開発の範囲で自走 |
| 隔離branch/worktree、限定した独立調査・review | 依頼実現に必要なら自走。ただし現行セッション/管理ポリシーが委譲を制限する場合は従う |
| 既存依存の大規模更新、新しい外部サービス・有料機能・schema破壊を伴う選択 | 具体的差分・影響・代替案を用意して判断を求める |
| global provider、権限、共通skill、hookを他repoへ効かせる変更 | 明示された保守作業内でのみ実施。一連の変更集合に対して一度確認し、同じ範囲で再確認しない |
| commit | 通常の「実装して」では自動実行しない。commitまでの依頼なら指定差分だけ実行 |
| push、PR作成/投稿、merge、deploy、Issue close、通知 | 明示依頼された範囲で実行。未依頼なら成果と宛先を具体化した最後に確認 |
| 他者の未コミット変更破棄、force push、DB削除、他pane停止 | 具体的対象の明示確認が必要 |
| 指定先への匿名化した引継ぎ/教訓保存 | 採用後の許可済み保存root・内容範囲内で自走。外部同期経路も別途確定 |
| 新規認証、実資産読取り、Notion更新 | wealthの段階別契約に従う。接続と業務利用を混同しない |
| 金融の発注・注文画面・送金 | 引き続き禁止 |

OSのsandbox確認は文章の合意だけでは消えない。通常開発に必要なrepo/cache/networkを事前設定し、global設定変更権限は保守用途へ分ける。ただし全repoで設定ファイルの読み取りを禁止するという意味ではない。

`developer`を通常用途、`maintenance`をglobal設定編集用、`review`をread-only用途とする案。既存`review.config.toml`と`unattended-fix.config.toml`は保存し、旧sandbox指定とnamed permissionsの優先関係を試験してから整える。`never`で失敗を隠す運用やfull-accessの一律採用はしない。

## 6. Astra・委譲・品質の運用

### この移行プロジェクトの当該セッションで適用する体制

| 担当 | 所有する判断・作業 | 引渡し・確認 |
|---|---|---|
| 親Astra | 要求整理、設計判断、優先順位、実装者とレビュー担当のモデル選定、レビュー採否、成果の統合管理 | 対象・所有ファイル・受入条件・禁止事項を実装者へ渡す。判断待ちは親に集約する |
| 別agent（実装担当） | 指定された所有範囲の実装、編集、関連テスト、失敗修正、検証結果の報告 | 他者の未追跡を含む変更を保持し、範囲外の設計判断や外部操作は親へ戻す |
| 実装者と別contextのAstra | 重要変更の独立レビュー | 判定と根拠を親へ渡し、親が採否・再作業・統合を決める |

通常の実装担当モデルは`GPT-5.6 Sol`。難度またはリスクの高い作業は親の判断で`Astra`を選ぶ。重要レビューは実装者と別contextの`Astra`を使う。安価なモデルへ暗黙にfallbackせず、モデル変更が必要なら親が明示して判断する。担当とモデルの指定はこのセッションのものであり、共通設定・AGENTS・skill・hookを今回書き換える根拠にはしない。

### 将来の一般運用案（当該セッションの分担とは別）

| 作業 | メイン | 委譲・検証 |
|---|---|---|
| 局所修正・短い文書修正 | Astra mediumを基準、定型作業はlowを比較候補 | 自分で関連確認。計画文書・2段レビューを一律必須にしない |
| 複数ファイルの機能、難しい不具合 | Astra medium、必要時high | 短いSPEC/PLAN。仕様と品質の独立レビューが必要な対象を明示 |
| 共通権限、hook、provider、金融計算・データ経路 | Astraで設計を主導 | 設計反証、仕様準拠/品質を別の新規contextで確認。関連テスト必須 |
| 列挙・参照箇所・hash・件数 | 決定的なコマンド | LLMへの丸投げをしない |
| 独立した調査/ファイル群の実装 | 分割の利益を判断 | 親と子の担当が重ならず並行できる場合のみ。通常最大2子を提案 |
| 判断が曖昧、繰り返し失敗 | 原因・不足情報を整理 | 同じpromptで無制限再試行せず、範囲縮小または本人判断へ |

一般運用案で委譲を選ぶ場合、親は目標・受入条件・統合を担当し、子には対象、所有ファイル、禁止事項、検証コマンドを渡す。実装子に親の会話全文を渡さず、レビューは実装の思考過程から独立したcontextにする。同じモデルの新規contextでも相関した盲点は残るため、テストや不変条件を代用しない。

一般運用案での速い別モデルはまず比較候補に留める。Astraを暗黙に安いモデルへ変更しない。一般運用としての委譲先モデル・接続経路・cost上限は採用時に決める。今回の調査ではモデル間の性能順位、所要時間、分業による速度改善を測定していない。

## 7. skill・hookの整理案

独立二観点レビューの必須条件は、権限・外部副作用・データ送信境界・後方互換性・金融計算の意味を変える変更。ファイル数だけでは判定しない。単なる文言・整形や局所変更には文書一式と二段レビューを一律要求しない。現行AGENTS/skillとこの運用案をP2の同じ変更集合で整合させ、規約改訂前に軽量運用を適用済みとは扱わない。

| 現在の資産 | 方針 |
|---|---|
| `AGENTS.md` | 非標準の契約、実行/検証コマンド、危険境界、正本参照に絞る。設計の歴史や長い工程は参照先へ |
| `fable-class` | Codexではモデル名依存の強制routingを外す案。SPEC・代替案・証拠・重要変更reviewは残す。Claude版への影響は別に扱う |
| 旧17 agent | 全面移植を開発移行の条件から外す。まずメイン＋direct-reviewer。実際に使う責務だけ追加 |
| wealth分析skill | 保持フィルタ、分母、欠損、合算、鮮度、数値計算等は残す。共通の意味とruntime adapterを分離し、Claude/Codexの意味差をレビュー |
| 旅行・ライフプラン | 意味差を確認し個人用の正本に整理。Codex用repoコピーとglobal synced版を同時に維持しない |
| MCP/browser/document skill | 実際の用途があるものを保持。provider管理pluginのcacheを手で削除せず、有効化設定や配布元で制御 |
| SessionStart | 指定task、未完了、関連教訓への短い入口。全文の教訓・全queueを注入しない |
| UserPromptSubmit | 状態差分/重要変更のみ。毎ターン同じ警告の注入は減らす案 |
| Stop | 1回の継続要求と明確な未完状態。失敗検出は残す。重いprivacy全検査は公開前/対象変更時へ寄せる案を検証 |
| 学び抽出 | 毎Stopの追加LLM呼出しを通常開発の必須経路から外す案。節目でメインが根拠付き要約し保存する |

disable/移動はback up後、利用者・CLI/Appの両surface・plugin提供元の挙動を確認して実施する。skill数の削減だけを成功指標にしない。

## 8. Obsidianへ学びを残して再開する

既存の個人コンテキスト保存・再利用契約（非公開Vault資料）を維持する。検索DB・新たな自動記憶基盤の導入を今回の必須条件にしない。既存のcontext_memory.py等は未コミットの先行資産として保存し、別の計画として評価する。

既存契約では、利用者向け機能仕様・PDR・採用した業務ルールの正本もVaultにある。その役割は維持し、技術実装契約と区別する。今回新設するのは移行状況/引継ぎの入口であり、既存仕様をrepoへ移す計画ではない。

保存は「作業が終わる時」「中断時」「同じ失敗の再発を検出した時」。毎ツール・毎返答の保存を義務にしない。

最小の引継ぎ内容:

- 目的、依頼された範囲、現在地、次の一手、未決事項。
- repo/branch/HEAD、未コミット成果の場所と必要な内容hash。
- 実行した検証と結果、未実施の検証、残るリスク。
- 判断の理由と再検討条件、技術原本へのリンク。

repoには技術計画・検証・復旧コマンドを残す。Vaultはプロジェクト入口からそれを参照し、横断教訓は「状況→失敗→原因→次回の対応→証拠」を短く保存する。事実・仮説・採用済み・失効を区別する。新しいノートを作るより既存入口の更新で足りるならそれを使う。

再開は「該当project入口→現行planとGit→関連教訓上位数件→対象テスト」の順。Vaultに書いただけで完了とせず、**新規セッションが正しい次手へ戻れること**を受入試験にする。

当面はrepo内にVault用の安全な要約を作り、保存先・対象内容・同期先の許可を具体化してから書く。許可後は対象root内の節目の追記を毎回聞き直さない。生会話・認証情報・実資産本文は保存しない。既存の自動captureは別作業の設定として勝手に解除せず、対象repoでの有効状態を明示する。

## 9. 実行順序と完了条件

| ID | 実施内容・所有者 | 依存 | 完了条件・確認のタイミング |
|---|---|---|---|
| P0 | 別agentが両repo/globalの設定と未コミット差分のmanifestを作成。親が統合管理 | なし | 対象パス/管理者/版/適用状態が明確。他者変更を混ぜない。秘密値は記録しない |
| P1 | 共通権限の管理元をagent-crewへ整理。設定区画とprofile設計を確定 | P0 | 既存wealth成果を移管履歴付きで再利用。dry-run、競合検出、idempotence、rollback試験成功。global適用前に具体的差分を確認 |
| P2 | AGENTS/skill/agentを軽量化し、共通hooksを仕上げる | P1 | 二重発動と古いroutingを除去。既存38件＋追加した意味のあるテスト成功。新規CLIで開始context・Stop継続1回・再入終了を実証。最終品質再レビューとガイド更新 |
| P3 | 節目の引継ぎ/教訓保存と再開手順を導入 | P2と独立に草案可 | 許可済み保存rootへ匿名化要約。新規セッションが目的/版/未完/次手を再現。重複・古い記録の誤採用を防ぐ |
| P4 | wealthの開発作業を同じ共通契約で動かす | P1、必要なP2 | global設定をwealth installerが再所有しない。Notion未接続でも開発チェックが可能。計算fixtureの境界変更は具体案を先に確定 |
| P5 | 通常開発の比較評価、未コミット成果のレビュー/統合 | P2/P3/P4 | 品質・速度・承認待ち・引継ぎが基準を満たす。commit/PRは別途依頼された範囲で行う |
| P6 | wealth実データ読み取り運用（別マイルストーン） | 開発移行後、対象/情報経路の合意 | AGENTSとskillを同時更新し、既存G1〜G8を検証。実資産をLLM/中継へ渡すか、ローカル計算だけにするかを確定 |
| P7 | Notion更新/月次運用（任意） | P6＋具体的更新許可 | 履歴ADR不一致解消、冪等性・重複・部分失敗の試験。金融実行は含めない |

着手可能範囲はP0〜P5の「開発移行」。P6/P7の本人データ判断を待つことを理由に、開発移行まで停止させない。実装開始時にこの計画を小さな変更集合へ切り、各集合の完了条件を確認して進める。日数の確約は実測前には行わない。

### 比較評価の方法

P0で課題・開始snapshot・採点基準と現行baselineを固定し、各変更段階でも同じ代表課題で効果を確認する。P5は総合確認の段階であり、初めて計測を開始する段階ではない。

安全境界は両条件で同じに保つ。A=現行の開発指示、B=短い共通契約＋必要時skill。モデル/effort/provider/CLI版を固定し、まず指示だけ変える。hook・権限・review工程・モデル・Gateway速度は一度に変更せず、その後の別実験にする。

両repoで合計6タスク程度（局所バグ、横断変更、hook異常系、文書整合、wealth静的準備、引継ぎ）を選び、同じ開始snapshotから各条件2回、実行順を入れ替える。少数比較なので統計的な性能保証は主張しない。各runは独立worktree/fixtureで隔離し、先の回答を後のrunへ渡さない。

計測: 開始から受入完了までのwall time、承認回数と待ち時間、LLM/tool時間、token/費用（取得できた範囲）、再修正回数、reviewの見落とし、範囲外変更、引継ぎの成功。最初の返答の速さだけで評価しない。

採用基準案: 重大な品質・権限違反0、既存の受入条件すべて合格、通常許可内の操作で追加承認0、同等以上の引継ぎ成功。中央値の完了時間20%短縮を目標とするが未達なら原因を分類し、品質合格だけで「高速化完了」としない。費用/時間上限は比較run開始前に具体化し、上限到達時は記録して停止する。

wealthの現行契約は架空資産例の生成も禁じているため、計算精度fixtureを今の段階で勝手に実行しない。実データ禁止は維持したまま「既存の非個人テストfixtureを開発検証に使う」限定案をP4で準備し、適用後に計算テストを評価対象へ追加する。

## 10. 将来の一般運用案の代替案と判断

| 案 | 利点 | 問題 | 判断 |
|---|---|---|---|
| Claudeの全agent/skill/hookを同じ形で移植 | 見かけの操作を揃えやすい | 古いモデル前提、二重管理、不要な委譲、実装差の吸収に時間 | 不採用 |
| すべて外して素のCodexにする | 最小構成、比較baselineには有用 | 資産計算の非標準条件、QA、引継ぎを失う | 運用案として不採用 |
| 短い共通契約＋repo固有skill＋選択的review | Astraの自律性と現場制約を両立 | 境界と評価が必要 | 推奨 |
| 全設定をglobalへ寄せる | 導入箇所が少ない | 別repo/paneへ即波及、共有障害 | 不採用 |
| 毎作業を複数agentで分業 | 大きい独立作業では並列化 | 小作業では待ち・引継ぎ・統合の費用 | 条件付き採用 |

## 11. Vercel AI Gatewayの位置づけ

Codexという作業用クライアント、Astraというモデル、OpenAI/Vercelという呼出し経路、MCPというデータ接続を分ける。Gatewayを導入しても常にそこを経由する義務はない。現在のセッションがどの経路かは実効設定で確認する。

提案はOpenAI系モデルを使い、OpenAI直接経路を基準、Gatewayを明示profileで比較可能にすること。ユーザーがGatewayを既定として選ぶ場合も、profile単位で再現し、別作業中にglobal providerを切り替えない。モデル名・key・endpointをセットで扱い、keyの有無だけで疎通成功としない。

Vercel公式にはCodex用`/codex/v1`互換endpointと`openai/gpt-6-astra`の例がある。API互換と実際のtool/streaming/長時間継続/再開の動作は別に試験する。秘密のない短い課題で検証し、wealth資産データを接続確認に使わない。[Vercel公式Codex設定](https://vercel.com/docs/ai-gateway/coding-agents/openai-codex)

Gateway説明は別paneで行う。料金、ルーティング、ログ/保持、API課金とChatGPT契約の違いはそこで出典付きで確認する。アカウント固有の課金・残高・保存設定は一般仕様だけで断定しない。

## 12. 根拠・レビュー・引継ぎ

参照した旧計画と正本。非公開資料は公開cloneに含めず、参照名のみを示す:

- agent-crew移行状況、wealth移行状況、失敗パターン、ADR索引（いずれも非公開Vault資料）
- 共通hook既存計画（非公開の過去資料）、[既存起動ガイド](../codex-direct/README.md)
- wealth運用準備、権限導入証跡（非公開の別repo資料）

独立反証の7指摘を反映し、別々の新規contextで仕様準拠・品質の両レビューがAPPROVED。対象本文hashと検証範囲は[レビュー記録](2026-09-21-codex-operating-model-reviews.md)を参照。この承認は追補前の計画本文に対するもの。今回のセッション分担の追補とSite更新は親の独立レビュー待ちであり、設定適用・移行実装・性能改善の完了も意味しない。

次の一手: 親が今回の計画追補とSite更新を独立レビューし、採否と公開の続行を判断する。その後、P0/P1の具体的変更集合を作る。実装を依頼された場合も、この調査時点のglobal設定を固定事実にせず再取得する。設定適用前には対象ファイルの直前hashを確認し、他セッションの変更があれば止めて統合する。
