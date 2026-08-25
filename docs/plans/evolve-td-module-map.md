# 群変（evolve-td）モジュール地図（CP5時点）

実装者は、この地図＋自分が触るファイル＋設計/UX文書の該当節だけを読めば着手できることを目指す。

## config.js
全数値の一元定義。塔4種（TOWERS）、経済（ECONOMY, killReward。2026-08-18: killBase 5／killPerWave 0.8／
waveClearBonus 60＝Gate A難易度調整）、盤面（GRID, LANE_LENGTH）、遺伝子範囲（GENOME_RANGES, GENOME_BASE,
INITIAL_JITTER=0.3, INITIAL_LANE_NOISE=0.15, INITIAL_LANE_PREF=0.4, INITIAL_RESIST_SHARE=0.25,
LANE_SHARPNESS=3, hpBaseForWave, RESIST_HP_COST=0.85）、HP_CURVE（base20/slope5。2026-08-18: 8→5）、
個体数式（POPULATION, populationSizeForWave）、色/形状符号（RESIST_COLORS, RESIST_MARKER_SHAPES,
TOWER_COLORS, TOWER_SHAPES）、解禁ウェーブ（UNLOCK_WAVES）、塔アップグレード（UPGRADE:
costMul=[0.8,1.2]／dmgMul=1.4／rangeAdd=0.3／maxLevel=3。2026-08-18 CP5: Gate B対応）、
進化パラメータ（EVOLUTION、DIFF_THRESHOLDS）、表示名（RESIST_LABELS, LANE_LABELS）、
スキル（SKILL: 発熱 CD30s・0.5・cold耐性0.75・3.0s）、ウェーブ数（WAVE_COUNT=15）、到達被害、
属性一致ダメージ倍率（RESIST_DAMAGE_MULT=0.5）、撃破ジュース・UI演出数値（JUICE）。
公開: 全て名前付きexport（関数以外は定数オブジェクト）。

## rng.js
- `makeRng(seed): rngFn` — mulberry32。`rngFn()`→[0,1)、`rngFn.int(n)`、`rngFn.pick(arr)`、`rngFn.normal(mean, sd)`。

## evolution.js（純粋関数・DOM非依存、乱数は引数で注入）
- `initialPopulation(n, rng): genome[]` — speed/hp/size±30%、resist 25%が1〜3、lane=好みのレーン1つ。
- `evaluate(results): number[]` — `progress + (reachedBase?1:0) + damageDealtToBase*0.25`。
- `evolve(population, fitness, ctx, rng): genome[]` — 上位20%親、一様交叉、突然変異
  p=0.14*(1+(1-towerDiversity))、多様性保険10%。`ctx = {wave, towerDiversity, nextSize}`。
- `summarize(population): {speedMean, hpMean, sizeMean, resistShare[4], laneShare[3]}` —
  laneShareはCP5のプレビュー・レーン分布バー（main.js `renderPreview`）が直接参照する。
- `diffReport(prevSummary, nextSummary): string[]` — 最大3行。
- `representative(population, summary): genome`。

## game-state.js
GameState: `{seed, gold, lives, wave, phase:'place'|'wave'|'report', towers:[{id,col,row,level}],
population, prevSummary, lastSummary, unlocked, waveDiversity, cleared, endless, bestWave, skillReadyAt}`。
塔インスタンスは2026-08-18(CP5)から `level`(1〜3)を持つ。`placeTower`は`level:1`で生成。
- `startNewGame/canPlace/placeTower/sellTower/startWave/skillUnlocked/useSkill/loseLives/
  endWave/closeReport/continueEndless/isCleared/isGameOver/unlockedTowers`（CP1〜3から凍結、詳細は
  過去版の本ファイルまたはコード参照）。
- `upgradeCost(tower): number`（CP5）— `TOWERS[tower.id].cost * UPGRADE.costMul[tower.level-1]`
  を四捨五入（Lv1→2はcostMul[0]、Lv2→3はcostMul[1]。いずれも初期費用基準・累積ではない）。
- `canUpgrade(state,col,row): boolean`（CP5）— 塔なし／Lv3(maxLevel)／資金不足でfalse。
- `upgradeTower(state,col,row): GameState`（CP5）— canUpgrade=falseなら状態不変。gold減・level+1。
- `towerInvested(tower): number`（CP5）— 初期費用＋支払った強化費用の合計（levelから再計算する
  純粋関数。個別の支払額は保持しない）。`sellTower`の返金額＝`towerInvested×ECONOMY.sellRatio`（切り捨て、
  CP1〜3の「初期費用×0.7」から一般化）。

## enemies.js
Enemy: `{genome, lane(0-2), x, hp, maxHp, spawnAt, realSpeed, slowUntil, slowFactor, alive, reached}`。
- `spawnFromPopulation/livesLostFor/applyHeatToLane/stepEnemies/collectResults/applySlow/
  pickGameOverRepresentative`（CP1〜3から凍結。実HP＝hpBaseForWave×hp×size×耐性コスト）。

## towers.js
- `stepTowers(towerInstances, enemies, dt, laneRows, now=0): shots[]` — 索敵「射程内で最も臓器に近い
  個体」。2026-08-18(CP5): `tower.level`（未設定はLv1扱い）に応じ、ダメージは`def.damage*dmgMul^(level-1)`、
  射程は`def.range+rangeAdd*(level-1)`で効く（内部の`effectiveDamage/effectiveRange`、非export）。
  heatは着弾点半径0.8セル全個体（レベル反映後のダメージで）、coldは`applySlow`呼び出し。
  `towerInstances`要素へ`cooldown`を破壊的に付与。shots: `{x1,y1,x2,y2,towerId,ttl}`。

## renderer.js（DOM/Canvas依存）
- `render(ctx, {towers, enemies, shots, rangePreview, laneSelectAlpha?, laneFlash?, particles?,
  goldPopups?}): void` — 論理解像度576×384。
- `renderGenomeIcon/renderGenomeGroup(ctx, genome(s), size…): void` — genome静止描画（プレビュー・
  レポート・負けた画・CP5あそびかた凡例で共用）。
- `drawTowerIcon(ctx, towerId, size): void` — パレット用アイコン（levelなし＝常にLv1見た目）。
- 塔描画（`drawTower`内部）: 外周形状（basic正円／heat棘6本／cold六角枠／bolt ジグザグ）は既存のまま、
  2026-08-18(CP5)から中心図形を`tower.level`数だけ同心円で描く（Lv1=1重／Lv2=2重／Lv3=3重）。
  `LOGICAL_WIDTH/LOGICAL_HEIGHT` — 576/384。

## share.js / storage.js / survey.js / audio.js
CP3までで凍結、CP5での変更なし。`share.js`: `encodeChallenge/decodeChallenge`。`storage.js`:
`evolveTd.`接頭辞、bestWave/survey/challengeReceived/seenIntro/sessions/wave2Started、例外を投げない。
`survey.js`: `initSurvey/resetSurveyScreen`。`audio.js`: `initAudio/playPlace/playKill/playHit/
playWaveStart/setMuted/isMuted`（合成のみ、外部音声なし）。

## main.js（DOM依存、エントリーポイント）
画面遷移 title→playing→result→survey→title。CP1〜3: 配置/ウェーブ/変異レポートmodal/次ウェーブ
プレビュー/発熱/チャレンジリンク/アンケート/撃破ジュース/負けた画/教えない導入（詳細は過去版参照）。
CP5追加分:
- 配置済み塔タップの`#tower-panel`が「強化{upgradeCost}G」「売る{towerInvested×0.7切捨}G」の2ボタンに
  （Lv3は強化ボタンhidden、資金不足はdisabled）。`showTowerPanelFor(col,row)`が動的に金額・可否を再計算。
  `handleUpgrade()`→`upgradeTower`→パネル再表示。PC: 塔選択中（パネル表示中）`U`キーで強化。
- `#preview-panel`に`summarize(population).laneShare`から「上/中央/下 ▮…(10段階) NN%」の3行
  （`renderPreview()`内、既存の5体アイコンは維持）。
- `#howto-modal`（あそびかた）: タイトルの`#howto-button`／HUDの`#howto-hud-button`（配置フェーズのみ
  活性、`updateHud()`で`state.phase!=='place'`ならdisabled）で開く。凡例は`renderHowtoLegend()`が
  `GENOME_RANGES`の代表値genomeを`renderGenomeIcon`で描画（fast/tough/big/heat/cold/bolt）。
