# ゲーム部門プロトタイプ「巡室（じゅんしつ）」設計文書（コンセプトC実装）

> KR2.4（ゲーム部門: プロトタイプ1本試作＋実プレイテスト検証）対象。ブランチ `research/game-department-prototype`。
> 対象コンセプト: [ゲーム部門 探索フェーズ — コンセプトリサーチ報告](https://claude.ai/code/artifact/17c5e162-5657-4fdf-9bd1-15afa37aa0f3) 案C「歪みの一人称」。オーナー優先順位 C > A > E（2026-08-03）。

## SPEC

### 要求の再記述
コンセプトC「歪みの一人称ホラー」を14日規模のブラウザゲームプロトタイプとして実装し、友人5名→SNS/Discord 10〜20名の2段階で実プレイテストを行い、継続意向・満足度データを収集して2027年Go/No-Go判断材料とする。案A・Eは次点として着手しない。

### 暗黙の前提
- 技術・デプロイ・計測は実現可能性リサーチの推奨（ブラウザゲーム／localStorage永続化／マルチプレイなし）に従う
- 実装はSonnetサブエージェントに委譲し、オーケストレーター（本セッション）は設計・レビュー判定に専念する
- **憲章第1条の境界**: プレイテスター募集（友人への声かけ・SNS投稿）は「対外コミュニケーション」でL0＝オーナー専権。AI側はデプロイ可能な状態まで整え、募集の実行はオーナーに依頼する
- 外部分析SaaS（PostHog等）の新規契約は対外送信系のセットアップとしてグレーゾーンのため避ける

### テーゼ
**時間box付き検証フェーズの目的は「プレイテストデータを得ること」そのものであり、それに本質的に不要な複雑さ（ビルドパイプライン・外部サービス契約・複雑な永続化・対外コミュニケーションの自動化）を一切持ち込まない設計が、14日で実プレイテストに到達する確率を最大化する。**

以降の技術選定・デプロイ先・計測手法の全判断はこのテーゼから導出する。

## PLAN — 代替案比較

### 技術スタック
| 案 | 複雑度 | リスク |
|---|---|---|
| Phaser4 | 中（構造化APIだがビルドパイプライン要） | 今回のゲームは静止画観察+2択判断が核で、物理・タイルマップ等の機能は不要。オーバースペック |
| **Vanilla JS + Canvas（採用）** | 低（ビルドステップなし） | Grumbulus事例（2晩で15,000行）が同構成での高速開発を実証済み |

**決定**: Vanilla JS + HTML5 Canvas、ビルドステップなし。**却下理由**: Phaser4はテーゼ「不要な複雑さを持ち込まない」に照らし、今回のミニマルなゲームプレイには不要な依存・学習コストを持ち込む。

### デプロイ先
| 案 | リスク |
|---|---|
| **GitHub Pages（採用）** | 既存GitHubアカウントの範囲内、新規契約不要 |
| itch.io / Cloudflare Pages | 新規アカウント作成・利用規約同意が発生し、憲章L0「契約」境界に近づく |

**決定**: GitHub Pages。**却下理由**: itch.io等は配布プラットフォームとして強みがあるが、新規対外契約というグレーゾーンを持ち込む。将来の展開（プレイテスト第2弾以降）はオーナー判断で追加検討。

### 計測手法
| 案 | リスク |
|---|---|
| PostHog等外部SaaS | 新規サービス契約・APIキー発行が必要 |
| **localStorage自己記録＋ゲーム内アンケート＋JSON手動エクスポート（採用）** | 自動集計ではないが5〜20人規模には十分。契約不要 |

**決定**: ゲーム内終了時アンケート（5問）をlocalStorageに保存し、「結果をコピー」ボタンでJSON文字列をクリップボードに出力。プレイテスターがオーナー/開発者に送る運用。

## ゲームデザイン仕様（実装者に裁量を残さないための確定事項）

**コアループ**:
1. 同じ「部屋」を繰り返し提示（Canvas 2D描画、固定視点）
2. 各周回、部屋は「通常」か「異変あり」（15〜20種のパターンから1つ）
3. プレイヤーは「進む（正常）」か「戻る（異変あり）」を選択
4. 正解→周回数+1、次の部屋へ。誤答→ゲームオーバー、到達周回数がスコア
5. 難易度カーブ: 周回が進むほど異変が微細になる

**異変パターンの設計原則**: 「完璧すぎる／意図がない／統計的に不自然」というAIらしさの正体（市場・AIネイティブ両リサーチで確認済み）を演出の核にする。代表例: 家具の等間隔すぎる配置／影の向きと光源の矛盾／壁模様の反復回数の過不足／家具配置の意味のない鏡写し／時計と暦の不整合／窓の外の景色だけ変化。

**セッション設計**: 1周観察5〜10秒、1プレイ3〜10分。部屋の土台レイアウトは5〜8パターンをローテーション。

**操作**: マウスクリック/タップのみ（「進む」「戻る」ボタン）。モバイル対応。

**画面遷移**: title → playing → gameover → (survey) → title

**アセット方針**: 外部画像・音声アセット非使用。Canvas上の図形描画のみでプロシージャルに構成（AI生成アセットの拒否反応リスクを回避）。

### ディレクトリ構成
```
game-prototype/loop-room/
├── index.html
├── style.css
├── js/
│   ├── main.js          # 画面遷移制御
│   ├── room-renderer.js # Canvas 2D描画
│   ├── variants.js      # 異変パターン定義（15〜20種）
│   ├── game-state.js    # 状態管理・正誤判定
│   ├── survey.js        # アンケートUI・収集
│   ├── storage.js       # localStorage読み書き
│   └── test.mjs         # ロジック単体テスト（Node.js実行、DOM非依存部分のみ）
└── README.md
```

### データ構造・インターフェース（確定仕様・実装committed版）

> 本節は仕様ドライラン後、実際に委譲プロンプトで確定・実装された最終版。初期ドラフトの`judgeChoice(playerChoseVariant: boolean): boolean`という1引数シグネチャは、状態を明示的にやり取りする設計への具体化の過程で下記に置き換わっている（VERIFYで検出、実装側の逸脱ではなくドキュメント更新漏れと判定し本節で追従）。

```js
// variants.js: 各要素 { id, name, apply(roomState, round) => roomState(変異後の新オブジェクト、破壊的変更禁止) }
// roomState: { furniture: [{x,y,w,h,...描画用拡張プロパティ}], wallPattern: {...}, lightSource: {x,y,angle,...}, clock: {hourHand,minuteHand}, calendarDate: string, window: {sceneId} }
// export function computeMagnitude(baseMagnitude, round) => baseMagnitude * Math.max(0.25, 1 - round * 0.03)
// export const VARIANTS = [...] （15〜20個）

// game-state.js
// GameState shape: { round, bestRound, isVariant, currentVariantId, roomLayoutIndex, recentVariantIds: string[] }
// export function startNewGame(): GameState
// export function nextRound(state): GameState
// export function judgeChoice(state, playerChoseBack: boolean): { correct: boolean, newState: GameState }
// export function isGameOver(judgeResult): boolean

// room-renderer.js
// export function buildBaseRoomState(layoutIndex): roomState
// export function render(ctx, roomState): void — 5〜8種のbaseレイアウトをroomLayoutIndexで切替

// storage.js
// saveBestRound(n), loadBestRound(), saveSurveyResponse(obj), loadSurveyResponses(), exportSurveyAsJSON()

// survey.js
// 5問（また遊びたいか1-5／怖さ1-5／難易度1-5／良かった瞬間の自由記述／イライラした瞬間の自由記述）
// storage.js経由で保存、navigator.clipboard.writeTextでJSON出力
```

## タスク粒度についてのミニADR

**背景**: fable-classは2〜5分粒度のマイクロタスク分解を原則とするが、本ゲームのコアロジック（状態管理・描画・異変定義・永続化・アンケート）は相互のデータ構造が密結合している。

**決定**: ゲーム本体（index.html + style.css + js/*.js 一式）は1タスク・1エージェントに集約実装。デプロイ設定（GitHub Actions + README）は本体完了後の別タスクとして直列実行する。

**理由**: 実現可能性リサーチで、密結合コンポーネントを並列生成すると統合バグが発生することが実証されている（Grumbulus事例: 18件の統合バグ）。単一エージェントへの集約と、本ドキュメントでのインターフェース事前定義を組み合わせることで、実装者の裁量を排除しつつ統合バグを回避する。

**却下案**: 8タスクへの機械的分割（画面・状態・描画・異変・永続化・アンケート等を別エージェントに分担）。マイクロタスク原則には忠実だが、ファイル間インターフェースの実装時ズレによる統合バグリスクが看過できないため却下。

## 仕様ドライランで検出された曖昧点への確定回答

仕様ドライラン（新規コンテキストのsonnetエージェントに本ドキュメントの仕様のみを渡し、曖昧点を列挙させた）で7点の未確定事項が検出された。以下で確定する。

1. **判定ロジック**: 「異変あり」で「進む」を選んでも、「異変なし」で「戻る」を選んでも、どちらも誤答＝即ゲームオーバーとする（空振りにもペナルティを課す）。`judgeChoice(playerChoseVariant: boolean): boolean` は「正解だったか」を返す（false＝呼び出し側でgameOver()を呼ぶ）。緊張感を保つため「失敗できる」設計を徹底する（Suck Up!のUX教訓: 失敗判定が消えると緊張感が消える）。
2. **異変の有無の抽選**: 各周回、異変の有無は確率50%固定（コイントス）。
3. **異変パターンの選出**: 直近2周回で使用したvariant IDは選出プールから除外し、重複を避ける。
4. **難易度カーブ**: 異変の「有無」の確率は変えず、異変の「視認しやすさ」で難易度を作る。`variants.js`に共通ヘルパー`computeMagnitude(baseMagnitude, round) => baseMagnitude * Math.max(0.25, 1 - round * 0.03)`を追加し、全variantの`apply()`はこの関数で減衰させた変化量を使う。
5. **baseレイアウトの切り替え**: 1プレイ（ゲームオーバーまで）を通して固定。`startNewGame()`内でランダムに1つ選び、以降変更しない（「同じ部屋を繰り返し観察する」という体験の核を守るため）。
6. **roomStateの初期化**: `room-renderer.js`に`buildBaseRoomState(layoutIndex): roomState`を追加し、baseレイアウトからroomStateを生成する。`variants.js`の`apply()`はこの結果のディープコピーを受け取って変異させる。
7. **観察時間**: 強制タイマーなし。目安として5〜10秒だが、操作はいつでも可能（プレイヤーのペースに委ねる。強制タイマーは離脱要因になりやすい）。
8. **アンケート発生条件**: ゲームオーバー画面に「もう一度」に加え「感想を送る」ボタンを常設。強制ではなく任意、プレイ終了ごとに毎回選べる。`exportSurveyAsJSON`は`loadSurveyResponses()`で蓄積された全件を対象とする。
9. **恐怖感の演出（音声なし・図形のみの制約下）**: 背景は暗いグレー（#1a1a1a程度）、部屋の輪郭線は薄いグレー。ゲームオーバー時にCSS transitionで一瞬赤みのフラッシュ。正しく次周回に進む際は一瞬暗転してからフェードイン。BGM・SEなし＝無音であること自体を演出とする。

## 仕様ドライラン結果（参考記録）

検出された曖昧点の原文は`docs/design/`の変更履歴（本コミット）に残す。実装者への委譲プロンプトには、上記の確定回答をすべて含める。

## DoD（完了定義）
- [ ] index.htmlをブラウザで直接開く（file://）かローカルサーバーで動作確認できる
- [ ] title→playing→gameover→(survey)→titleの画面遷移が一通り動作する
- [ ] 異変パターンが最低15種実装されている
- [ ] 周回数カウントと自己ベストのlocalStorage永続化が動作する
- [ ] アンケート回答のJSON出力（クリップボードコピー）が動作する
- [ ] モバイル（タッチ操作・レスポンシブ）で操作可能
- [ ] GitHub Pages用デプロイ設定一式が用意されている
- [ ] READMEに遊び方とローカル起動手順が書かれている
