# タスク: 2つのブランチの成果物を合成して GitHub Pages に公開する

このリポジトリの成果物は2か所に分かれている。

- `main` ブランチ: ダッシュボード
  - `dashboard/app/index.html` … 実データ版
  - `dashboard/prototype/stonefish-dashboard.html` … シミュレーションのデモ版
- `research/game-department-prototype` ブランチ: ゲーム「巡室」一式
  - `game-prototype/loop-room/` 配下（`index.html` などをそのまま公開する）

GitHub Pages は**サイト全体を丸ごと置き換える**ため、片方だけを公開すると
もう片方が消えてしまう。両方を合成した1つのサイトを公開する仕組みを
`.github/workflows/deploy-pages.yml` として作ってほしい。

## 公開後のサイト構成

| URL | 中身 |
|---|---|
| `/` | ゲーム「巡室」（`game-prototype/loop-room/` の内容をそのまま） |
| `/dashboard/` | ダッシュボード実データ版（`dashboard/app/index.html`） |
| `/dashboard/demo.html` | デモ版（`dashboard/prototype/stonefish-dashboard.html`） |

## 仕様

- **どちらのブランチへの push でも**、サイト全体を作り直して公開する。
  トリガー元がどちらであっても、常に両方のブランチの内容を取得して合成する。
- 公開するファイル一式は `_site` ディレクトリに組み立て、それを Pages の
  アーティファクトとしてアップロードする。
- Pages へのデプロイに必要な権限を workflow に与える（Pages への書き込みと
  OIDC トークンの発行）。
- デプロイが同時に走って競合しないよう、実行をまとめる設定を入れる。
- `/dashboard/` を https で開いた訪問者（＝ローカルサーバを持たない人）が
  デモ版へ移動できるよう、実データ版のページから `demo.html` への導線を用意する。

## 受け入れ基準

- workflow のビルド手順を実行すると、上の表のとおりのファイル配置が `_site` の下に
  できあがる（ゲームがルート、ダッシュボードが `dashboard/` の下）。
- 2つのブランチをそれぞれ別の場所に取得しており、取得先が衝突していない。
- push トリガーの対象ブランチに両方が入っている。
- 権限・同時実行制御・アップロード対象のパスが上の仕様どおりになっている。
