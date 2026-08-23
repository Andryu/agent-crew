# genimage: Gemini (Nano Banana) 画像生成セットアップ

EP01 の落書き素材（口パク差分・背景・モブ・エンドカード）を、オーナーの手描き参照画像を
マルチモーダル入力として渡しながら Gemini の image generation モデルで生成するためのスクリプト。

## スクリプト

- `video-studio/scripts/genimage.py`
  - 引数: `--prompt "..."` `--ref path.png`（複数指定可）`--out path.png` `--model モデル名`
  - `GEMINI_API_KEY` 環境変数必須
  - 参照画像は inline_data として base64 でリクエストに含める（複数枚可）
  - レスポンスの `inlineData` から画像バイト列を取り出して `--out` に保存

使用例:

```bash
python3 video-studio/scripts/genimage.py \
  --prompt "この落書きキャラの口を大きく開けたバージョンを、同じ素人落書きタッチ（太さが不均一な線・ヨレた輪郭・白背景・彩色ほぼ無し）で再現。口以外はできるだけ同一に。" \
  --ref video-studio/episodes/ep01/assets/kanojo_face.png \
  --out video-studio/episodes/ep01/assets/gen/kanojo_face_open.png \
  --model gemini-2.5-flash-image
```

## 利用可能な nano banana 系モデル（2026-07-20 時点で `/v1beta/models` に存在）

| モデル名 | 系統 | 備考 |
|---|---|---|
| `gemini-2.5-flash-image` | Nano Banana (初代) | image generation、`generateContent` |
| `gemini-3.1-flash-image` / `-preview` | Nano Banana 2 系 | 同上 |
| `gemini-3.1-flash-lite-image` | Nano Banana 2 Lite | 同上、軽量 |
| `gemini-3-pro-image` / `-preview` | Pro 系画像生成 | 高品質・高コスト想定 |
| `nano-banana-pro-preview` | Nano Banana Pro | 同上 |
| `imagen-4.0-*` | Imagen 4 系 | `predict` エンドポイント、参照画像を使った編集向けではない（テキストto画像中心） |

いずれも `responseModalities: ["IMAGE"]` を指定して `generateContent` で呼び出す想定
（本スクリプトの `genimage.py` はこの形式に対応済み）。

## 現状のブロッカー（2026-07-20 未解決）

**このAPIキーに紐づくプロジェクトで、Gemini API の無料枠デイリークォータが 0 になっており、
画像生成はおろかテキスト生成すら実行できない。**

再現した事実:
- `gemini-2.5-flash-image` / `gemini-3.1-flash-image` / `gemini-3.1-flash-lite-image` /
  `gemini-3-pro-image` / `nano-banana-pro-preview` の画像生成モデル全て `429 RESOURCE_EXHAUSTED`
- プレーンテキストの `gemini-2.0-flash` / `gemini-2.0-flash-lite` でも同一エラー
- エラー詳細は一貫して `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 0`
- 45秒程度の間隔を空けた再試行でも解消せず（レート制限の瞬間的な混雑ではなく、
  日次クォータそのものが 0 = 無料枠がプロジェクトに割り当てられていない状態）

つまりモデル選定の問題ではなく、**APIキー/プロジェクト側の無料枠が有効化されていない**。

### 想定される原因と対処（オーナー確認事項）

1. `https://ai.dev/rate-limit` でこのプロジェクトの現在のクォータ状況を確認する
2. Google AI Studio (https://aistudio.google.com/apikey) で発行したキーが、
   意図したプロジェクトに紐づいているか確認する（Google Cloud のプロジェクトを
   後から関連付けた場合、無料枠が外れることがある）
3. 無料枠が本当に 0 のままなら、プロジェクトに課金を有効化する
   （Nano Banana 系は従量課金でも比較的安価。1枚あたり目安は数円〜十数円程度）
4. 別プロジェクト/別アカウントで新規に AI Studio の API キーを発行し直すのも有効
   （新規プロジェクトはデフォルトで無料枠が付与されるケースが多い）

上記のいずれかで無料枠 or 課金が有効化され次第、`genimage.py` はそのまま使える状態にしてある。
このドキュメント作成時点では **1枚も画像を生成できていない**（後述の「生成結果」参照）。

## プロンプトの型（動作確認でき次第、実プロンプトで更新予定）

以下は今回組み立てて投げた口パク差分用のプロンプト（実行はクォータ切れで失敗、内容は温存）:

```
This is a reference image of a hand-drawn amateur doodle character (a girl), created by an
untrained artist using a phone note app. Study the exact line style: uneven, wobbly pen strokes
with inconsistent thickness, slightly crooked outlines, minimal shading, almost no color except
light brown scribbled hair, plain white background, childlike proportions. Redraw the SAME
character in the SAME doodle style, same face shape, same hair, same expression details, but with
the mouth open wide (as if talking/singing), instead of the small closed mouth in the reference.
Keep everything else as close to identical as possible: same head/shoulder framing, same simple
black line eyes and eyebrows, same messy uneven pen linework, same white background, no clean
vector lines, no anime shading, no watermark, no text, no UI elements, no screenshot chrome.
```

ポイント:
- 「素人が描いた」「線の太さが不均一」「輪郭がヨレている」を明示的に言語化する
- 「クリーンなベクター線／アニメ塗りにするな」を否定形で明示する
- 参照画像に含まれる意図しない要素（スマホのステータスバーやアプリUIのアイコンなど、
  実機スクショゆえに写り込んでいるもの）は出力に含めないよう明示的に除外指示を入れる
  （kanojo_face.png / kareshi_body.png 等の参照素材はメモアプリのスクショそのままで、
  時計・戻る矢印・undo/redoアイコン等のUIが写り込んでいるため）
- ウォーターマーク・テキスト・透かしの禁止も明示する
