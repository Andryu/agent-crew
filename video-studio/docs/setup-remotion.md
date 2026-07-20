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
        Cut.tsx              # 1カット分の描画（背景+前景・画像/動画・カメラ演出・ゆらぎ・字幕・セリフ音声・口パク）
        Caption.tsx          # 画面下部1/3の字幕
        DialogueCaption.tsx   # v2: セリフ再生ウィンドウ中だけ表示する話者色分け字幕
        Credit.tsx            # 画面右下の小さなクレジット表記（VOICEVOX等）
        PlaceholderCut.tsx   # 素材未着カット用の紙テクスチャ+テキスト
        cameraEffect.ts      # zoom-in/zoom-out/pan/shake の transform計算
        idleSway.ts           # v2: 常時ゆらゆら（手書き風の揺れ）の transform計算
        paperTexture.ts       # v2: 単色の代わりに使う紙風テクスチャ（CSS radial-gradient）
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

## `episode.json` スキーマ（v2）

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
      "background": "assets/gen/bg_street.png", // 省略可。全画面フルブリードで最背面に描画する背景1枚
      "images": ["assets/a.png", "assets/b.png"],
      // 画像0枚 = placeholder使用 / 1枚 = 静止 / 2枚 = toggleFpsの速さで交互表示（目パチ・口パク風、補間なし）
      // 拡張子が .mp4 / .webm の場合は OffthreadVideo で動画として埋め込み表示（Animated Drawings のモーションクリップ用）
      "toggleFps": 6,                       // 省略時 6。images静止画2枚指定時のみ有効
      "videoLoopSec": 1.2,                   // images が動画のときのループ単位秒。省略時はループせず1回再生
      "placeholder": {                      // imagesが空の時に使う紙テクスチャ+テキスト
        "color": "#FCEFE0",
        "text": "説明テキスト（任意）"
      },
      "caption": "画面下部1/3に出す字幕",     // 省略可（字幕なしカット）
      "narrationText": "台本の該当行（参考用・音声には使わない）",
      "narration": "assets/narration/cut01.wav", // [非推奨・後方互換] 単一ナレーションのみの場合。未生成なら null
      "dialogue": [                          // v2: セリフ劇（複数話者・startSecでシーケンス配置）
        {
          "speaker": "kanojo",                // "kanojo" | "kareshi" | "mob"
          "wav": "assets/voice/cut01_kanojo.wav",
          "startSec": 0,                       // カット先頭からの再生開始秒
          "durationSec": 1.8,                  // wavの実測秒数（口パクウィンドウ・尺検証に使う）
          "mouthLayer": {                      // 省略可。指定時だけ口パク表示
            "mouthClosed": "assets/kanojo_mouth_closed.png",
            "mouthOpen": "assets/kanojo_mouth_open.png",
            "toggleFps": 8                     // 省略時 8
          },
          "text": "初ハウステンボス来たー！"      // 省略可。再生ウィンドウ中だけ表示するセリフ字幕
        },
        {
          "speaker": "kareshi",
          "wav": "assets/voice/cut01_kareshi.wav",
          "startSec": 1.9,
          "durationSec": 1.5,
          "text": "おー、なんかヨーロッパじゃん"
          // mouthLayer省略時は通常の images 表示のまま（口開き素材が無い間の後方互換動作）
        }
      ],
      "se": "assets/se/hyuu.wav",                // 未生成/無音なら null
      "camera": "zoom-in",                   // "zoom-in" | "zoom-out" | "pan" | "shake" | "none"
      "credit": "VOICEVOX:波音リツ",          // 省略可。画面右下に小さく常時表示するクレジット
      "note": "制作メモ（画面には出ない）"
    }
  ]
}
```

- 動画の総尺は `cuts` の `durationSec` 合計から自動計算される（`calculateMetadata` で算出）。
- `narration` / `dialogue[].wav` / `se` は wav が用意できるまで省略 or `null` にしておき、ファイル名や台本行は
  `note` / `narrationText` に書いておく運用。JSON はコメントを書けないため、この2フィールドが実質的な「コメントアウト」の代わりになる。
- ナレーション/セリフの音量は常に 1.0（`Audio` コンポーネントに明示指定）。BGMは `audio.bgmVolume`（省略時0.4）で別途調整する。
- `images` が静止画2枚のときの切り替えは `Math.floor(frame / round(fps/toggleFps)) % 2` によるステップ切り替えで、
  滑らかな補間は行わない（手書きアニメらしいカクカク感を優先）。
- カメラ演出（`zoom-in` / `zoom-out` / `pan`）はCapCut風に滑らかな `interpolate`、
  `shake` のみ6パターンのジッターをフレーム単位で切り替える（こちらも補間なし）。
- `credit` は VOICEVOX 等の規約上必須なクレジット表記用。`placeholder` や `images` を後で差し替えても消えない独立レイヤー
  （`Credit.tsx`、画面右下）として描画されるので、規約対応のクレジットはここに入れる。

### v2で追加された機能

**1. 常時ゆらゆら（`idleSway.ts`）**
すべての画像/動画/プレースホルダーレイヤーに、上下±1〜2%の平行移動＋微小回転（±1.5度程度）を標準装備。
カメラ演出（`cameraEffect.ts`）とは別レイヤーで重ねがけしており、`camera: "none"` でも常にこの揺れが入る。
6fps相当のステップ切り替え（`Math.floor(frame / framesPerStep)` で固定8パターンテーブルから選択）で、滑らかな補間はしない。
オフにするフラグは無い（「標準装備」という設計判断のため）。カット番号を揺れの位相シードに使っており、隣接カット間で揺れ方をずらしている。

**2. セリフ劇対応（`dialogue` 配列）**
`narration`（単一・非推奨だが後方互換で継続サポート）に加え、`dialogue` 配列で複数話者のセリフを
`startSec` 基準でカット内にシーケンス配置できる。話者は `"kanojo" | "kareshi" | "mob"` の3種。
実装は各 `dialogue` 項目を `<Sequence from={startSec*fps} durationInFrames={durationSec*fps}><Audio .../></Sequence>` として
Cutの中にネストしているだけなので、`narration` と `dialogue` は同一カットで併用可能（通常はどちらか一方を使う想定）。

**3. 口パク（`mouthLayer`）**
`dialogue` の各項目に `mouthLayer: { mouthClosed, mouthOpen, toggleFps? }` を指定すると、
そのセリフの再生ウィンドウ（`startSec` 〜 `startSec + durationSec`）内だけ、通常の `images` 表示を無視して
`mouthClosed` / `mouthOpen` を約8fps（デフォルト）でステップトグルする。補間はしない。
`mouthLayer` を指定しなければ通常の `images` ロジックにフォールバックするので、口開き素材が無いカットでも壊れない。

**4. 動画埋め込み（OffthreadVideo + Loop）**
`images` に `.mp4` / `.webm` を指定すると、静止画の代わりに `OffthreadVideo`（muted）で埋め込み表示する
（Animated Drawings 等のモーションクリップ用。白背景推奨）。
`videoLoopSec` を指定すると Remotion の `Loop` コンポーネントでその秒数を1周としてループ再生する
（例: 1.2秒の歩行モーションクリップを6秒のカットいっぱいにループ）。未指定なら1回再生のみ（ループしない）。

**5. 紙テクスチャ背景（`paperTexture.ts`）**
Cutの背景およびPlaceholderCutの単色塗りを、うっすら斑点の乗った紙風テクスチャに置き換えた。
**実装メモ（ハマりどころ）:** 当初SVGの `feTurbulence` フィルターを `background-image` のdata URIとして使う実装だったが、
Remotionのヘッドレスフレーム書き出し（`still`/`render` 両方、PNG/JPEG問わず）では**このフィルターが一切反映されない**ことを
ピクセル値の分散が完全に0であることで実測確認した（Chrome headless shell 側のSVGフィルター処理の制約とみられる）。
そのため、フィルタープリミティブに依存しない複数の `radial-gradient`（タイルサイズを互いに素に近い値でずらして重ねる）方式に
差し替えて解決した。**今後このテンプレートに新しいテクスチャ/エフェクトを追加する際は、SVGフィルターに頼らずCSSグラデーション/
transform等のネイティブCSSプロパティで実装し、`still`コマンドでPNG書き出し→ピクセル分散をチェックする形で検証すること。**

**6. セリフ字幕（`DialogueCaption.tsx`）**
`dialogue[].text` を指定すると、そのセリフの再生ウィンドウ中だけ話者ごとに縁色を変えた字幕（吹き出しではなく丸みのあるバッジ+色ドット）を表示する。
`cut.caption`（画面下部1/3、タイトル・演出テロップ用）とは別レイヤーで、その少し上（画面55%あたりから下向き）に重ねているため、
両方を同時に使うカット（タイトル+セリフ、演出テロップ+セリフ等）でも通常は重ならない。同時刻に複数話者のセリフが再生中の場合
（例: 2人同時に「うわあああ！」）は縦に積み上げて両方表示する。話者色: kanojo=ピンク、kareshi=青、mob=緑。

**7. 背景レイヤー（`cut.background`）**
`cut.background` に画像1枚を指定すると、全画面フルブリードで最背面に描画される。既存の `images`/`placeholder` はその上に
今まで通り重ねて描画されるが、背景がある場合は前景側に `mix-blend-mode: multiply` を適用する。
本テンプレートの素材は全て「白背景の線画」（PNG、アルファチャンネル無し）という前提があるため、multiplyブレンドにより
白同士は透過的に振る舞い、線画（インク部分）だけが両方とも残る＝マスクや切り出し無しで自然に重なる。
背景・前景で `idleSway` の位相をずらしており（背景は `cut.index + 100` をシードに使用）、2枚の紙が別々に揺れているように見える。
カメラ演出（zoom/pan/shake）は背景・前景を含むシーン全体にかかる（背景だけ/前景だけに別々のカメラ効果は掛けられない設計）。

> 前景画像（例: キャラクターの全身/顔）は元々オブジェクトフィットcoverで画面いっぱいに表示される設計だったため、
> 背景を追加しても前景の表示位置・サイズは変えていない（"今まで通り"）。透明化はCSSのブレンドモードのみで実現しており、
> マスクや複数解像度合わせ等の凝った処理はしていない。

## レンダリング

```bash
# ラッパー経由（推奨）
video-studio/scripts/render.sh ep01
# -> video-studio/episodes/ep01/out/ep01.mp4

# 出力ファイル名を指定（相対パスでも絶対パスでもOK。相対パスは呼び出し時のカレントディレクトリ基準で解決される）
video-studio/scripts/render.sh ep01 episodes/ep01/out/ep01_v2.mp4

# Remotion CLIを直接使う場合（video-studio/remotion がカレントディレクトリであること）
cd video-studio/remotion
npx remotion render doodle-short ../episodes/ep01/out/ep01.mp4 --props='{"episodeId":"ep01"}'
```

**ハマりどころ（render.shの過去のバグ）:** `render.sh` は内部で `cd "${REMOTION_DIR}"`（`video-studio/remotion`）してから
Remotion CLIを呼ぶ。第2引数（出力ファイル名）を相対パスで渡すと、この `cd` の後の相対パスとして解釈されてしまい、
`video-studio/episodes/.../out/xxx.mp4` ではなく `video-studio/remotion/episodes/.../out/xxx.mp4` という意図しない場所に
書き出されるバグがあった（Remotion CLIの実行時カレントディレクトリを基準に相対パスが解決されるため）。
このため「レンダリングは成功して尺やffprobeの結果も正しいのに、確認しているファイルには古い内容しか反映されない」という
非常に分かりにくい症状になった（実際には別の場所に正しいファイルができていた）。
`render.sh` 側で第2引数が相対パスの場合は呼び出し時点のカレントディレクトリを基準に絶対パス化するよう修正済み。
**教訓:** レンダリング結果を疑うより先に `find` で実際にファイルがどこに書かれているかを確認する。また、コード修正後に
"ファイルサイズが前回と一致する"だけでは検証にならない（同じ古いキャッシュ相当の内容を指している可能性がある）。
必ず更新後のファイルの mtime とフレーム内容（できれば複数カット）を確認すること。

プレビュー（Remotion Studio）:

```bash
cd video-studio/remotion
npm run dev
```

## 動作確認済み

**v1（ep01・ナレーション型）**
- `video-studio/scripts/render.sh ep01` で `video-studio/episodes/ep01/out/ep01.mp4` を書き出し。
- `ffprobe` で 1080x1920・30fps・h264/aac・尺 51.5秒（cut1/cut5のdurationSec拡張後）を確認済み。
- ナレーションwav（VOICEVOX・波音リツ、cut1〜cut8）を各カットの `narration` に反映し、`ffmpeg -af volumedetect` で
  ナレーションのあるカットは実音声（平均-28〜-29dB程度）、ナレーション/BGMなしのcut9は無音（-91dB）であることを確認済み。
- cut9の右下クレジット「VOICEVOX:波音リツ」が単独で正しい位置に描画されることをフレーム抽出で目視確認済み。
- **v2改修後の回帰確認**: v2実装後に ep01（`narration`のみ・`dialogue`未使用）を再レンダリングし、尺51.5秒・解像度・
  フレームレートが変わらず正常に書き出せることを確認済み（後方互換性OK）。

**v2（`episodes/_test-v2/` ダミー素材によるテンプレート機能検証。本番投入前提のepisode.jsonではなく検証用の使い捨てフィクスチャ）**
`_voice_samples` のダミーwav・ep01アセット流用画像・ffmpeg生成のダミーmp4を使い、以下を確認:
- **dialogue配列のシーケンス再生**: kanojo→kareshi→mob の3話者を`startSec`で連結配置し、`ffmpeg -af volumedetect`で
  各話者区間は実音声（-27〜-31dB程度）、話者間のギャップは無音に近い(-83dB)ことを確認。
- **mouthLayer口パク**: kanojoのセリフ区間（0-4.5s、toggleFps8）で、8fpsごとに`mouthClosed`/`mouthOpen`の異なる画像へ
  切り替わることをフレーム抽出で目視確認（4フレーム間隔でパッと切り替わり、補間なし）。
- **動画埋め込み+ループ**: `.mp4`画像を`videoLoopSec:1`で6秒カットに指定し、1周目と2周目の同一位相フレームがほぼ同一、
  周内の中間フレームは異なる絵になることを比較して確認（Loopコンポーネントが正しく機能）。
- **常時ゆらゆら**: カメラ演出`none`のカットでも、数フレーム離れたフレーム間で画像の位置/回転がわずかに異なることを
  目視確認。
- **紙テクスチャ**: `still`コマンドでPNG書き出しし、800x200pxの背景領域のRGB標準偏差が0.0（テクスチャ無し）から
  2.3〜2.6（テクスチャあり）に変化したことでCSSグラデーション方式の実装を検証（詳細は上記実装メモ参照）。

**v3（ep01・生成素材の組み込み: 背景レイヤー・mouthLayer展開・endcard差し替え）**
episode.jsonをセリフ劇(v2)構成へ全面組み替え（絵コンテ9カット→10カットに分割、cut6を6a/6bに分割）した上で、
`assets/gen/` の生成素材7点（背景3種、口開き顔2種、mob_girls、endcard）を組み込み。
- `ffprobe`: 1080x1920・30fps・h264/aac・尺37.76秒（10カット合計37.7秒と一致）
- `ffmpeg -af volumedetect`: セリフのある9カット全てで実音声（-27〜-30dB程度）、セリフ無しのcut10(エンドカード)は
  無音(-91dB)であることを確認
- セリフ間の重なり無し検証: cut1/cut2/cut5(意図的な「間」)/cut7(jump)/cut8(wave)の各セリフ間ギャップ区間を切り出し、
  -82〜-91dB（実質無音）であることを確認（cut3は2人同時発声の意図的な重ね再生のため対象外）
- 目視確認（フレーム抽出）: cut2(顔2枚交互+街並み背景)・cut4(彼女全身+傘の通り背景)・cut6(mob_girls+傘の通り背景)で
  multiplyブレンドによる背景/前景合成がキャラを隠さず自然に重なっていること、cut9(index9)の口パクが
  mouthLayer指定どおり閉じ/開きでトグルしていること、cut10(エンドカード)がendcard.png+3名クレジット表記で
  正しく表示されることを確認済み
- **上記のrender.shバグに一度引っかかり、誤った場所（`video-studio/remotion/episodes/...`）に書き出された古い内容を
  「正しい最新のレンダリング結果」と誤認しかけた。`find`で実際の書き込み先を特定し、バグ修正後に再レンダリングして
  解決した。**

## 残課題 / 今後の差し替え予定

- ep01 の cut1（歩行）・cut7=index7（彼のjump反応、既にkareshi_jump.mp4を1回再生で組み込み済みだが尺に対してクリップが
  長いため末尾はトリミングされている）は Animated Drawings 側のモーション成果物の追加調整があれば差し替える。
- SE（ヒュー・時計・ガーン）は音源が揃い次第、各カットの `se` に実パスを設定する。
- cut1（歩行ポーズ）・cut3（VR、屋内のため背景無し）は依然placeholder。歩きポーズ2枚が揃い次第 `images` を差し替える。
- `assets/gen/bg_ferris.png`（観覧車の背景）は生成済みだが今回の組み込み対象(team-lead指定)に含まれていない
  （cut7=index7 wave のシーンで使えそうだが、動画がフルブリードのため背景が隠れる想定で見送られている）。
  将来 wave シーンを動画でなく静止画+カメラ演出に戻す場合などに使える。
- 現在の `Cut` コンポーネントは背景1枚+前景1枚（画像/動画）の2レイヤーまで対応（v3で背景対応済み）。
  3枚以上のレイヤー合成が必要になった場合はさらに拡張が必要。
- `_test-v2` はテンプレート機能検証用の使い捨てフィクスチャ（ダミー音声・ダミー動画）。本番のepisode.jsonの一部ではないので、
  不要になれば `episodes/_test-v2/` ごと削除して構わない。
