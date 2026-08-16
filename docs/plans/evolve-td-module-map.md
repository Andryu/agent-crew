# 群変（evolve-td）モジュール地図（CP3時点）

CP4実装者は、この地図＋自分が触るファイル＋設計/UX文書の該当節だけを読めば着手できることを目指す。

## config.js
全数値の一元定義。塔4種（TOWERS）、経済（ECONOMY, killReward）、盤面（GRID, LANE_LENGTH）、
遺伝子範囲（GENOME_RANGES, GENOME_BASE, INITIAL_JITTER=0.2, INITIAL_LANE_NOISE=0.15, hpBaseForWave, RESIST_HP_COST=0.85）、個体数式（POPULATION,
populationSizeForWave）、色/形状符号（RESIST_COLORS, RESIST_MARKER_SHAPES, TOWER_COLORS,
TOWER_SHAPES）、解禁ウェーブ（UNLOCK_WAVES）、進化パラメータ（EVOLUTION: parentRatio 0.3/parentMin 6/多様性保険 0.15 ほか、DIFF_THRESHOLDS: stat 4%/share 8pt/shareMinAfter 15%/soft 1%・3pt）、表示名（RESIST_LABELS, LANE_LABELS）、スキル（SKILL: 発熱 CD30s・0.5・cold耐性0.75・3.0s）、
ウェーブ数（WAVE_COUNT=15）、到達被害（REACHED_DAMAGE_LARGE_SIZE_THRESHOLD=1.2, REACHED_DAMAGE_LARGE=2, REACHED_DAMAGE_SMALL=1）、
属性一致ダメージ倍率（RESIST_DAMAGE_MULT=0.5、CP2レビューで塔のapplyDamageハードコードから移設）、
撃破ジュース・UI演出数値（JUICE: 粒子個数6-10・速度30-80px/s・寿命0.4s、資金ポップ寿命0.6s・上昇速度
-20px/s、撃破音スロットル0.04s、トースト2000ms、初回吹き出しタイムアウト8000ms、振動50ms、
ビネット0.25s＝style.cssの実体値と一致させる記録用。2026-08-17 main.jsのハードコードから移設）。
公開: 全て名前付きexport（関数以外は定数オブジェクト）。

## rng.js
- `makeRng(seed): rngFn` — mulberry32。`rngFn()`→[0,1)、`rngFn.int(n)`、`rngFn.pick(arr)`、`rngFn.normal(mean, sd)`（Box-Muller）。同seedで同列を保証。

## evolution.js（純粋関数・DOM非依存、乱数は引数で注入）
- `initialPopulation(n, rng): genome[]` — speed/hp/size 基準値±20%、resist=0、lane 均等±0.15ノイズ→正規化。
- `evaluate(results): number[]` — `progress + (reachedBase?1:0) + damageDealtToBase*0.25`。
- `evolve(population, fitness, ctx, rng): genome[]` — 上位30%（最低6）親プール、一様交叉、突然変異
  p=0.08*(1+(1-towerDiversity))（stat σ0.15乗算・resist 現在値除外再抽選・lane±0.15）、15%多様性保険（置換）、クランプ。
  `ctx = {wave, towerDiversity, nextSize}`。
- `summarize(population): {speedMean, hpMean, sizeMean, resistShare[4], laneShare[3]}`
- `diffReport(prevSummary, nextSummary): string[]` — 最大3行。閾値通過なしなら「わずかに〜」1行 or 定型1行。
- `representative(population, summary): genome` — 平均に正規化距離が最も近い個体（レポート・負けた画で使う）。

## game-state.js
GameState: `{seed, gold, lives, wave, phase:'place'|'wave'|'report', towers:[{id,col,row}],
population, prevSummary, lastSummary, unlocked, waveDiversity, cleared, endless, bestWave, skillReadyAt}`。
- `startNewGame({seed,gold}): GameState`
- `canPlace/placeTower/sellTower(state, ...): boolean|GameState`
- `startWave(state): GameState` — `waveDiversity` をこの時点でスナップショット、`skillReadyAt=0`
- `skillUnlocked(state): boolean`（wave>=3）／`useSkill(state, lane, now): GameState`（未解禁/非wave/CD中/不正laneなら不変。発動で `skillReadyAt=now+30`）
- `loseLives(state, n): GameState`
- `endWave(state, results, rng): {state, report}` — evaluate→evolve→summarize→diffReport を実際に呼ぶ
  （CP1から）。`prevSummary = state.lastSummary ?? summarize(state.population)`。
  `cleared = (state.wave===15 && !state.endless)`。phase→'report'
- `closeReport(state): GameState` — wave+1、`unlocked=unlockedTowers(wave)`、phase→'place'
- `continueEndless(state): GameState` — `endless=true, cleared=false`
- `isCleared/isGameOver(state): boolean`
- `unlockedTowers(wave): string[]` — 累積解禁

## enemies.js
Enemy: `{genome, lane(0-2), x, hp, maxHp, spawnAt, realSpeed, slowUntil, slowFactor, alive, reached}`。
- `spawnFromPopulation(population, wave, rng): Enemy[]` — `spawnAt=index*0.6`、初期`x=-1`、実HP=hpBase*hp*size*(resist≠0?0.85:1)
- `livesLostFor(genome): 1|2`（size>=1.2 で 2）
- `applyHeatToLane(enemies, lane, now): void` — 出現済み生存個体の減速factorを「現在のslowFactorと発熱factor(0.5、cold耐性0.75)の小さい方」に、slowUntilを「現在値とnow+3.0の大きい方」に更新（applySlowとは別ロジック。cold塔で既に強い減速が乗っていてもno-opにならず、持続時間だけは必ず延長される。2026-08-16 CP2レビュー対応）
- `stepEnemies(enemies, dt, laneLength=12, now): void` — 破壊的更新。`now`はwaveClock基準の
  現在時刻（cold/発熱の減速判定に使用、省略時は減速無視）
- `collectResults(enemies, laneLength): results[]`
- `applySlow(enemy, factor, durationSec, now): enemy` — 強い方優先、同じなら延長、弱ければ無視
- `pickGameOverRepresentative(enemies, laneLength=12): genome|null` — ゲームオーバー時点で
  出現済み(spawnAt<=0)のalive/reached個体から即席スコア`(reached?2:0)+x/laneLength`最大の1体の
  genomeを返す（同点はgenome.hpが大きい方）。該当個体なしはnull（呼び出し側でフォールバック要）。
  純粋関数として2026-08-17 main.jsから移設（同点ケースで`best.genome.hp`参照の例外バグを修正）

## towers.js
- `stepTowers(towerInstances, enemies, dt, laneRows, now=0): shots[]` — 索敵は「射程内で最も
  臓器に近い個体」。ヒットスキャン即着弾。heatは着弾点半径0.8セル全個体、coldは`applySlow`呼び出し。
  `towerInstances`要素へ`cooldown`を破壊的に付与。shots: `{x1,y1,x2,y2,towerId,ttl}`（0.1秒軌跡、色は renderer が config から）

## renderer.js（DOM/Canvas依存）
- `render(ctx, {towers, enemies, shots, rangePreview, laneSelectAlpha?, laneFlash?, particles?, goldPopups?}): void`
  — 論理解像度576×384。CP3で`particles`（撃破粒子）・`goldPopups`（資金ポップ）の描画を追加
- `renderGenomeIcon(ctx, genome, size): void` — genome静止描画（プレビュー・レポート・CP3負けた画で共用）
- `drawTowerIcon(ctx, towerId, size): void` — パレット用アイコン。`LOGICAL_WIDTH/LOGICAL_HEIGHT` — 576/384

## share.js（純粋関数・DOM非依存）
- `encodeChallenge({seed, gold}): string` — base64url化（`"#c="`を除いた部分）
- `decodeChallenge(hashOrPayload): {seed,gold}|null` — `"#c=..."`付き/なし両方受理。v≠1・seed非整数/範囲外(uint32外)・gold範囲外(ECONOMY.goldRange外)・パース不能はnull

## storage.js（localStorage、キー接頭辞 `evolveTd.`、不在でも全関数が例外を投げない）
`saveBestWave/loadBestWave`（自己ベストのみ、内部でmax）、`saveSurveyResponse/loadSurveyResponses`、
`exportSurveyAsJSON(): string`（`{responses,bestWave,challengeReceived,sessions,wave2Started}`）、
`markChallengeReceived/hasChallengeReceived`、`markSeenIntro/hasSeenIntro`、
`recordSessionStart/recordWave2Started`（離脱計測点「ウェーブ2開始率」の分母/分子）。

## survey.js（DOM依存）
- `initSurvey({onBackToTitle, onSkip?, getReachedWave}): void` — `#survey-form`（5問）送信で保存＋
  exportSurveyAsJSONをクリップボードへコピー。スキップ/タイトルへ戻るを配線
- `resetSurveyScreen(): void` — フォーム・送信後表示を初期化

## audio.js（DOM/Web Audio依存、合成のみ・外部音声ファイルなし、失敗時は無音続行）
`initAudio()`（ユーザー操作内で呼ぶ）、`playPlace(lowPitch?)`（売却は`true`で低ピッチ）、`playKill()`、
`playHit()`（到達被害音）、`playWaveStart()`、`setMuted(boolean)`、`isMuted(): boolean`。

## main.js（DOM依存、エントリーポイント）
画面遷移 title→playing→result→survey→title。配置/ウェーブフェーズ、塔パレット、セルタップ配置、売却ポップアップ、
ウェーブ開始/×2、HUD、ゲームオーバー/クリア。PC: `1-4`選択・`Space`開始・`Tab`速度・`Esc`解除。
画面状態は `screen`（title/playing/result/survey）、`state.phase` は place/wave/report のみ。
CP2: `endWave` 後に変異レポート modal（`#report-modal`、見出し「第{wave}世代の記録」、wave===1 のとき `#report-intro`）
→「とじる」で `closeReport`。`cleared` なら modal なしで result(クリア)。次ウェーブプレビュー `#preview-panel`
（配置フェーズ・wave>=2）。発熱 `#skill-button`（W3解禁、押下→レーン選択モード `#skill-select-banner`→盤面タップで
最寄りレーン→`useSkill`+`applyHeatToLane`、Esc/再押下/盤面外でキャンセル、F キー）。

CP3: タイトルで`decodeChallenge(location.hash)`検出→`#challenge-banner`「この条件で始める」
（`markChallengeReceived`後`startGame({seed,gold})`）/「通常ではじめる」（ハッシュ破棄）。結果画面に代表
個体拡大描画＋添え書き（`formatResultCaption`、負けは`enemies.pickGameOverRepresentative`＝出現済み
個体の即席スコア最大、クリアは`pickClearRepresentative`＝W15 evaluate最大）、「この条件で挑戦状を送る」
（`encodeChallenge`+定型文コピー、`#toast`）、「アンケートに答える」。`#mute-button`。`#retry-button`（もう
一度あそぶ）はゲームオーバーのみ表示、クリア画面では非表示（UX§7.2のボタン4つ＝エンドレス／挑戦状／
アンケート／タイトル）。`#intro-bubble`は`hasSeenIntro()`未設定セッションのみ、配置成功/ウェーブ開始/
タイムアウトで`markSeenIntro`（`seenIntroThisSession`でCP2レポート初回1行とも連動）。消滅は即時`hidden`
ではなく`is-fading`クラス→0.3秒後に`hidden`（style.cssの`opacity`transition）。撃破時に粒子
(reduced-motionで省略)と資金ポップ、到達時に`#vignette-overlay`赤ビネット。これら演出の個数・速度・
寿命・タイムアウト等の数値は`config.js`の`JUICE`定数に一元化（2026-08-17）。売却ボタンは`row>=6`で
上側反転、配置失敗で振動（`JUICE.vibrateMs`）。
wave2到達で`recordWave2Started`、開始で`recordSessionStart`、終了で`saveBestWave(state.wave)`。
