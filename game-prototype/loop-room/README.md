# 巡室（じゅんしつ）

同じ「部屋」を繰り返し観察し、周回のたびに部屋の異変の有無を見抜くホラー探索ブラウザゲーム。

Vanilla JS + HTML5 Canvasのみで動作し、ビルドステップは不要。

## 遊び方

1. タイトル画面の「はじめる」で開始する。
2. 表示された部屋をよく観察する（制限時間はなく、いつでも操作可能）。
3. 部屋に何か「異変」があると感じたら「戻る」を、何も無いと感じたら「進む」を選ぶ。
4. 判定ルール:
   - 異変あり + 「戻る」を選んだ → 正解、次の周回へ進む
   - 異変あり + 「進む」を選んだ → 誤答、ゲームオーバー
   - 異変なし + 「進む」を選んだ → 正解、次の周回へ進む
   - 異変なし + 「戻る」を選んだ → 誤答（空振り）、ゲームオーバー
5. どちらの誤り方でも即ゲームオーバーになる。到達した周回数が記録される。
6. 周回を重ねるほど、異変の「視認しやすさ」（変化の大きさ）が徐々に薄れていく。ただし異変が発生する確率自体は常に50%で変わらない。
7. ゲームオーバー後、「もう一度」で再挑戦するか、「感想を送る」からアンケートに回答できる。

## ローカルでの起動手順

ビルド不要。以下のいずれかの方法で `index.html` を開く。

### 方法A: index.htmlを直接ブラウザで開く

`loop-room/index.html` をダブルクリックするか、ブラウザにドラッグ&ドロップする。

### 方法B: ローカルサーバーで配信する（推奨）

```sh
cd game-prototype/loop-room
python3 -m http.server 8000
```

ブラウザで `http://localhost:8000/` を開く。

（ES Modulesを`file://`から直接読み込む際、一部のブラウザ/環境で制約が出ることがあるため、ローカルサーバー経由を推奨）

## テストの実行方法

Node.js単体で実行できるロジックテストを用意している（DOM描画やUI部分は対象外）。

```sh
cd game-prototype/loop-room
node js/test.mjs
```

全項目PASSであれば `ALL TESTS PASSED` が出力される。

## ディレクトリ構成

```
loop-room/
├── index.html          画面構造（title/playing/gameover/survey の4画面）
├── style.css            スタイル・演出（暗転フェード、ゲームオーバー時の赤フラッシュ等）
├── js/
│   ├── main.js           画面遷移制御・イベントリスナー登録
│   ├── room-renderer.js  baseレイアウト生成・Canvas 2D描画
│   ├── variants.js       異変パターン（20種）・難易度カーブ計算
│   ├── game-state.js     周回進行・正誤判定ロジック
│   ├── survey.js         アンケートUI・回答収集
│   ├── storage.js        localStorage永続化（自己ベスト・アンケート回答）
│   └── test.mjs          ロジック単体テスト
└── README.md
```

## GitHub Pagesでの公開

`research/game-department-prototype` ブランチの `game-prototype/loop-room/**` に変更をpushすると、`.github/workflows/deploy-loop-room.yml` のワークフローが自動的にビルドなしでこのディレクトリをGitHub Pagesにデプロイする（`workflow_dispatch`による手動実行も可能）。

公開後のURLは、リポジトリの `Settings > Pages` 画面、またはワークフロー実行結果の `deploy` ジョブの出力（`page_url`）で確認できる。

**初回設定として、リポジトリの `Settings > Pages` で Source を「GitHub Actions」に設定する必要がある。これはコードでは自動化できない、人間が一度だけ行う手動設定。**
