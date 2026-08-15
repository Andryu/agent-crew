# ゲーム部門プロトタイプ2「群変（ぐんぺん）」設計文書（進化する群れのタワーディフェンス）

> ゲーム部門 次弾候補の1本目。壁打ちメモ: `docs/research/game-ideation-2026-08.md`（2026-08-15 オーナー合意: TD→ソウルライクの順、抽象図形＋免疫の薄い皮、着手は巡室判定前）。
> ブランチ `feature/game-ideation`。巡室（`game-prototype/loop-room`、PR #171）とは独立したディレクトリで実装し、Pagesは `/evolve-td/` 配下に置く。

## SPEC

### 要求の再記述
敵の群れがウェーブごとにプレイヤーの防衛配置に対して進化するタワーディフェンスを、14日規模のブラウザゲームプロトタイプとして実装する。「群れが自分に合わせてきた」と知覚できることを最重要の検証点とし、チャレンジリンク（URL共有）で他人に届く導線を最初から持たせる。巡室と同じアンケート＋JSONエクスポートで継続意向・2周目到達率を回収する。

### 暗黙の前提
- 巡室の設計文書のテーゼ・技術選定・デプロイ・計測方針をそのまま継承する（Vanilla JS + Canvas、ビルドなし、GitHub Pages、localStorage＋ゲーム内アンケート＋JSON手動エクスポート、外部SaaS契約なし）
- 部門原則「AIはコンテンツ供給者でなく攻略対象のシステムに置く」に従い、進化はルールベース（遺伝的アルゴリズム）で完結させる。LLM・外部通信は使わない
- 実装はSonnetサブエージェントに委譲し、オーケストレーターは設計・レビュー判定に専念する（fable-class）
- プレイテスター募集・SNS投稿はL0＝オーナー専権。AI側はデプロイ可能な状態まで整える

### テーゼ
**このプロトタイプの価値は「進化がプレイヤーに知覚されるか」に集約される。進化モデルの精巧さではなく、変化が見た目とレポートで読めること、そして読んだ上で配置を変える手段があることに設計コストを集中し、それ以外（塔の種類・マップ数・メタ進行）は最小にする。**

## PLAN — 代替案比較

### 進化の変化源
| 案 | 所感 |
|---|---|
| 固定ウェーブ表（通常のTD） | 進化なし。部門原則から外れる |
| ランダム変異のみ（評価なし） | 「変わる」が「合わせてくる」にならない。知覚されない |
| **評価付き遺伝的アルゴリズム（採用）** | 到達距離・与ダメで個体を評価し上位を交配。防衛の弱点が次ウェーブに反映される |
| 探索（プレイヤーの配置に対して最適経路・最適耐性を直接計算） | 最適化が強すぎて理不尽化しやすく、変化の「過程」が見えない。却下 |

### マップ構造
| 案 | 所感 |
|---|---|
| 自由経路の迷路型（壁で経路を作る） | 経路探索＋進化の相互作用が複雑。14日では調整しきれない。却下 |
| **固定3レーン（採用）** | 「レーン嗜好」遺伝子が素直に効き、配置での対抗（そのレーンに塔を寄せる）が直感的 |

### 見た目
| 案 | 所感 |
|---|---|
| ドット絵・キャラクター | 素材コスト大。AI生成画像は拒否反応リスク |
| **抽象図形＋遺伝子の見た目直結（採用）** | 速度=細長さ／体力=輪郭の太さ／耐性=色／体格=大きさ。進化がそのまま見える。名称・フレーバーのみ免疫（白血球vs病原体）で味付け |

### 届け方
| 案 | 所感 |
|---|---|
| なし（Pages URLのみ） | 巡室と同じ課題（届け方）を繰り返す |
| **チャレンジリンク（採用・v1）** | seed＋初期資金をURLハッシュに埋め込み、同条件で到達ウェーブを競う。サーバ不要 |
| 攻め手モード（非同期PvP） | 相手の防衛配置を受け取り遺伝子ポイントで群れを設計して攻める。魅力的だが第2のゲームモードになる。**v2へ送る** |

## ゲームデザイン仕様（実装者に裁量を残さないための確定事項）

### 用語・フレーバー
- 塔=「免疫細胞」、敵=「病原体」、拠点=「臓器」。表示名は日本語、フレーバーは表示名のみ（設定テキストは書かない）
- 塔4種: 汎用「好中球」／熱「マクロファージ」／凍「インターフェロン」／電「抗体」

### 盤面
- グリッド **12列×8行**、セル48px（論理解像度 576×384、CSSで画面幅に合わせて拡大縮小、モバイルはタップ配置）
- レーンは行1・行4・行7（0始まり）の**横一直線3本**（左端から右端の臓器へ）。レーン上のセルには塔を置けない
- 臓器は右端に1つ（3レーン共通）。ライフ **20**

### 塔（`config.js` に一元定義、実装者は数値を変えない）
| id | 表示名 | 属性 | 費用 | 射程(セル) | 攻撃間隔(s) | ダメージ | 特殊 |
|---|---|---|---|---|---|---|---|
| basic | 好中球 | none | 50 | 2.0 | 0.5 | 6 | なし |
| heat | マクロファージ | heat | 100 | 2.0 | 1.0 | 14 | 着弾点半径0.8セルに範囲ダメージ |
| cold | インターフェロン | cold | 100 | 2.5 | 0.8 | 8 | 命中対象を1.5秒間 速度60%に |
| bolt | 抗体 | bolt | 120 | 3.5 | 1.4 | 30 | 単体・最長射程 |
- ターゲット: 射程内で**最も臓器に近い**個体。売却は費用の70%返金。配置はウェーブ中も可（ただし進化の面白さのため、ウェーブ間の配置フェーズを主とし、ウェーブ中配置は許可するだけ）

### 経済
- 初期資金 **300**（チャレンジリンクで上書き可、範囲150〜600）
- 撃破報酬 = `4 + floor(wave * 0.5)`。ウェーブクリアボーナス `+40`
- 到達被害: 体格 `size >= 1.2` の個体は 2ライフ、それ以外 1ライフ

### 敵の遺伝子（genome）
```js
// genome: { speed: number, hp: number, resist: 0|1|2|3, lane: [number,number,number], size: number }
//   speed: 0.6〜2.0（基準1.0＝1.0セル/秒）
//   hp:    0.6〜3.0（倍率。実HP = (20 + wave*8) * hp * size）
//   resist: 0=なし 1=heat 2=cold 3=bolt（該当属性からの被ダメ50%）
//   lane:  正規化済み重み。個体はこの重みで出現レーンを1つ抽選
//   size:  0.7〜1.5（実速度 = speed / sqrt(size)。表示半径に比例）
```
- 見た目直結: `speed`→楕円の縦横比（速いほど進行方向に細長い）、`hp`→輪郭線の太さ（1〜5px）、`resist`→塗り色（none=#9a9a9a／heat=#e05a3a／cold=#4aa8e0／bolt=#e6c94a）、`size`→半径（8〜17px）
- 個体数 `20 + wave*2`（上限50）。個体は0.4秒間隔で順次出現

### 進化（`evolution.js`、純粋関数・DOM非依存・乱数は注入）
```js
// export function initialPopulation(n, rng): genome[]  — 全遺伝子を基準値±10%でジッター、resistは全て0、laneは均等
// export function evaluate(results): number[]
//   results[i] = { progress: 0..1(到達距離割合), reachedBase: boolean, damageDealtToBase: number }
//   fitness = progress + (reachedBase ? 1.0 : 0) + damageDealtToBase*0.25
// export function evolve(population, fitness, ctx, rng): genome[]
//   ctx = { wave, towerDiversity: 0..1 (配置中の塔種類数/4), nextSize }
//   1. fitness上位30%を親プールに（最低4体）
//   2. 子は親2体からの遺伝子ごとの一様交叉
//   3. 突然変異: 遺伝子ごとに確率 p = 0.08 * (1 + (1 - towerDiversity))  ← 単一戦術への罰
//        speed/hp/size: 正規乱数(σ=0.15)を乗算的に加え、範囲でクランプ
//        resist: p の確率で 0〜3 から再抽選
//        lane: 各要素に ±0.15 の一様ノイズ、負値は0、再正規化
//   4. 多様性保険: 子集団の10%は initialPopulation の個体で置き換える（局所解の固着と理不尽化を防ぐ）
// export function summarize(population): { speedMean, hpMean, sizeMean, resistShare: [4], laneShare: [3] }
// export function diffReport(prevSummary, nextSummary): string[]
//   変化量の大きい順に最大3行の日本語文。例:
//   「群れは高速化した（+12%）」「抗体への耐性を持つ個体が増えた（15%→40%）」「中央レーンを好むようになった（33%→52%）」「体格が大きくなった（+9%）」
//   |変化| が閾値未満（速度・体力・体格 ±4%未満、割合 ±8pt未満）の項目は出さない。全て閾値未満なら「群れに目立った変化はない」1行
```

### ウェーブ進行
- ウェーブは自動開始しない。配置フェーズに「ウェーブ開始」ボタン。ゲーム速度 ×1 / ×2 切替
- ウェーブ終了（全個体の撃破または到達）→ `evolve` → **変異レポートをモーダルで表示**（閉じるまで次に進まない。読ませることが目的）→ 配置フェーズ
- **ウェーブ15をクリアでリザルト（クリア）**、その後「エンドレスで続ける」を選べる。ライフ0でリザルト（ゲームオーバー）。スコア＝到達ウェーブ数（エンドレス中も加算）

### チャレンジリンク（`share.js`）
- `location.hash = "#c=" + base64url(JSON.stringify({ v: 1, seed: <uint32>, gold: <int> }))`
- タイトル画面: ハッシュがあれば「挑戦状が届いています（seed表示）」→「この条件で始める」。なければ通常開始（seedはランダム生成）
- リザルト画面: 「この条件で挑戦状を送る」＝現在のseed/goldでURLを生成しクリップボードへ。表示テキストに到達ウェーブ数を含めた定型文（例:「群変 seed:XXXX で 12 ウェーブ耐えた。あなたは？ <URL>」）
- seedは `rng.js`（mulberry32）に渡し、初期集団・突然変異・出現レーン抽選に使う。塔の挙動は決定的（乱数不使用）
- 受け手側は `storage.js` に `challengeReceived: true` を記録し、アンケートJSONに含める（届け方の効果測定）

### 画面遷移
title → playing（配置／ウェーブ／変異レポートmodal の内部状態）→ result（clear | gameover）→ (survey) → title

### アンケート（巡室から流用、設問2のみ差し替え）
1. また遊びたいか 1-5 ／ 2. **群れが自分の守り方に合わせてきたと感じたか 1-5** ／ 3. 難易度 1-5 ／ 4. 良かった瞬間（自由記述）／ 5. イライラした瞬間（自由記述）
- 任意・毎回選べる。「結果をコピー」でJSON（全件＋bestWave＋challengeReceived）をクリップボードへ

### アセット方針
外部画像・音声非使用。図形描画のみ。効果音は巡室の Web Audio 合成（`audio.js`）の方式を踏襲し、配置音・撃破音・到達被害音・ウェーブ開始音の4種のみ（BGMなし。任意でミュート）

### ディレクトリ構成
```
game-prototype/evolve-td/
├── index.html
├── style.css
├── js/
│   ├── main.js        # 画面遷移・ゲームループ・入力（配置/売却/ボタン）
│   ├── config.js      # 塔・経済・遺伝子範囲・進化パラメータの全定数
│   ├── rng.js         # mulberry32、seed→乱数関数
│   ├── game-state.js  # 資金・ライフ・ウェーブ・塔配置の状態と純粋な更新関数
│   ├── towers.js      # 塔の定義参照・索敵・攻撃・弾/効果
│   ├── enemies.js     # genome→個体生成、レーン移動、被ダメ、results生成
│   ├── evolution.js   # 進化（純粋関数）とレポート
│   ├── renderer.js    # Canvas描画（盤面・塔・個体の見た目直結・弾）
│   ├── audio.js       # Web Audio合成SE 4種
│   ├── share.js       # チャレンジリンクの符号化/復号
│   ├── storage.js     # bestWave / survey / challengeReceived
│   ├── survey.js      # アンケートUI・JSON出力
│   └── test.mjs       # evolution / game-state / share の単体テスト（Node実行、DOM非依存）
└── README.md
```

### データ構造・インターフェース（確定仕様）
```js
// game-state.js
// GameState: { seed, gold, lives, wave, phase: 'place'|'wave'|'report', towers: [{id, col, row}], population: genome[], lastSummary, bestWave }
// export function startNewGame({ seed, gold }): GameState
// export function canPlace(state, towerId, col, row): boolean   // レーン上・重複・資金不足で false
// export function placeTower(state, towerId, col, row): GameState
// export function sellTower(state, col, row): GameState
// export function startWave(state): GameState                   // phase→'wave'、population を個体化するのは enemies.js
// export function endWave(state, results, rng): { state: GameState, report: string[] }  // evolve+summarize+diffReport、phase→'report'
// export function isCleared(state): boolean  // wave===15 到達時
// export function isGameOver(state): boolean

// enemies.js
// export function spawnFromPopulation(population, wave, rng): Enemy[]  // Enemy: { genome, lane, x(セル単位), hp, maxHp, slowUntil, alive, reached }
// export function stepEnemies(enemies, dt, laneLength): void
// export function collectResults(enemies, laneLength): results[]      // evolution.evaluate の入力

// towers.js
// export function stepTowers(towerInstances, enemies, dt): Projectile[]/効果適用（実装者裁量: 弾を即着弾扱いにしてよいが、描画用に0.1秒の軌跡を残す）

// share.js
// export function encodeChallenge({ seed, gold }): string  // "#c=..." を除いた base64url 部分
// export function decodeChallenge(hashOrPayload): { seed, gold } | null  // 不正・範囲外は null
```

## タスク粒度についてのミニADR
巡室と同じ判断: ゲーム本体（index.html + style.css + js/*.js 一式）は**1タスク・1エージェント**に集約実装し、`evolution.js`/`game-state.js`/`share.js` は純粋関数として `test.mjs` で先にテストを書かせる。デプロイ設定（`deploy-pages.yml` に `/evolve-td/` を追加、README）は本体完了後の別タスク。理由（密結合コンポーネントの並列生成による統合バグ回避）は巡室設計文書のミニADRを参照。

## 想定される曖昧点への先回り回答
1. **弾の実装**: 即着弾（ヒットスキャン）でよい。描画のみ軌跡線を0.1秒残す。範囲ダメージ（heat）は着弾対象の位置を中心に判定
2. **同一セルへの重ね置き**: 不可。売却してから置く
3. **ウェーブ中の売買**: 許可。ただし配置フェーズ推奨のUI文言にする（「ウェーブ中でも配置できます」）
4. **エンドレス時の個体数・HP**: 同じ式を継続（上限50体）。wave が増えるほど `hp` 基準値が伸びるので事実上いつか負ける
5. **towerDiversity の算出**: 盤面に存在する塔の**種類数**/4（本数ではない）。塔0本なら 0
6. **レポート閾値**: 上記 diffReport の閾値に従う。全ての変化が閾値未満なら1行の定型文
7. **速度×2**: dtを2倍にするだけ（物理・索敵は同じ関数）。レポート表示中は停止
8. **モバイル**: 塔選択→セルタップで配置。選択中の塔の射程円を表示。売却は配置済みセルをタップ→「売る」ボタン
9. **チャレンジ受領時のseedの扱い**: 「この条件で始める」を選ばず通常開始した場合はハッシュを消してランダムseedにする
10. **bestWave**: seedごとではなく全体の自己ベストのみ保存（シンプル優先）

## DoD（完了定義）
- [ ] index.htmlをブラウザで直接開く（file://）かローカルサーバーで動作確認できる
- [ ] title→playing（配置/ウェーブ/レポート）→result→(survey)→title が一通り動作する
- [ ] 塔4種・3レーン・15ウェーブ・エンドレスが動作し、`config.js` の数値で全バランスが変えられる
- [ ] 進化（評価→選抜→交叉→突然変異→多様性保険）が `evolution.js` の純粋関数として実装され、`test.mjs` で ①上位個体の形質が次世代に寄ること ②突然変異率が towerDiversity に依存すること ③範囲クランプ、が検証されている
- [ ] 遺伝子が見た目（縦横比・輪郭・色・半径）に反映されている
- [ ] 変異レポートがウェーブ終了ごとにモーダルで表示され、閾値未満の項目が省かれる
- [ ] チャレンジリンクの生成・復号・不正値の拒否が動作し、`test.mjs` で往復テストがある
- [ ] localStorage に bestWave / アンケート / challengeReceived が保存され、JSONコピーができる
- [ ] Web Audio SE 4種＋ミュート
- [ ] モバイル（タッチ操作・レスポンシブ）で配置・売却・ウェーブ開始ができる
- [ ] READMEに遊び方・ローカル起動手順・チャレンジリンクの仕組みが書かれている
- [ ] （別タスク）`deploy-pages.yml` に `/evolve-td/` の合成が追加され、Pagesで遊べる

## プロトタイプ内の成功判定（オーナー実プレイ）
- 1ランのうちに「群れが自分に合わせてきた」と感じる瞬間が1回以上あるか
- レポートを読んで配置を変えたか（変えたくなる情報だったか）
- 「もう1回」を自発的に押したか（2周目到達）

## 14日の工程（目安）
- D1-3: 通常のTDとして遊べる状態（盤面・塔・敵・経済・15ウェーブ）
- D4-7: 進化・見た目直結・変異レポート・test.mjs
- D8-10: チャレンジリンク・アンケート・storage・SE
- D11-14: バランス調整（オーナー実プレイ2回）・Pages配備・README
