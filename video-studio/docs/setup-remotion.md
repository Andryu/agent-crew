# Remotion セットアップ・「落書きショート」テンプレート仕様

手書き落書き風ショート動画を `episode.json` 駆動で自動組み立てするための Remotion プロジェクト。

## 前提

- Node.js（動作確認: v25.9.0 / npm 11.12.1）
- `video-studio/remotion/` が Remotion プロジェクト本体（`npx create-video@latest --yes --blank` で作成、Tailwindは未使用のため削除済み）

```bash
cd video-studio/remotion
npm install
```

## ディレクトリ構成

```
video-studio/
  .gitignore              # node_modules・レンダリング出力・個人素材(assets/音声)を除外
  remotion/                # Remotionプロジェクト本体
    remotion.config.ts     # publicDir を ../episodes に向ける設定（重要・後述）
    src/
      Root.tsx              # "doodle-short" コンポジションを登録
      compositions/DoodleShort/
        DoodleShort.tsx     # メインコンポーネント + calculateMetadata
        Cut.tsx              # 1カット分の描画（画像・カメラ演出・字幕・音声）
        Caption.tsx          # 画面下部1/3の字幕
        PlaceholderCut.tsx   # 素材未着カット用の単色+テキスト
        cameraEffect.ts      # zoom-in/zoom-out/pan/shake の transform計算
        loadEpisode.ts       # episode.json のfetch/検証
        types.ts             # episode.json のスキーマ型定義
  episodes/
    ep01/
      episode.json          # このエピソードの台本データ（cuts配列）
      assets/                # キャラ画像・SE・ナレーションwav（gitignore対象・個人素材）
      out/                   # レンダリング出力（gitignore対象）
  scripts/
    render.sh               # episode.jsonを読んでレンダリングするラッパー
```

### なぜ `publicDir` を `episodes/` に向けているか

Remotion の `staticFile()` はプロジェクトの public dir 配下のファイルしか参照できない。
`episode.json` や画像・音声は Remotion プロジェクトの外（`video-studio/episodes/<episodeId>/`）に置きたいため、
`remotion.config.ts` で

```ts
Config.setPublicDir(path.join(process.cwd(), "..", "episodes"));
```

としている。これにより `staticFile("ep01/episode.json")` や `staticFile("ep01/assets/kanojo_face.png")` で
`video-studio/episodes/ep01/...` を参照できる。

**注意:** `process.cwd()` 基準なので、Remotion CLI は必ず `video-studio/remotion` をカレントディレクトリとして実行すること
（`scripts/render.sh` はこれを自動で行う）。CJSバンドルの制約上 `import.meta.url` は使えないため `process.cwd()` を使っている。

## `episode.json` スキーマ

```jsonc
{
  "id": "ep01",                 // エピソードID（ディレクトリ名と一致させる）
  "title": "エピソードタイトル",
  "fps": 30,                     // 省略時 30
  "width": 1080,                 // 省略時 1080
  "height": 1920,                // 省略時 1920（9:16）
  "audio": {
    "bgm": "assets/bgm.mp3",     // 省略/null可。episode.jsonからの相対パス
    "bgmVolume": 0.35            // 省略時 0.4
  },
  "cuts": [
    {
      "index": 1,                          // カット番号（絵コンテと対応）
      "durationSec": 3,                     // このカットの表示秒数
      "images": ["assets/a.png", "assets/b.png"],
      // 画像0枚 = placeholder使用 / 1枚 = 静止 / 2枚 = toggleFpsの速さで交互表示（目パチ・口パク風、補間なし）
      "toggleFps": 6,                       // 省略時 6。2枚指定時のみ有効
      "placeholder": {                      // imagesが空の時に使う単色+テキスト
        "color": "#FCEFE0",
        "text": "説明テキスト（任意）"
      },
      "caption": "画面下部1/3に出す字幕",     // 省略可（字幕なしカット）
      "narrationText": "台本の該当行（参考用・音声には使わない）",
      "narration": "assets/narration/cut01.wav", // 未生成なら null
      "se": "assets/se/hyuu.wav",                // 未生成/無音なら null
      "camera": "zoom-in",                   // "zoom-in" | "zoom-out" | "pan" | "shake" | "none"
      "note": "制作メモ（画面には出ない）"
    }
  ]
}
```

- 動画の総尺は `cuts` の `durationSec` 合計から自動計算される（`calculateMetadata` で算出）。
- `narration` / `se` は wav が用意できるまで `null` にしておき、ファイル名や台本行は `note` / `narrationText` に書いておく運用。
  JSON はコメントを書けないため、この2フィールドが実質的な「コメントアウト」の代わりになる。
- `images` が2枚のときの切り替えは `Math.floor(frame / round(fps/toggleFps)) % 2` によるステップ切り替えで、
  滑らかな補間は行わない（手書きアニメらしいカクカク感を優先）。
- カメラ演出（`zoom-in` / `zoom-out` / `pan`）はCapCut風に滑らかな `interpolate`、
  `shake` のみ6パターンのジッターをフレーム単位で切り替える（こちらも補間なし）。

## レンダリング

```bash
# ラッパー経由（推奨）
video-studio/scripts/render.sh ep01
# -> video-studio/episodes/ep01/out/ep01.mp4

# 出力ファイル名を指定
video-studio/scripts/render.sh ep01 /path/to/output.mp4

# Remotion CLIを直接使う場合（video-studio/remotion がカレントディレクトリであること）
cd video-studio/remotion
npx remotion render doodle-short ../episodes/ep01/out/ep01.mp4 --props='{"episodeId":"ep01"}'
```

プレビュー（Remotion Studio）:

```bash
cd video-studio/remotion
npm run dev
```

## 動作確認済み

- `video-studio/scripts/render.sh ep01` で `video-studio/episodes/ep01/out/ep01.mp4` を書き出し。
- `ffprobe` で 1080x1920・30fps・h264/aac・尺 約48秒 を確認済み。

## 残課題 / 今後の差し替え予定

- ep01 の cut1（歩行）・cut6（彼のjump反応）・cut7（wave）は Animated Drawings 側のモーション成果物が揃い次第、
  `images` を差し替える（現状はプレースホルダー or 静止画）。
- SE（`assets/se_hyuu.wav` 相当・`se_tokei.wav`・`se_gaan.wav`）とナレーションwavは VOICEVOX 側の成果物が揃い次第、
  各カットの `se` / `narration` に実パスを設定する。
- cut2（街並み背景）・cut3（VR）・cut6（女子グループ）・cut9（2人並び＋チャンネル名）の背景/構図イラストが未着手。
  AI生成 or 手描きで用意でき次第、`images` または `placeholder` を差し替える。
- 現在の `Cut` コンポーネントは画像レイヤーを1枚しか重ねられない（背景+キャラの合成は未対応）。
  複数レイヤー合成が必要になった場合は `Cut.tsx` の拡張が必要。
