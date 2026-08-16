# 群変（evolve-td）モジュール地図（CP1時点）

CP2/CP3の実装者は、この地図＋自分が触るファイル＋設計/UX文書の該当節だけを読めば着手できることを目指す。

## config.js
全数値の一元定義。塔4種（TOWERS）、経済（ECONOMY, killReward）、盤面（GRID, LANE_LENGTH）、
遺伝子範囲（GENOME_RANGES, GENOME_BASE, INITIAL_JITTER, hpBaseForWave）、個体数式（POPULATION,
populationSizeForWave）、色/形状符号（RESIST_COLORS, RESIST_MARKER_SHAPES, TOWER_COLORS,
TOWER_SHAPES）、解禁ウェーブ（UNLOCK_WAVES）、進化パラメータ（EVOLUTION, DIFF_THRESHOLDS ※CP2用）。
公開: 全て名前付きexport（関数以外は定数オブジェクト）。

## rng.js
- `makeRng(seed): rngFn` — mulberry32。`rngFn()`→[0,1)、`rngFn.int(n)`、`rngFn.pick(arr)`、
  `rngFn.normal(mean, sd)`（Box-Muller）。同seedで同列を保証。

## evolution.js（純粋関数・DOM非依存、乱数は引数で注入）
- `initialPopulation(n, rng): genome[]` — 本実装。基準値±10%ジッター、resist=0、lane均等。
- `evaluate(results): number[]` — 本実装。`progress + (reachedBase?1:0) + damageDealtToBase*0.25`。
- `evolve(population, fitness, ctx, rng): genome[]` — **CP1はスタブ**
  （`initialPopulation(ctx.nextSize, rng)` を返すのみ、`// CP2: replace body`）。
  `ctx = {wave, towerDiversity, nextSize}`。
- `summarize(population): {speedMean, hpMean, sizeMean, resistShare[4], laneShare[3]}` — 本実装。
- `diffReport(prevSummary, nextSummary): string[]` — **CP1はスタブ**（`[]` を返す、`// CP2: replace body`）。

## game-state.js
GameState: `{seed, gold, lives, wave, phase:'place'|'wave'|'report', towers:[{id,col,row}],
population, prevSummary, lastSummary, unlocked, waveDiversity, cleared, endless, bestWave}`。
- `startNewGame({seed,gold}): GameState`
- `canPlace/placeTower/sellTower(state, ...): boolean|GameState`
- `startWave(state): GameState` — `waveDiversity` をこの時点でスナップショット
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
- `spawnFromPopulation(population, wave, rng): Enemy[]` — `spawnAt=index*0.4`、初期`x=-1`
- `stepEnemies(enemies, dt, laneLength=12, now): void` — 破壊的更新。`now`はwaveClock基準の
  現在時刻（cold/発熱の減速判定に使用、省略時は減速無視）
- `collectResults(enemies, laneLength): results[]`
- `applySlow(enemy, factor, durationSec, now): enemy` — 強い方優先、同じなら延長、弱ければ無視

## towers.js
- `stepTowers(towerInstances, enemies, dt, laneRows, now=0): shots[]` — 索敵は「射程内で最も
  臓器に近い個体」。ヒットスキャン即着弾。heatは着弾点半径0.8セル全個体、coldは`applySlow`呼び出し。
  `towerInstances`要素へ`cooldown`を破壊的に付与。shots: `{x1,y1,x2,y2,color,towerId,ttl}`（0.1秒軌跡）

## renderer.js（DOM/Canvas依存）
- `render(ctx, {towers, enemies, shots, rangePreview}): void` — 論理解像度576×384
- `drawTowerIcon(ctx, towerId, size): void` — パレット用アイコン単体描画
- `LOGICAL_WIDTH/LOGICAL_HEIGHT` — 576/384

## main.js（DOM依存、エントリーポイント）
画面遷移 title→playing→result。配置/ウェーブフェーズ、塔パレット、セルタップ配置、売却ポップアップ、
ウェーブ開始/×2、HUD、ゲームオーバー/クリア。PC: `1-4`選択・`Space`開始・`Tab`速度・`Esc`解除。
CP1では`endWave`直後に`closeReport`を即時に呼ぶ（`cleared`ならresult(クリア)へ）。

## CP2/CP3で追加予定（CP1では未実装）
変異レポートmodal・次ウェーブプレビュー・発熱スキル・チャレンジリンク（share.js）・
storage.js・survey.js・audio.js・撃破ジュース・負けた画・教えない導入。
