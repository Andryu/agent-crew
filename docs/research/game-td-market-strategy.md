# 群変（ぐんぺん）市場・販売戦略（Go-to-Market）レポート

**要約（3行）**
GitHub Pages無料公開→unityroom/itch.ioでB/C層への無料到達を広げる→継続判定後にSteam（Next Fest含む）で収益化検討、の三段階が最も無理がない。「敵が適応学習する」を看板にした商業的成功例は調査で見つからず、群変は先行者的ポジションに立てるが説明コストも自分たちで負う必要がある。AI（遺伝的アルゴリズム）の対外発信はCygames AI Studio炎上（2026-01）を教訓に、「生成AIアセット不使用」を先に明言する設計にすべき。

---

## 1. プラットフォーム戦略

### 選択肢の比較

| プラットフォーム | 到達層 | コスト | 契約・審査負担 | タイミングの目安 |
|---|---|---|---|---|
| **GitHub Pages（現状）** | ほぼゼロ（オーナーの声かけ経由のみ） | ¥0 | なし | プロトタイプ〜1次プレイテスト（現在） |
| **unityroom** | 日本語圏、TD/ブラウザゲーム好きの個人開発者コミュニティ（B層に近い） | ¥0 | 審査なし、Unity製前提だがVanilla JS/Canvas製も規約上は投稿可否要確認 | 2次プレイテスト拡大期 |
| **itch.io** | 英語圏インディーコミュニティ、開発者同士の相互プレイ文化（C層に強い） | ¥0（デフォルト90/10、価格は自由設定） | 審査なし、即日公開 | 2次プレイテスト拡大期、Steam前の検証としても定石 |
| **Steam（ページのみ／ウィッシュリスト）** | 最大母数だが埋もれやすい。B層の可視性は高いが到達には時間がかかる | ページ作成自体は無料。正式リリースには**$100の審査料**（売上$1,000到達で慈善団体へ還元） | Steamworks審査あり、コンテンツサーベイ（AI開示含む）必須 | 継続判定後、収益化を検討する段階 |
| **Steam Next Fest** | TDジャンル注目層に短期集中で届く。デモ必須 | $0（ページ・デモは別途用意） | デモの完成度が問われる | 収益化検討段階で、正式リリース前のシグナル取得に使う |
| **国内インディーイベント（東京ゲームダンジョン／デジゲー博／BitSummit）** | 対面でC層（技術者・インディー好き）に直接説明できる | 東京ゲームダンジョン ¥3,300〜／デジゲー博 ¥7,000〜／BitSummit ¥33,000（学生割あり） | 東京ゲームダンジョンは**先着順・審査なし**（個人開発者に最も開かれている）。BitSummitは規模が大きい分、審査・準備負担も大きい | 収益化を意識し始めた段階、または継続判定後の露出強化 |

出典: [Fungies.io Steam vs Itch.io 2026](https://fungies.io/steam-vs-itch-io-indie-developers/)、[unityroomとは（indie-game.hatenablog）](https://indie-game.hatenablog.com/entry/2025/08/04/075021)、[unityroom公式](https://unityroom.com/)、[東京ゲームダンジョン ファミ通記事](https://www.famitsu.com/article/202502/33624)、[デジゲー博出展レポート](https://3dunity.org/game-work/to-be-game-creator/digigameexpo-repo/)、[BitSummit X-Roads募集情報](https://indiegamesjp.dev/?p=4888)

### B/C層に届く順序の提案

1. **GitHub Pages（現状維持）**: 巡室と同じ「オーナーの声かけ→友人5名→SNS/Discord 10〜20名」を継続。まずは部門憲章のプレイテスト回収を薄めない。
2. **unityroom並行投稿**: 審査なし・即日公開・日本語TD好きコミュニティに直接届く。**B層（元TD世代）に最も安く到達できる一手**。ただしVanilla JS/Canvas製ゲームの投稿可否・埋め込み形式は事前に規約確認が必要（unityroomはUnity製ゲームが主流のため、iframe埋め込み等の形式次第で扱いが変わる可能性がある。**要確認**）。
3. **itch.io並行投稿**: 英語圏のC層（インディー好き・技術者）に届く。「進化する敵」というAIネイティブな切り口はitch.ioの開発者コミュニティで語られやすい。無料公開のまま、devlog形式で「遺伝的アルゴリズムで敵が進化する仕組み」を短い技術記事として添えるとC層の拡散が起きやすい（後述4章）。
4. **（継続判定後）Steamページ作成・ウィッシュリスト収集**: まだ無料段階でも先にページだけ作り、チャレンジリンクや告知にウィッシュリストへの導線を混ぜる。Steam Next Festは正式リリース前のデモ品質チェックとしても機能する。
5. **（収益化検討段階）国内インディーイベント出展**: 東京ゲームダンジョンは低コスト・審査なしで個人開発者向け。オーナーが対外説明を直接行う場が必要になった時点（L0の判断）で検討。

---

## 2. 価格・収益モデル

### 類例の価格帯と根拠

| タイトル | 形態 | 価格・数値 | 出典 |
|---|---|---|---|
| **Thronefall**（2人開発） | Steam買い切り | $12.99。初年度100万本、EA数ヶ月で31.5万本・返品率6.9%、発売2ヶ月時点で35%以上が5時間以上プレイ | `docs/research/td-hits-analysis.md`（[GameDiscoverCo](https://newsletter.gamediscover.co/p/deep-dive-how-thronefall-went-minimal)、[Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/thronefall)） |
| **Emberward**（ソロ開発） | Steam買い切り | $14.99。レビュー2,406件中97%好評（Overwhelmingly Positive） | [Emberward on Steam](https://store.steampowered.com/app/2459550/Emberward/)、[Play Indies #4](https://www.bighungry2x.com/playindies/emberward) |
| **スイカゲーム** | Switch買い切り／スマホ基本無料 | Switch版240円（税込）。iOS版は3ヶ月弱で単体累計収益が約200万ドル（約3.1億円）に迫る、総DL300万超 | [4Gamer](https://www.4gamer.net/games/764/G076493/20240416011/)、[日経クロストレンド](https://xtrend.nikkei.com/atcl/contents/watch/00013/02354/) |
| **Rogue Tower**（ソロ開発） | Steam買い切り | 推定累計粗収益約$299万（第三者推計ツールのため参考値） | [steam-revenue-calculator.com](https://steam-revenue-calculator.com/app/1843760/rogue-tower) |
| **Tangy TD**（ソロ開発・4年制作） | Steam買い切り | 発売1週間で粗収益$245,123・28,078本・レビュー好評率約89% | [spilled.gg](https://spilled.gg/developer-steam-revenue-hours-tower-defense-game-sales/)、[gamingpromax.com](https://gamingpromax.com/tangy-td-solo-dev-cakez-250k-steam/) |

### どの段階でどれを検討すべきか

- **プロトタイプ段階（現在）**: 無料以外の選択肢はない。部門憲章がすでに「追加課金ゼロ」を前提にしており、これは変えない。
- **2次プレイテスト拡大〜継続判定前**: 無料のまま。unityroom/itch.ioは投げ銭（pay-what-you-want）機能があるが、**プロトタイプ段階で投げ銭導線を作ると計測目的（継続意向・2周目到達率）が濁る**ため非推奨。
- **継続判定（09-30）後、Steam展開を検討する場合**: 買い切りが妥当。価格帯は**Thronefall（$12.99）〜Emberward（$14.99）の水準**が同ジャンル・同規模チームの相場。スイカゲームの240円はモバイルの衝動買い価格帯であり、PC/Steamの「TDとして遊びごたえを期待する」B層には安すぎて逆に「浅いのでは」という懸念を生みうる（ジャンル文化の違いに注意）。
- **広告モデル**: ブラウザ版に広告を入れる案は、部門憲章の「外部SaaS新規契約なし」原則と摩擦がある（広告ネットワーク契約が必要）。**優先度は低い**。

### 有料化に進む判断シグナル（無料段階で何が出れば）

1. 部門既存指標（有効回答15件・平均3周以上・継続意向50%以上）を満たしている
2. プロダクトデザイン文書の固有指標「群れが合わせてきたと感じたか」平均**3.5以上**
3. チャレンジリンクの自然発生率（`challengeReceived`比率）が一定以上あり、届け方が機能している証拠がある
4. （Steam展開を検討する場合）Steam Next Festのデモでウィッシュリスト転換率**20%以上**（後述4章の基準）

---

## 3. B/C層への到達チャネル（日本＋英語圏）

### チャネル別の事実整理

| チャネル | 有効性の根拠 | 群変への含意 |
|---|---|---|
| **X（Twitter）** | 「コミュニティ形成には効くが、単独でウィッシュリストを大きく動かすことは稀」との分析がある一方、個別の成功例もある（下記） | 継続的な発信より「変異レポート」「負けた画」など見せ場の切り抜きを繰り返し流す方が効く |
| **Reddit** | r/TowerDefense固有のルールは調査で確認できなかった（**見つからなかった**）。一般則として自己宣伝は投稿の10%以内に抑える「10%ルール」があり、r/gaming（数千万人規模）は開発者の自己宣伝にほぼ厳格に対応、r/IndieGaming（39万人）・r/indiegames（23.5万人）の方が現実的 | まずr/IndieGaming等でフィードバック依頼形式（スクリーンショット＋動画＋「感想を聞かせて」）から入るのが定石 |
| **Discord** | TDジャンル専用の大規模Discordコミュニティの実績数値は確認できなかった（**見つからなかった**）。一般的な開発者コミュニティ（r/gamedev系Discord等）への参加は定石とされる | 数値的根拠が薄いチャネルであることを明記した上で、コスト低いので並行実施は妨げない |
| **YouTube/配信者** | Tangy TDは「開発者本人が売上を見て泣く動画」が拡散の起点になり、既存の透明性ある開発ログで築いたコミュニティが初動を支えた | 群変も「進化に負けた瞬間」「変異レポートを見て驚く瞬間」など感情の動く場面を短尺で見せる方が配信映えする |
| **BitSummit／デジゲー博／東京ゲームダンジョン** | 1章参照。東京ゲームダンジョンが個人開発者に最も開かれている（審査なし・低コスト） | オーナー稼働（L0）が必要なため、優先度は継続判定後 |
| **Steam Next Fest** | デモ→ウィッシュリスト転換率は目安として15〜25%が通常、25〜35%で良好、40〜55%で非常に良好。15%未満はデモに問題があるサイン | 群変のデモ（チャレンジリンク付き）を出す場合、この転換率を成功指標に使える |

出典: [gamedeveloper.com Reddit tips](https://www.gamedeveloper.com/business/don-t-get-downvoted-some-tips-for-promoting-your-indie-game-on-reddit)、[cloutboost.com](https://www.cloutboost.com/blog/how-to-market-a-video-game-on-reddit-the-complete-2025-guide-for-game-developers)、[alineaanalytics.substack.com](https://alineaanalytics.substack.com/p/wishlist-to-buyer-conversions-for)、[strayspark.studio](https://www.strayspark.studio/blog/steam-next-fest-demo-optimization-wishlists)

### 個人開発者が実際に成果を出した事例（数値付き・成功／失敗セット）

**成功**
- **Tangy TD**（ソロ・4年開発）: 発売1週間で$245,123・28,078本、レビュー好評率89%。開発ログで築いたコミュニティ＋バイラルクリップが決め手（[spilled.gg](https://spilled.gg/developer-steam-revenue-hours-tower-defense-game-sales/)）
- **Tiny Glade**（2人開発）: 有料マーケティング費用ゼロで**ウィッシュリスト100万超**を達成（TDではないが少人数×口コミの実証例として参考、[opgamemarketing.substack.com](https://opgamemarketing.substack.com/p/tiny-glade-an-indie-game-by-2-devs)）
- **Ouroboros King**: ウィッシュリストが500→20,000へ2週間で急伸。TikTok/X経由でTikTokフォロワー36万・1,000万いいねを獲得（[opgamemarketing.substack.com](https://opgamemarketing.substack.com/p/tiny-glade-an-indie-game-by-2-devs)内の言及）

**失敗・埋没**
- **Brigador**（5年開発・破壊表現が特徴）: Steamレビュー好評率94%と評価は高いのに、レビュー数・売上が伸びず苦戦。開発者が経緯をImgurに公開している（[Kotaku](https://kotaku.com/what-happens-after-an-indie-game-fails-1784062530)）— **評価の高さと商業成功は別物**という教訓
- itch.io上の無料TD多数（Dawn of Defense、PokéPath TD等）は、プレイ数やレビュー数を公開しておらず「埋もれているかどうか」自体を定量化できなかった（**見つからなかった**）。これは「無料ブラウザTDは可視化された失敗データがほぼ存在しない＝埋もれても誰も気づかない」というリスクの裏返しでもある

---

## 4. 競合ポジショニング

### 既存TD強豪との対比（設計文書の既存分析を土台に整理）

| タイトル | 売りの核 | 群変との対比 |
|---|---|---|
| BTD6 | 塔を「自分が育てる」（3系統×5段階アップグレード） | 群変は「敵が育つ」— 主語が逆 |
| Kingdom Rush | 敵ごとに違う正解を要求する対処パズル＋能動介入 | 群変は敵側の性質が固定でなく**動的に変化**する点が異なる |
| Thronefall | ジャンルの脂身を全部落として本質だけ磨く | 群変も「進化の知覚」1点に設計コストを集中する方針で一致（`docs/design/game-td-evolve-design.md`） |
| ローグライトTD群（Rogue Tower/Isle of Arrows/Emberward） | 周回の変化源はRNGドラフト（タイル引き・テトリス壁・カード） | 群変の変化源は「進化」であり、RNGに頼らない点が差別化軸（`docs/research/td-hits-analysis.md` で既指摘） |

### 「敵が適応学習する」を売りにした既存タイトルの調査結果

- 学術研究では、TDの敵AIコントローラの評価や配置最適化に遺伝的アルゴリズムを用いる論文が複数存在する（例: [Automated Evaluation for AI Controllers in Tower Defense Game Using Genetic Algorithm](https://link.springer.com/chapter/10.1007/978-3-642-40567-9_12)、[Adaptive AI to play tower defense game](https://www.researchgate.net/publication/221633792_Adaptive_AI_to_play_tower_defense_game)）。ただしこれらは**研究目的のプロトタイプであり、商業的な販売実績・レビュー実績は伴わない**。
- itch.io上に「The Abbattoir Intergrade」という、遺伝的アルゴリズムでクリーチャーのステータスを進化させるタワーディフェンス系ゲームが存在するが、レビュー数・プレイ数などの実績指標は公開されておらず確認できなかった（[itch.io tag: genetic-algorithms](https://itch.io/games/tag-genetic-algorithms)）。
- **結論: 「敵がプレイヤーに適応して進化する」ことを主要な差別化フックとして商業的に実証成功した既存TDタイトルは、今回の調査では見つからなかった。** 群変はこの軸でほぼ手つかずのポジションに立てる可能性が高いが、裏を返せば「market pull（既に需要が証明されている）」の裏付けもない、先行リスクを自分たちで取る立場になる。

---

## 5. 個人開発TDの実績分布（成功3件・埋もれた例3件）

**成功例（売上・DL数・レビュー数が確認できたもの）**

| タイトル | 開発体制 | 実績 | 何が違ったか |
|---|---|---|---|
| Tangy TD | ソロ（Cakez、4年） | 発売1週間$245,123・28,078本・好評率89% | 開発の透明性（配信・SNSでの制作過程公開）で発売前からコミュニティを持っていた。バイラルな感情的瞬間（開発者本人の反応）が拡散のトリガー |
| Emberward | ソロ | レビュー2,406件中97%好評、"phenomenal numbers"と評される販売実績 | トレーラー・プレスキット・SNS更新まで全て自力でこなし、ローグライトTDのRNG周回設計をブレなく実行 |
| Thronefall | 2人 | 初年度100万本、$12.99、返品率6.9%（業界平均より大幅に低い） | 「小さく作って完成させる」を徹底し、機能を削ることに時間を使った（開発者本人のインタビューでの明言） |

**埋もれた／苦戦した例**

| タイトル | 開発体制 | 実績 | 何が違ったか |
|---|---|---|---|
| Brigador | 少人数（5年開発） | Steam好評率94%だがレビュー数・売上が伸びず、開発者が苦境をImgurで公開 | **評価の質と可視性は別問題**。目立つ「フック」がなく発見されにくかった |
| itch.io上の無料TD群（Dawn of Defense、PokéPath TD等多数） | 主に個人 | プレイ数・レビュー数が非公開で実績が可視化されていない | 「埋もれている」こと自体が観測不能——**届け方の設計（チャレンジリンク等）がないと、無料公開だけでは実績すら残らない** |
| 一般的な「王道TD」新作（差別化フックなし） | 様々 | `docs/research/td-hits-analysis.md`にある通りジャンルは飽和状態で、フックのない新作は埋没しやすいとされる（Steamの専用フェスができるほど競合が多いことの裏返し） | フックの有無が生存を分ける、というのが人気TD分析の一貫した結論 |

---

## 6. AI関連の対外発信リスク

### Cygames AI Studio炎上（2026-01）の教訓

- 2026年1月9日、Cygamesが生成AI活用の子会社「Cygames AI Studio」設立を発表したところ、**発表24時間でリプライ2,206件・リツイート7,051件・インプレッション918万回、9割以上がネガティブ反応**という炎上が起きた（[テツメモ on X](https://x.com/tetumemo/status/2009952176471478649)）。
- Cygamesは1月14日に謝罪し、「画像生成AIのアウトプットは含まれず」「無断で生成物をコンテンツに使用しない」ことを明言した（[Game*Spark](https://www.gamespark.jp/article/2026/01/14/161576.html)、[ITmedia](https://www.itmedia.co.jp/aiplus/articles/2601/14/news113.html)）。
- **教訓**: 「AI活用」を先に打ち出し、詳細説明を後回しにすると、たとえ実態が無害（今回は「生成AIアウトプットは含まれない」）でも炎上する。**日本市場では「AI」という語だけで身構えられる**。説明の順序が重要。

### Steam AI開示ポリシー

- Steamは「コンテンツサーベイ」内でAI開示を必須化しており、2026年1月の更新で対象が明確化された。**プレイヤーが実際に消費する最終コンテンツ（アート・音声・台詞）を生成AIで作った場合のみが開示対象**であり、開発時の裏方効率化ツール（コーディング支援等）は対象外と明言されている（[PC Gamer](https://www.pcgamer.com/software/ai/steam-updates-ai-disclosure-form-to-specify-that-its-focused-on-ai-generated-content-that-is-consumed-by-players-not-efficiency-tools-used-behind-the-scenes/)、[Steamworks Content Survey](https://partner.steamgames.com/doc/gettingstarted/contentsurvey)）。
- 開示は「Pre-Generated Content」（開発時に生成し同梱するもの）と「Live-Generated Content」（実行中に動的生成されるもの、例: 動的NPC台詞）の2バケットに分かれる。
- **群変への適用**: 群変の遺伝的アルゴリズムは、ゲームロジック内で敵のステータス（数値）を進化させるものであり、プレイヤーが消費する「アート・音声・台詞」を生成するものではない。Steamの2026年1月更新の定義に従えば、**形式的な開示義務には該当しない可能性が高い**。ただし最終的な該当判断はSteamworksのコンテンツサーベイ提出時に確認が必要（**要確認**、断定はできない）。

### どう言うべきか（提言）

1. **先に「不使用」を明言する**: 「絵・音・文章はすべて人力（コード生成含む）で、生成AI・LLMは一切使っていません」を先に置く。Cygamesの逆順（AI活用を先に言って後から補足）を避ける。
2. **「AI」より「進化」「遺伝的アルゴリズム」を主語にする**: 「AIが敵を強くする」ではなく「群れは、あなたの守り方に合わせて進化する」（プロダクトデザイン文書の一文の約束をそのまま対外発信にも使う）。技術用語（遺伝的アルゴリズム）は補足情報として、興味を持った人（C層）が深掘りできる形（devlog等）に留める。
3. **LLM不使用を強調する対象は限定的でよい**: 一般プレイヤー（B層）向けの告知では技術詳細を語る必要はなく、「進化する」という体験の一文で十分。技術詳細を語るのはitch.io devlogやC層向けのX投稿など、興味を持った人が自分から読みに来る場に限定する。

---

## 7. 提言: 段階別GTMロードマップ

### ロードマップ案

| 段階 | 時期目安 | やること | 収益モデル | 主要チャネル |
|---|---|---|---|---|
| **0. プロトタイプ** | 現在（開発中） | GitHub Pages公開、友人+SNS/Discordでの1次〜2次回収（部門憲章どおり） | 無料 | オーナー声かけ（L0） |
| **1. プレイテスト拡大** | 継続判定（09-30）まで、または判定後すぐ | unityroom・itch.io へ横展開。同じチャレンジリンク・アンケート機構をそのまま使う | 無料（投げ銭導線は入れない） | unityroom（B層）、itch.io devlog（C層） |
| **2. 公開拡大** | 継続判定後、部門固有指標達成を確認してから | Steamページ作成・ウィッシュリスト収集開始。Steam Next Festへのデモ出展を検討。国内インディーイベント（東京ゲームダンジョン優先）出展を検討 | まだ無料（ウィッシュリストのみ） | Steam、東京ゲームダンジョン等 |
| **3. 収益化検討** | 段階2のシグナルが出揃った時点 | Steam買い切りリリース判断。価格帯$9.99〜14.99（Thronefall〜Emberward水準）を軸に検討 | 買い切り（無料ブラウザ版は認知用に残す二段構えも選択肢） | Steamストア、既存コミュニティへの告知 |

### オーナーが決めるべき事項（複数案を残す）

1. **公開拡大の順序（unityroom先行 / itch.io先行 / 同時）**: unityroom先行は日本語B層に直接安く届くが、審査なし・投稿形式（Vanilla JS/Canvas製の可否）を先に確認する必要がある。itch.io先行は英語圏C層・開発者コミュニティに強いが、無料TDが多数埋もれている市場でもある。同時実施も可能だが、巡室と同じく「回収の分散に注意」が必要（設計文書のミニADRと同じ論点）。
2. **収益化の方針（Steam買い切り / 無料+投げ銭 / 当面判断保留）**: 今回の調査では類例（Thronefall $12.99、Emberward $14.99）が示す相場観は明確だが、プロトタイプ段階でこれを決め切る必要はない。ただし「次弾以降も含めた方針」を早めに握っておくかどうかはオーナー判断。
3. **AIの対外呼称の踏み込み方（技術を語らない / 「遺伝的アルゴリズム」を看板にする）**: Cygames前例を踏まえた慎重派（体験の一文のみで押す）と、積極派（C層拡散のために技術詳細をむしろ強みとして語る）の両方に一理ある。どちらの温度感で対外発信するかは、対外コミュニケーションがL0（オーナー専権）である以上、オーナーが決める事項。
