# 調査レポート：動画制作パイプラインをClaude Codeスキルで構築できるか

作成日: 2026-07-20
前提: EP01（ハウステンボス回）の制作フローを対象に、各工程を Claude Code スキル＋MCP＋外部API で自動化できるかを調査。

---

## 1. 結論

**8工程中6工程はスキル化可能。** 人間に残るのは「元絵を描く」「品質チェック」「TikTok/Instagramへの投稿ボタン」の3つだけ。
（※リッチ演出のimage-to-video API＝fal.ai/Kling等はオーナー判断で不採用。動きはAnimated Drawingsのミニマム表現に統一する——手書き感の維持にもコスト0円化にも寄与）

| 工程 | 自動化 | 手段 | コスト |
|---|---|---|---|
| ① 台本・絵コンテ生成 | ◎ 完全自動 | Claude Codeスキル（プロンプトのみ） | 0円 |
| ② キャラ元絵 | ✗ 人間（ここが価値） | — | 0円 |
| ③ ポーズ違い・背景生成 | ◎ 完全自動 | Gemini API（Nano Banana 2） | 約$0.045/枚、AI Studio無料枠 約500req/日 |
| ④ 動き付け（歩く・跳ぶ・手を振る） | ◎ 完全自動 | **Animated Drawings（OSS）をローカル実行** | 0円 |
| ⑤ 音声合成 | ◎ 完全自動 | **VOICEVOXエンジンのローカルREST API** | 0円 |
| ⑥ 合成・字幕・書き出し | ◎ 完全自動 | **Remotion（Claude Code Agent Skills公式対応）** | 0円※ |
| ⑦ YouTube投稿 | ○ 半自動 | YouTube Data API（限定公開で上げて人間が公開） | 無料（6本/日まで） |
| ⑧ TikTok / Instagram投稿 | △ 当面手動 | 公式APIは審査制で個人には厳しい（後述） | — |

※ Remotionは個人・小規模チームは無料ライセンス（規模が大きくなったら要有償ライセンス確認）

**1本あたりの変動費は実質0円（画像生成がGemini無料枠に収まる限り）。**

---

## 2. 各工程の裏付け

### ④ Animated Drawings はOSSでローカル実行できる（今回の最重要発見）

動き付けはこれ一本に統一する（リッチ演出APIは不採用）。EP01の絵コンテもwalk/jump/waveの3モーション＋静止画で成立する設計になっており、ミニマムな動きの方が手書き感も保てる。

Webデモを手で操作する必要はない。[facebookresearch/AnimatedDrawings](https://github.com/facebookresearch/AnimatedDrawings) が公開されており:

- `pip install -e .`（Python 3.8系 + conda）でローカル導入
- `render.start(config.yaml)` で **MP4/GIF書き出しまでコード実行可能**
- キャラの関節アノテーションは TorchServe + 同梱Dockerfile の自動検出スクリプトあり
- モーション（walk / jump / dance / wave 等）はYAML設定で切り替え → **スキルから完全制御できる**

つまり「絵を置いてスキルを叩けば、歩行ループMP4が出てくる」状態にできる。

### ⑥ VOICEVOX はローカルサーバーとしてREST APIを持つ

[VOICEVOX/voicevox_engine](https://github.com/VOICEVOX/voicevox_engine) を起動すると `localhost:50021` にHTTP APIが立つ:

```
POST /audio_query?text=...&speaker=N  → 音声クエリJSON
POST /synthesis?speaker=N             → wavファイル
```

台本の9行をループでcurlするだけで全ナレーションが生成できる。[API仕様書](https://voicevox.github.io/voicevox_engine/api/)も公開されており、Claude CodeからのCLI自動化事例も既にある。

### ⑦ Remotion が Claude Code Agent Skills に公式対応（2026年1月）

[Remotion](https://www.remotion.dev/) は「Reactコンポーネントで動画を書く」フレームワーク。ヘッドレスChromiumでフレームを描画しFFmpegで結合する仕組みなので:

- 絵コンテの9カット＝Reactコンポーネント9個としてテンプレート化できる
- 字幕・SEタイミング・9:16書き出しがすべてコードで再現可能 → **2本目以降はJSONを差し替えるだけ**
- 2026年1月にClaude CodeのAgent Skillsへ公式対応し、「プロンプト→動画生成」の事例が多数出ている

CapCutは高機能だがAPI/CLIがなく自動化不可。**自動化パイプラインの心臓部はRemotion一択。**

### ③ 画像生成はAPIで呼べる

- **Gemini API（Nano Banana 2 = gemini-3.1-flash-image）**: 「同じ落書きタッチでポーズ違い」の画像編集がAPIで可能。約$0.045/枚、[Google AI Studio無料枠が約500リクエスト/日](https://blog.laozhang.ai/en/posts/gemini-image-api-guide-2026)あるので実質無料で回せる。※API生成画像は透かし（SynthID）の仕様に注意

### ⑦⑧ 投稿APIの現実

- **YouTube Data API**: 動画アップロード1本=1,600ユニット、デフォルトクォータ10,000/日 → **1日6本まで自動投稿可能**。個人でも使える。「限定公開でアップ→人間が確認して公開」の半自動が安全
- **TikTok Content Posting API**: アプリ審査（2〜6週間）が必要で、**未審査アプリの投稿は非公開限定**。個人が今すぐ使うのは非現実的 → 当面は手動投稿（書き出しファイルを渡すところまで自動化）
- **Instagram Graph API (Reels)**: ビジネス/クリエイターアカウント化が前提。こちらも当面手動が現実的
- 3プラットフォーム同時投稿を本気で自動化するなら Blotato / Postiz 等のサードパーティ投稿APIという選択肢もある（有料、月$29〜程度）

---

## 3. 提案アーキテクチャ：`video-studio` スキルセット

agent-crew 流に、工程ごとのスキルに分割する。

```
.claude/skills/
├── ep-plan/      # ネタ1行 → 台本・絵コンテJSON生成（Claudeのみ）
├── ep-assets/    # 絵コンテJSON → 不足素材をGemini APIで生成（要レビュー）
├── ep-animate/   # キャラPNG → AnimatedDrawingsでモーションMP4書き出し
├── ep-voice/     # 台本JSON → VOICEVOXローカルAPIでwav一括生成
├── ep-render/    # 素材+JSON → Remotionテンプレで9:16動画に合成
└── ep-publish/   # YouTubeへ限定公開アップ＋TikTok/IG用ファイル書き出し
```

- 各スキルの入出力を `episodes/ep01/` のようなディレクトリ規約で受け渡し（台本=JSON、素材=PNG、音声=wav、成果物=MP4）
- 一気通貫の `/ep-produce` スキルが上記を順に呼ぶ。**人間のチェックポイントは「素材生成後」と「最終動画確認後」の2箇所**だけ
- MCPは必須ではない（Gemini/fal.aiはcurlで足りる）。Notion管理やSlack通知を挟みたくなったら既存連携を流用

### 初期セットアップ（1回だけ）

1. AnimatedDrawings のconda環境構築 + アノテーション用Docker
2. VOICEVOXエンジン導入（アプリ or Docker、起動で localhost:50021）
3. Remotionプロジェクト作成 + 「落書きショート」テンプレート実装（字幕スタイル・SE配置込み）
4. Gemini APIキー取得（無料枠）
5. YouTube Data API のOAuth設定

セットアップは半日〜1日想定。**ここを乗り越えると、2本目以降は「ネタ1行＋不足素材の落書き」だけで動画が出てくる。**

---

## 4. リスクと注意点

- **AnimatedDrawingsはPython 3.8系**と古め。conda環境を分離して隔離すること（メンテが止まっているリスクはあるがローカル完結なので急に使えなくなることはない）
- **Gemini API画像の透かし（SynthID）**: 不可視透かしは実害なしだが、可視透かしの有無はモデル/プランで異なるため導入時に実機確認する
- **Remotionのライセンス**: 個人利用は無料。収益が伸びて法人化・チーム化する際は企業ライセンス要否を再確認
- **VOICEVOXキャラ規約**: 使う話者ごとにクレジット表記等の規約を確認（多くは「VOICEVOX:キャラ名」表記で商用可）
- **投稿の完全自動化はまだしない**: 品質事故（音ズレ・素材崩れ）をそのまま公開するリスクがあるため、公開ボタンは人間に残すのが当面の推奨

---

## Sources

- [facebookresearch/AnimatedDrawings（GitHub）](https://github.com/facebookresearch/AnimatedDrawings)
- [VOICEVOX/voicevox_engine（GitHub）](https://github.com/VOICEVOX/voicevox_engine)
- [voicevox_engine API Document](https://voicevox.github.io/voicevox_engine/api/)
- [VOICEVOXをClaude CodeでCLI自動化する実践ガイド](https://peaky.co.jp/voicevox-claude-code-cli-automation/)
- [Remotion | Make videos programmatically](https://www.remotion.dev/)
- [Remotion × Claude Code Agent Skills 完全ガイド](https://www.aquallc.jp/remotion-ai-video-guide/)
- [【Remotion】Agent Skills × Claude Codeでプロンプトから動画生成](https://weel.co.jp/media/tech/remotion/)
- [Complete Gemini Image API Guide 2026（Nano Banana料金）](https://blog.laozhang.ai/en/posts/gemini-image-api-guide-2026)
- [Nano Banana による画像生成（Google公式）](https://ai.google.dev/gemini-api/docs/image-generation)
- [YouTube API Guide 2026: Quotas](https://zernio.com/blog/youtube-api)
- [TikTok Content Posting API Guide（公式）](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- [TikTok Content Posting API: The Complete Developer Guide [2026]](https://zernio.com/blog/tiktok-developer-api)
- [Social Media API Rules: Limits & Specs (2026)](https://postproxy.dev/blog/social-media-platform-api-rules-rate-limits-media-specs/)
