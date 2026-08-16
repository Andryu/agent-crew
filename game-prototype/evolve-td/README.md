# 群変（ぐんぺん）

敵の群れがウェーブごとにプレイヤーの防衛配置に対して進化するタワーディフェンス。「群れが自分に合わせてきた」と知覚できることを最重要の検証点とするブラウザゲームプロトタイプ。

Vanilla JS + HTML5 Canvasのみで動作し、ビルドステップは不要。

## 遊び方

1. タイトル画面の「はじめる」で開始する（挑戦状リンクを踏んで開いた場合は「この条件で始める」/「通常ではじめる」を選ぶ）。
2. 配置フェーズで塔（免疫細胞）を盤面に置き、「ウェーブ開始」で病原体の群れを迎え撃つ。
3. 全個体を撃破するか、全個体が右端の臓器に到達するとウェーブ終了。群れは評価→選抜→交叉→突然変異で次のウェーブへ進化し、「変異レポート」でどう変わったかが読める。
4. 塔はウェーブ1（好中球）・3（マクロファージ）・5（インターフェロン）・7（抗体）で段階的に解禁される。ウェーブ3から能動スキル「発熱」（レーンを選んで一時的に減速させる）が使える。
5. ウェーブ15をクリアすると「防衛完了」。ライフが0になると「あなたを倒した群れ」としてゲームオーバー。到達ウェーブ数がスコア（自己ベストはlocalStorageに保存）。
6. 結果画面から「この条件で挑戦状を送る」で同じseed/初期資金のURLをコピーでき、そのURLを開いた相手は同じ条件で群れの進化を再現できる（決定的乱数）。
7. 結果画面から「アンケートに答える」で任意のフィードバックを送れる（回答は端末内のlocalStorageに溜まり、「結果をコピー」でJSONとして取り出せる）。

## ローカルでの起動手順

ES Modulesを使用しているため、`file://` の直接オープンでは動作しない環境がある。ローカルサーバー経由を推奨する。

```sh
cd game-prototype/evolve-td
python3 -m http.server 8000
```

ブラウザで `http://localhost:8000/` を開く。

## テストの実行方法

Node.js単体で実行できるロジックテストを用意している（`renderer.js`/`main.js`/`audio.js`/`survey.js`はDOM依存のため構文チェックのみ、それ以外は純粋関数として動作を検証する）。

```sh
cd game-prototype/evolve-td
node js/test.mjs
```

末尾に `ok (N tests)` が出力されれば全項目PASS。

## チャレンジリンクの仕組み

- `share.js` が `{ v: 1, seed, gold }` をJSON化しbase64url符号化した文字列を `location.hash` に `#c=...` の形で埋め込む。
- タイトル画面はページ読み込み時にハッシュを検出し、有効な挑戦状なら「挑戦状が届いています（seed: XXXX）」バナーを表示する。
- `decodeChallenge` はバージョン不一致・seedの非整数/範囲外（uint32範囲外）・goldの範囲外（150〜600）・パース不能ないずれかでnullを返し、不正なリンクは黙って通常開始扱いになる。
- 受領して「この条件で始める」を選んだ場合は `storage.js` に `challengeReceived: true` を記録する（届け方の効果測定に使う）。
- 塔の挙動・進化の乱数はすべて`seed`から生成される決定的乱数（`rng.js`のmulberry32）のみに依存するため、同じseed/goldなら同じ展開が再現される。

## アンケート回収手順

1. プレイヤーに結果画面から「アンケートに答える」→回答後の「結果をコピー」を押してもらい、出力されたJSON文字列を送ってもらう（1人が複数回プレイしていれば、その分の回答が `responses` 配列にまとまって入っている）。
2. JSONの形は `{ responses: [...], bestWave: number, challengeReceived: boolean, sessions: number, wave2Started: number }`。`sessions`/`wave2Started` は離脱計測点「ウェーブ2開始率」の分子・分母（`wave2Started / sessions`）に使う。
3. `responses` の各要素は `{ wantToPlayAgain(1-5), adaptationFelt(1-5, 群れが守り方に合わせてきたと感じたか), difficultyLevel(1-5), goodMoment, badMoment, reachedWave, timestamp }`。

## ディレクトリ構成

```
game-prototype/evolve-td/
├── index.html          画面構造（title/playing/result/survey の4画面＋変異レポートmodal）
├── style.css            スタイル・演出
├── js/
│   ├── main.js           画面遷移制御・ゲームループ・入力・演出の統括
│   ├── config.js         塔・経済・遺伝子範囲・進化パラメータ・色/形状の全定数
│   ├── rng.js             mulberry32によるシード付き擬似乱数
│   ├── game-state.js     資金・ライフ・ウェーブ・塔配置の状態と純粋な更新関数
│   ├── towers.js          塔の索敵・攻撃
│   ├── enemies.js         genome→個体生成・移動・被ダメ・results生成
│   ├── evolution.js       進化（評価→選抜→交叉→突然変異→多様性保険）とレポート生成
│   ├── renderer.js        Canvas描画（盤面・塔・個体・粒子・数字ポップ）
│   ├── audio.js           Web Audio合成SE 4種（配置・撃破・到達被害・ウェーブ開始）
│   ├── share.js           チャレンジリンクの符号化/復号
│   ├── storage.js         bestWave / survey / challengeReceived / seenIntro / sessions / wave2Started
│   ├── survey.js          アンケートUI・JSON出力
│   └── test.mjs           Node実行のロジック単体テスト
└── README.md
```

## 開発メモ

- 詳細な設計仕様は `docs/design/game-td-evolve-design.md`、UI/UX仕様は `docs/ux/game-td-ux.md`、実装工程は `docs/plans/2026-08-16-evolve-td-v1.md` を参照。
- モジュールごとの責務・公開関数のシグネチャは `docs/plans/evolve-td-module-map.md` にまとめている。
- Pages配備（`deploy-pages.yml`）とバランス調整はオーナー実プレイ後の別タスクで行う（本README作成時点では未対応）。
