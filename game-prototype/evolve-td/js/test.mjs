// test.mjs
// Node.js単体で実行できるロジックテスト。
// DOM操作を含むrenderer.js/main.jsは構文チェックのみ（SyntaxErrorのみ失敗扱い）。
// 実行: node js/test.mjs

import * as Config from './config.js';
import { makeRng } from './rng.js';
import * as GameState from './game-state.js';
import * as Towers from './towers.js';
import * as Enemies from './enemies.js';
import * as Evolution from './evolution.js';

let count = 0;
let failed = 0;

function check(label, condition) {
  count++;
  if (condition) {
    console.log(`PASS: ${label}`);
  } else {
    console.log(`FAIL: ${label}`);
    failed++;
  }
}

// --- モジュール読み込みスモーク ---
console.log('--- module load smoke ---');
check('config.jsが読み込める', typeof Config.TOWERS === 'object');
check('rng.jsが読み込める', typeof makeRng === 'function');
check('game-state.jsが読み込める', typeof GameState.startNewGame === 'function');
check('towers.jsが読み込める', typeof Towers.stepTowers === 'function');
check('enemies.jsが読み込める', typeof Enemies.spawnFromPopulation === 'function');
check('evolution.jsが読み込める', typeof Evolution.initialPopulation === 'function');

// renderer.js / main.js はDOM依存のため構文チェックのみ（SyntaxErrorのみ失敗）
console.log('--- renderer.js / main.js 構文チェック（DOM参照エラーは許容） ---');
try {
  await import('./renderer.js');
  check('renderer.jsのimportがSyntaxErrorを起こさない', true);
} catch (e) {
  const isSyntaxError = e instanceof SyntaxError;
  check(`renderer.jsのimportがSyntaxErrorを起こさない（発生時: ${e.constructor.name}: ${e.message}）`, !isSyntaxError);
}
try {
  await import('./main.js');
  check('main.jsのimportがSyntaxErrorを起こさない', true);
} catch (e) {
  const isSyntaxError = e instanceof SyntaxError;
  check(`main.jsのimportがSyntaxErrorを起こさない（発生時: ${e.constructor.name}: ${e.message}）`, !isSyntaxError);
}

// --- rng.js ---
console.log('--- rng.js ---');
{
  const rngA = makeRng(12345);
  const rngB = makeRng(12345);
  const seqA = [rngA(), rngA(), rngA()];
  const seqB = [rngB(), rngB(), rngB()];
  check('同じseedなら同じ乱数列を返す', JSON.stringify(seqA) === JSON.stringify(seqB));

  const rngC = makeRng(999);
  const seqC = [rngC(), rngC(), rngC()];
  check('異なるseedなら異なる乱数列を返す', JSON.stringify(seqA) !== JSON.stringify(seqC));

  const rngD = makeRng(1);
  check('rng()は[0,1)の範囲', Array.from({ length: 1000 }, () => rngD()).every((v) => v >= 0 && v < 1));

  const rngE = makeRng(2);
  check('rng.intは指定範囲未満の整数', Array.from({ length: 500 }, () => rngE.int(7)).every((v) => Number.isInteger(v) && v >= 0 && v < 7));
}

// --- evolution.js ---
console.log('--- evolution.js ---');
{
  const rng = makeRng(42);
  const pop = Evolution.initialPopulation(50, rng);
  check(
    'initialPopulationの全個体でspeedが範囲内',
    pop.every((g) => g.speed >= Config.GENOME_RANGES.speed[0] && g.speed <= Config.GENOME_RANGES.speed[1])
  );
  check(
    'initialPopulationの全個体でhpが範囲内',
    pop.every((g) => g.hp >= Config.GENOME_RANGES.hp[0] && g.hp <= Config.GENOME_RANGES.hp[1])
  );
  check(
    'initialPopulationの全個体でsizeが範囲内',
    pop.every((g) => g.size >= Config.GENOME_RANGES.size[0] && g.size <= Config.GENOME_RANGES.size[1])
  );
  check('initialPopulationの全個体でresist=0', pop.every((g) => g.resist === 0));
  // 2026-08-16 team-lead判断: laneは均等固定[1/3,1/3,1/3]から「均等(1/3)に±0.15の
  // 一様ノイズを加え再正規化」に変更（CP2知覚テスト⑥でW1からのレーン適応が
  // 検出できるようにするため）。よって「厳密に1/3」ではなく「合計1・各要素≥0」を検証する
  check(
    'initialPopulationのlaneは合計1・各要素0以上（均等±0.15ノイズ後に再正規化）',
    pop.every((g) => g.lane.every((w) => w >= 0) && Math.abs(g.lane.reduce((a, b) => a + b, 0) - 1) < 1e-9)
  );

  const results = [
    { progress: 1.0, reachedBase: true, damageDealtToBase: 2 },
    { progress: 0.5, reachedBase: false, damageDealtToBase: 0 },
    { progress: 0.0, reachedBase: false, damageDealtToBase: 0 },
  ];
  const fitness = Evolution.evaluate(results);
  check('evaluateの式: 到達+被害あり', Math.abs(fitness[0] - (1.0 + 1.0 + 2 * 0.25)) < 1e-9);
  check('evaluateの式: 未到達progress0.5', Math.abs(fitness[1] - 0.5) < 1e-9);
  check('evaluateの式: 未到達progress0', Math.abs(fitness[2] - 0) < 1e-9);

  const summary = Evolution.summarize(pop);
  const resistShareSum = summary.resistShare.reduce((a, b) => a + b, 0);
  const laneShareSum = summary.laneShare.reduce((a, b) => a + b, 0);
  check('summarizeのresistShare合計が1', Math.abs(resistShareSum - 1) < 1e-9);
  check('summarizeのlaneShare合計が1', Math.abs(laneShareSum - 1) < 1e-9);

  // CP2: evolveは本実装。nextSize件を返し、全遺伝子が範囲内であること
  const nextPop = Evolution.evolve(pop, fitness.concat(Array(47).fill(0)), { wave: 1, towerDiversity: 0.25, nextSize: 24 }, rng);
  check(
    'evolveがnextSize件を返し全遺伝子が範囲内',
    nextPop.length === 24 &&
      nextPop.every(
        (g) =>
          g.speed >= Config.GENOME_RANGES.speed[0] && g.speed <= Config.GENOME_RANGES.speed[1] &&
          g.hp >= Config.GENOME_RANGES.hp[0] && g.hp <= Config.GENOME_RANGES.hp[1] &&
          g.size >= Config.GENOME_RANGES.size[0] && g.size <= Config.GENOME_RANGES.size[1] &&
          Number.isInteger(g.resist) && g.resist >= 0 && g.resist <= 3
      )
  );

  // CP2: diffReportは本実装。変化なし（同一summary同士）なら定型1行を返す
  const noChangeReport = Evolution.diffReport(summary, summary);
  check(
    'diffReportは変化なしで定型1行「群れに目立った変化はない」を返す',
    Array.isArray(noChangeReport) && noChangeReport.length === 1 && noChangeReport[0] === '群れに目立った変化はない'
  );
}

// --- enemies.js ---
console.log('--- enemies.js ---');
{
  const laneLength = Config.LANE_LENGTH;
  const reachedEnemy = { genome: { size: 1.5 }, x: laneLength, reached: true, alive: false };
  const killedEnemy = { genome: { size: 1.0 }, x: 6, reached: false, alive: false };
  const aliveEnemy = { genome: { size: 1.0 }, x: 3, reached: false, alive: true };
  const results = Enemies.collectResults([reachedEnemy, killedEnemy, aliveEnemy], laneLength);
  check('collectResults: 到達個体はreachedBase=true・progress=1', results[0].reachedBase === true && Math.abs(results[0].progress - 1) < 1e-9);
  check('collectResults: 到達個体でsize>=1.2は被害2', results[0].damageDealtToBase === 2);
  check('collectResults: 未到達個体はreachedBase=false・被害0', results[1].reachedBase === false && results[1].damageDealtToBase === 0);
  check('collectResults: progressがx/laneLength', Math.abs(results[2].progress - 3 / laneLength) < 1e-9);

  // livesLostFor境界値
  check('livesLostFor: size=1.19は1', Enemies.livesLostFor({ size: 1.19 }) === 1);
  check('livesLostFor: size=1.2は2', Enemies.livesLostFor({ size: 1.2 }) === 2);

  // applySlowの強弱規則
  const e1 = { slowUntil: 0, slowFactor: 1 };
  Enemies.applySlow(e1, 0.6, 1.5, 10); // 未適用状態から適用
  check('applySlow: 未適用状態から適用される', e1.slowFactor === 0.6 && Math.abs(e1.slowUntil - 11.5) < 1e-9);

  const e2 = { slowUntil: 11.5, slowFactor: 0.6 };
  Enemies.applySlow(e2, 0.5, 3.0, 10.5); // より強い(factor小)効果 → 置換
  check('applySlow: より強い効果は置換される', e2.slowFactor === 0.5 && Math.abs(e2.slowUntil - 13.5) < 1e-9);

  const e3 = { slowUntil: 11.5, slowFactor: 0.6 };
  Enemies.applySlow(e3, 0.8, 1.0, 10.5); // より弱い(factor大)効果 → 無視
  check('applySlow: より弱い効果は無視される', e3.slowFactor === 0.6 && Math.abs(e3.slowUntil - 11.5) < 1e-9);

  const e4 = { slowUntil: 11.5, slowFactor: 0.6 };
  Enemies.applySlow(e4, 0.6, 2.0, 10.5); // 同じ強さ → until延長
  check('applySlow: 同じ強さはuntilが延長される（Math.max）', e4.slowFactor === 0.6 && Math.abs(e4.slowUntil - 12.5) < 1e-9);

  // 出現・移動
  const rng = makeRng(7);
  const genomes = Evolution.initialPopulation(3, rng);
  const spawned = Enemies.spawnFromPopulation(genomes, 1, rng);
  check('spawnFromPopulationは個体数分のEnemyを返す', spawned.length === 3);
  check('spawnFromPopulationの初期xは-1', spawned.every((en) => en.x === -1));
  check(
    'spawnFromPopulationのspawnAtは0.4秒間隔',
    spawned.every((en, i) => Math.abs(en.spawnAt - i * Config.POPULATION.spawnInterval) < 1e-9)
  );

  const moveEnemies = [{ genome: genomes[0], x: -1, spawnAt: 0, realSpeed: 1, slowUntil: 0, slowFactor: 1, alive: true, reached: false, lane: 0 }];
  Enemies.stepEnemies(moveEnemies, 1, laneLength, 0);
  check('stepEnemies: spawnAt<=0の個体はdt分移動する', Math.abs(moveEnemies[0].x - 0) < 1e-9);

  const reachEnemies = [{ genome: genomes[0], x: laneLength - 0.5, spawnAt: 0, realSpeed: 1, slowUntil: 0, slowFactor: 1, alive: true, reached: false, lane: 0 }];
  Enemies.stepEnemies(reachEnemies, 1, laneLength, 0);
  check('stepEnemies: laneLengthに到達するとreached=true・alive=false', reachEnemies[0].reached === true && reachEnemies[0].alive === false);
}

// --- towers.js ---
console.log('--- towers.js ---');
{
  // basic（属性なし）はresist=0個体にフルダメージを与える
  const basicTower = { id: 'basic', col: 0, row: 0 };
  const basicVsNoResist = { alive: true, spawnAt: 0, x: 0.5, lane: 0, hp: 100, genome: { resist: 0 } };
  Towers.stepTowers([basicTower], [basicVsNoResist], 0.016, [0], 0);
  check(
    'basicがresist=0個体にフルダメージを与える',
    Math.abs(basicVsNoResist.hp - (100 - Config.TOWERS.basic.damage)) < 1e-9
  );

  // heat（属性heat）はresist=1（heat耐性）個体に半減ダメージ
  const heatTowerA = { id: 'heat', col: 0, row: 0 };
  const heatVsHeatResist = { alive: true, spawnAt: 0, x: 0.5, lane: 0, hp: 100, genome: { resist: 1 } };
  Towers.stepTowers([heatTowerA], [heatVsHeatResist], 0.016, [0], 0);
  check(
    'heatがresist=1個体に半減ダメージを与える',
    Math.abs(heatVsHeatResist.hp - (100 - Config.TOWERS.heat.damage * 0.5)) < 1e-9
  );

  // heat（属性heat）はresist=0（無耐性）個体にフルダメージ
  const heatTowerB = { id: 'heat', col: 0, row: 0 };
  const heatVsNoResist = { alive: true, spawnAt: 0, x: 0.5, lane: 0, hp: 100, genome: { resist: 0 } };
  Towers.stepTowers([heatTowerB], [heatVsNoResist], 0.016, [0], 0);
  check(
    'heatがresist=0個体にフルダメージを与える',
    Math.abs(heatVsNoResist.hp - (100 - Config.TOWERS.heat.damage)) < 1e-9
  );
}

// --- game-state.js ---
console.log('--- game-state.js ---');
{
  const state0 = GameState.startNewGame({ seed: 1, gold: 300 });
  check('startNewGameのphaseはplace', state0.phase === 'place');
  check('startNewGameのwaveは1', state0.wave === 1);
  check('startNewGameのunlockedはbasicのみ', JSON.stringify(state0.unlocked) === JSON.stringify(['basic']));
  check('startNewGameのpopulationは初期サイズ22', state0.population.length === Config.POPULATION.initialSize);

  // unlockedTowers
  check('unlockedTowers(1)はbasicのみ', JSON.stringify(GameState.unlockedTowers(1)) === JSON.stringify(['basic']));
  check('unlockedTowers(3)はbasic+heat', JSON.stringify(GameState.unlockedTowers(3)) === JSON.stringify(['basic', 'heat']));
  check('unlockedTowers(5)はbasic+heat+cold', JSON.stringify(GameState.unlockedTowers(5)) === JSON.stringify(['basic', 'heat', 'cold']));
  check('unlockedTowers(7)は4種累積', JSON.stringify(GameState.unlockedTowers(7)) === JSON.stringify(['basic', 'heat', 'cold', 'bolt']));

  // canPlace: レーン判定
  check('canPlace: レーン行(row=1)には置けない', GameState.canPlace(state0, 'basic', 0, 1) === false);
  check('canPlace: 非レーン行には置ける', GameState.canPlace(state0, 'basic', 0, 0) === true);
  check('canPlace: 未解禁の塔は置けない', GameState.canPlace(state0, 'heat', 0, 0) === false);

  // placeTower: 資金増減
  const afterPlace = GameState.placeTower(state0, 'basic', 0, 0);
  check('placeTowerで資金がcost分減る', afterPlace.gold === 300 - Config.TOWERS.basic.cost);
  check('placeTowerでtowersに追加される', afterPlace.towers.length === 1);

  // canPlace: 重複判定
  check('canPlace: 既に塔がある場所には置けない', GameState.canPlace(afterPlace, 'basic', 0, 0) === false);

  // 資金不足
  const poorState = { ...state0, gold: 10 };
  check('canPlace: 資金不足では置けない', GameState.canPlace(poorState, 'basic', 0, 0) === false);

  // sellTower: 資金増減
  const afterSell = GameState.sellTower(afterPlace, 0, 0);
  const expectedRefund = Math.floor(Config.TOWERS.basic.cost * Config.ECONOMY.sellRatio);
  check('sellTowerで資金が70%分戻る', afterSell.gold === afterPlace.gold + expectedRefund);
  check('sellTowerでtowersから消える', afterSell.towers.length === 0);
  check('sellTower: 存在しない塔は状態を変えない', GameState.sellTower(state0, 5, 0) === state0);

  // waveDiversityスナップショット
  const placedTwoKinds = GameState.placeTower(
    GameState.placeTower(state0, 'basic', 0, 0),
    'basic',
    0,
    2
  );
  const startedWave = GameState.startWave(placedTwoKinds);
  check('startWaveでwaveDiversityがスナップショットされる（basicのみ=1/4）', Math.abs(startedWave.waveDiversity - 1 / 4) < 1e-9);
  check('startWaveでphaseがwaveになる', startedWave.phase === 'wave');

  // ウェーブ中に塔を売っても直近のwaveDiversityは変わらない（スナップショット済み）
  const soldDuringWave = GameState.sellTower(startedWave, 0, 0);
  check('ウェーブ中の売却でwaveDiversityは変化しない', soldDuringWave.waveDiversity === startedWave.waveDiversity);

  // loseLives / isGameOver
  const damaged = GameState.loseLives(state0, 5);
  check('loseLivesでlivesが減る', damaged.lives === Config.LIVES_START - 5);
  check('isGameOver: lives>0はfalse', GameState.isGameOver(damaged) === false);
  const dead = GameState.loseLives(state0, 999);
  check('loseLivesは0未満にならない', dead.lives === 0);
  check('isGameOver: lives=0はtrue', GameState.isGameOver(dead) === true);

  // endWave → closeReport: wave規則
  const rngForEnd = makeRng(3);
  const dummyResults = state0.population.map(() => ({ progress: 0.5, reachedBase: false, damageDealtToBase: 0 }));
  const { state: reportState, report } = GameState.endWave(startedWave, dummyResults, rngForEnd);
  check('endWave後のphaseはreport', reportState.phase === 'report');
  check('endWaveはwaveを変えない（closeReportで進める）', reportState.wave === state0.wave);
  check('endWaveのreportは配列', Array.isArray(report));
  check(
    'endWaveでgoldがECONOMY.waveClearBonus分増える',
    reportState.gold === startedWave.gold + Config.ECONOMY.waveClearBonus
  );
  const closed = GameState.closeReport(reportState);
  check('closeReportでwaveが+1される', closed.wave === state0.wave + 1);
  check('closeReportでphaseがplaceに戻る', closed.phase === 'place');

  // W15クリア判定
  const wave15State = { ...state0, wave: 15, phase: 'wave' };
  const { state: clearedState } = GameState.endWave(wave15State, dummyResults, makeRng(9));
  check('wave15のendWaveでcleared=true', clearedState.cleared === true);
  check('isCleared(cleared状態)はtrue', GameState.isCleared(clearedState) === true);

  // エンドレス
  const endlessState = GameState.continueEndless(clearedState);
  check('continueEndlessでendless=trueかつcleared解除', endlessState.endless === true && endlessState.cleared === false);
  const endlessClosed = GameState.closeReport(endlessState);
  check('continueEndless後のcloseReportでwaveが進む', endlessClosed.wave === 16);
}

// --- evolution.js（CP2: evolve/diffReport本実装の検証） ---
console.log('--- evolution.js (CP2) ---');
{
  // ①上位個体の形質が次世代平均に寄る
  {
    const rng = makeRng(11);
    const n = 40;
    const pop = [];
    for (let i = 0; i < n; i++) {
      const highFit = i < n / 2;
      pop.push({ speed: highFit ? 1.9 : 0.7, hp: 1.0, resist: 0, lane: [1 / 3, 1 / 3, 1 / 3], size: 1.0 });
    }
    const fitness = pop.map((_, i) => (i < n / 2 ? 5 : 0.1));
    const overallMean = pop.reduce((s, g) => s + g.speed, 0) / n;
    const eliteMean = 1.9;
    const next = Evolution.evolve(pop, fitness, { wave: 1, towerDiversity: 1, nextSize: 60 }, rng);
    const nextMean = next.reduce((s, g) => s + g.speed, 0) / next.length;
    check(
      '①上位個体(高fitness)の形質(speed)が次世代平均に寄る',
      Math.abs(nextMean - eliteMean) < Math.abs(nextMean - overallMean)
    );
  }

  // ②突然変異率がtowerDiversityに依存する
  {
    const makeHomogeneousPop = (n) =>
      Array.from({ length: n }, () => ({ speed: 1.0, hp: 1.0, resist: 0, lane: [1 / 3, 1 / 3, 1 / 3], size: 1.0 }));
    const n = 200;
    const fitness = Array(n).fill(1);
    const variance = (arr) => {
      const mean = arr.reduce((s, v) => s + v, 0) / arr.length;
      return arr.reduce((s, v) => s + (v - mean) ** 2, 0) / arr.length;
    };
    const rngHighMutation = makeRng(55);
    const nextHighMutation = Evolution.evolve(
      makeHomogeneousPop(n),
      fitness,
      { wave: 1, towerDiversity: 0, nextSize: n },
      rngHighMutation
    ); // p = 0.08*(1+1) = 0.16
    const rngLowMutation = makeRng(55);
    const nextLowMutation = Evolution.evolve(
      makeHomogeneousPop(n),
      fitness,
      { wave: 1, towerDiversity: 1, nextSize: n },
      rngLowMutation
    ); // p = 0.08*(1+0) = 0.08
    const varHigh = variance(nextHighMutation.map((g) => g.speed));
    const varLow = variance(nextLowMutation.map((g) => g.speed));
    check(
      '②towerDiversity=0(高突然変異率)の方がtowerDiversity=1より子集団の変化(分散)が大きい',
      varHigh > varLow
    );
  }

  // ③全遺伝子が範囲内
  {
    for (const seed of [1, 2, 3]) {
      const rng = makeRng(seed);
      const pop = Evolution.initialPopulation(30, rng);
      const fitness = pop.map(() => rng());
      const next = Evolution.evolve(pop, fitness, { wave: 5, towerDiversity: 0.5, nextSize: 40 }, rng);
      const allInRange = next.every(
        (g) =>
          g.speed >= Config.GENOME_RANGES.speed[0] && g.speed <= Config.GENOME_RANGES.speed[1] &&
          g.hp >= Config.GENOME_RANGES.hp[0] && g.hp <= Config.GENOME_RANGES.hp[1] &&
          g.size >= Config.GENOME_RANGES.size[0] && g.size <= Config.GENOME_RANGES.size[1] &&
          Number.isInteger(g.resist) && g.resist >= 0 && g.resist <= 3 &&
          g.lane.every((w) => w >= 0) &&
          Math.abs(g.lane.reduce((a, b) => a + b, 0) - 1) < 1e-6
      );
      check(`③evolve(seed=${seed})の全遺伝子が範囲内`, allInRange);
    }
  }

  // ④diffReportが閾値未満を省き、全省略時は定型1行
  {
    const flatSummary = { speedMean: 1.0, hpMean: 1.0, sizeMean: 1.0, resistShare: [1, 0, 0, 0], laneShare: [1 / 3, 1 / 3, 1 / 3] };
    const noChange = Evolution.diffReport(flatSummary, flatSummary);
    check('④変化なしで定型1行「群れに目立った変化はない」', noChange.length === 1 && noChange[0] === '群れに目立った変化はない');

    const changed = { speedMean: 1.3, hpMean: 1.0, sizeMean: 1.0, resistShare: [0.6, 0, 0, 0.4], laneShare: [1 / 3, 1 / 3, 1 / 3] };
    const report = Evolution.diffReport(flatSummary, changed);
    check('④閾値以上の変化(speed+boltresist)のみ含まれる', report.length === 2);
    check('④閾値未満のhp/size/laneは省かれる', !report.some((l) => l.includes('体格') || l.includes('レーン')));

    const manyChanges = {
      speedMean: 1.5,
      hpMean: 1.5,
      sizeMean: 1.3,
      resistShare: [0.1, 0.3, 0.3, 0.3],
      laneShare: [0.6, 0.2, 0.2],
    };
    const bigReport = Evolution.diffReport(flatSummary, manyChanges);
    check('④最大3行まで（多数の変化があっても超えない）', bigReport.length <= 3);
  }

  // ⑤同seedで同じ子集団
  {
    const basePopRng = makeRng(999);
    const basePop = Evolution.initialPopulation(25, basePopRng);
    const fitness = basePop.map((g, i) => i % 4);
    const ctx = { wave: 4, towerDiversity: 0.5, nextSize: 30 };
    for (const seed of [1, 2, 3, 4, 5]) {
      const rngA = makeRng(seed);
      const nextA = Evolution.evolve(basePop, fitness, ctx, rngA);
      const rngB = makeRng(seed);
      const nextB = Evolution.evolve(basePop, fitness, ctx, rngB);
      check(`⑤seed=${seed}: 同じpopulation/fitness/ctxなら同じ子集団(JSON一致)`, JSON.stringify(nextA) === JSON.stringify(nextB));
    }
  }

  // ⑥知覚テスト: 「標準的な開き」(W1に好中球2本を上レーン付近、上レーンはprogress0.3〜0.5でブロック、
  // 中/下レーンはreachedでprogress1.0)のresultsからendWave相当を回したとき、
  // W1→W2のdiffReportが1行以上の実質変化を含む（seed5種で全て）
  console.log('--- ⑥知覚テスト（実測値） ---');
  {
    let allPass = true;
    for (const seed of [1, 2, 3, 4, 5]) {
      let s = GameState.startNewGame({ seed, gold: 300 });
      // 好中球2本を上レーン付近に配置した想定でwaveDiversityをスナップショット
      s = { ...s, towers: [{ id: 'basic', col: 2, row: 0 }, { id: 'basic', col: 4, row: 0 }] };
      s = GameState.startWave(s);
      const [minSpeed, maxSpeed] = Config.GENOME_RANGES.speed;
      const results = s.population.map((g, i) => {
        const isTopLane = i % 3 === 0; // 概ね1/3を上レーン(防御あり)想定
        if (isTopLane) {
          // 速い個体ほど被弾前に進む距離が伸びる、という標準的な開きを模す
          const t = (g.speed - minSpeed) / (maxSpeed - minSpeed);
          return { progress: 0.3 + t * 0.2, reachedBase: false, damageDealtToBase: 0 };
        }
        // 中/下レーンは無防備で到達。到達個体同士の被害は体格に応じて変わる、という想定
        return { progress: 1.0, reachedBase: true, damageDealtToBase: g.size };
      });
      const rngEnd = makeRng(seed * 1000 + 1);
      const { state: afterState, report } = GameState.endWave(s, results, rngEnd);
      const hasRealChange = report.length >= 1 && report[0] !== '群れに目立った変化はない';
      console.log(`  seed=${seed}: report=${JSON.stringify(report)}`);
      check(`⑥知覚テスト seed=${seed}: W1→W2のdiffReportが実質変化を含む`, hasRealChange);
      if (!hasRealChange) allPass = false;
    }
    if (!allPass) {
      console.log('⑥知覚テストが一部seedで未達。設計側の判断が必要（数値・初期集団は変更していない）。');
    }
  }

  // ⑦理不尽化テスト: 塔種類数1(towerDiversity=0.25)・全個体progress = 一様乱数×(resist===0?1:0.85)
  // （耐性コストを fitness に反映した代理指標。純粋な選択圧ゼロではGAは必ずどこかに固着するため、
  // 実ゲームの構造に合わせた。plan の確定回答参照）のresultsで15世代回し、
  // speedMean/hpMeanがクランプ上限の95%に張り付かず、単一resistの割合が70%を超えない
  console.log('--- ⑦理不尽化テスト（実測値） ---');
  {
    let allPass = true;
    for (const seed of [1, 2, 3, 4, 5]) {
      const rng = makeRng(seed);
      let population = Evolution.initialPopulation(22, rng);
      let wave = 1;
      for (let g = 0; g < 15; g++) {
        const results = population.map((genome) => {
          const progress = rng() * (genome.resist === 0 ? 1 : Config.RESIST_HP_COST);
          return { progress, reachedBase: progress >= 1, damageDealtToBase: 0 };
        });
        const fitness = Evolution.evaluate(results);
        const nextSize = Math.min(50, 20 + (wave + 1) * 2);
        population = Evolution.evolve(population, fitness, { wave, towerDiversity: 0.25, nextSize }, rng);
        wave++;
      }
      const summary = Evolution.summarize(population);
      const speedCap = Config.GENOME_RANGES.speed[1];
      const hpCap = Config.GENOME_RANGES.hp[1];
      // 判定対象は「耐性あり（1〜3）」の単一属性への集中。resist=0（なし）が多数派なのは正常
      const maxResistShare = Math.max(...summary.resistShare.slice(1));
      console.log(
        `  seed=${seed}: speedMean=${summary.speedMean.toFixed(3)}(cap${speedCap}) hpMean=${summary.hpMean.toFixed(3)}(cap${hpCap}) resistShare=[${summary.resistShare.map((v) => v.toFixed(2)).join(',')}] maxResist(1-3)=${maxResistShare.toFixed(3)}`
      );
      const speedOk = summary.speedMean < speedCap * 0.95;
      const hpOk = summary.hpMean < hpCap * 0.95;
      const resistOk = maxResistShare <= 0.7;
      check(`⑦seed=${seed}: speedMeanが上限95%未満`, speedOk);
      check(`⑦seed=${seed}: hpMeanが上限95%未満`, hpOk);
      check(`⑦seed=${seed}: 単一resistの割合が70%以下`, resistOk);
      if (!speedOk || !hpOk || !resistOk) allPass = false;
    }
    if (!allPass) {
      console.log('⑦理不尽化テストが一部seedで未達。設計側の判断が必要（数値・初期集団は変更していない）。');
    }
  }

  // ⑧追随テスト: 対応する塔がある（heat 塔主力＝heat耐性個体は多くが到達）状況では heat 耐性が増える（回帰ガード）
  {
    for (const seed of [1, 2, 3]) {
      const rng = makeRng(seed);
      let population = Evolution.initialPopulation(22, rng);
      let wave = 1;
      for (let g = 0; g < 12; g++) {
        const results = population.map((genome) => {
          // heat 塔が主力の盤面の代理: heat 耐性個体は被ダメ半減で多くが到達（0.7〜1.2）、それ以外は途中で落ちがち（0〜0.8、耐性コスト分さらに低い）
          const progress = genome.resist === 1 ? 0.7 + rng() * 0.5 : rng() * 0.8 * (genome.resist === 0 ? 1 : 0.85);
          return { progress, reachedBase: progress >= 1, damageDealtToBase: 0 };
        });
        const fitness = Evolution.evaluate(results);
        const nextSize = Math.min(50, 20 + (wave + 1) * 2);
        population = Evolution.evolve(population, fitness, { wave, towerDiversity: 0.25, nextSize }, rng);
        wave++;
      }
      const share = Evolution.summarize(population).resistShare;
      console.log(`  ⑧seed=${seed}: resistShare=[${share.map((v) => v.toFixed(2)).join(',')}]`);
      check(`⑧seed=${seed}: heat耐性が有利なら12世代で heat 耐性が 25% 以上に増える`, share[1] >= 0.25);
    }
  }

  // diffReport のソフト行と shareMinAfter
  {
    const base = { speedMean: 1, hpMean: 1, sizeMean: 1, resistShare: [1, 0, 0, 0], laneShare: [1 / 3, 1 / 3, 1 / 3] };
    const soft = Evolution.diffReport(base, { ...base, speedMean: 1.02 });
    check('diffReport: 全項目閾値未満なら最大変化を「わずかに」1行', soft.length === 1 && soft[0].startsWith('わずかに速く'));
    const noisy = Evolution.diffReport({ ...base, resistShare: [0.96, 0, 0, 0.04] }, { ...base, resistShare: [0.88, 0, 0, 0.12] });
    check('diffReport: 耐性8pt増でも変化後15%未満なら本行にしない（ソフト行）', noisy.length === 1 && noisy[0].startsWith('わずかに抗体'));
    const real = Evolution.diffReport({ ...base, resistShare: [0.96, 0, 0, 0.04] }, { ...base, resistShare: [0.77, 0, 0, 0.23] });
    check('diffReport: 耐性4%→23%は本行', real[0] === '抗体への耐性を持つ個体が増えた（4%→23%）');
    const same = Evolution.diffReport(base, base);
    check('diffReport: 変化ゼロは定型1行', same.length === 1 && same[0] === '群れに目立った変化はない');
  }

  // 耐性コスト: resist!==0 の個体は maxHp が resist=0 の RESIST_HP_COST 倍
  {
    const rng = makeRng(7);
    const g0 = { speed: 1, hp: 1, resist: 0, lane: [1 / 3, 1 / 3, 1 / 3], size: 1 };
    const g1 = { ...g0, resist: 1 };
    const [e0, e1] = Enemies.spawnFromPopulation([g0, g1], 1, rng);
    check('耐性コスト: resist=1 の maxHp は resist=0 の 0.85 倍', Math.abs(e1.maxHp / e0.maxHp - Config.RESIST_HP_COST) < 1e-9);
  }

  // representative: 平均遺伝子への正規化距離が最小の個体を返す
  {
    const pop = [
      { speed: 1.0, hp: 1.0, resist: 0, lane: [1 / 3, 1 / 3, 1 / 3], size: 1.0 },
      { speed: 2.0, hp: 3.0, resist: 3, lane: [1, 0, 0], size: 1.5 },
      { speed: 0.6, hp: 0.6, resist: 1, lane: [0, 1, 0], size: 0.7 },
    ];
    const summary = Evolution.summarize(pop);
    const rep = Evolution.representative(pop, summary);
    check('representativeは平均遺伝子に最も近い個体を返す(この例ではpop[0])', rep === pop[0]);
  }
}

// --- game-state.js（CP2: 発熱スキル） ---
console.log('--- game-state.js (CP2: 発熱スキル) ---');
{
  const early = GameState.startNewGame({ seed: 1, gold: 300 });
  check('skillUnlocked: wave1は未解禁', GameState.skillUnlocked(early) === false);
  const wave3State = { ...early, wave: 3 };
  check('skillUnlocked: wave3は解禁済み', GameState.skillUnlocked(wave3State) === true);

  // startWaveでskillReadyAtが0にリセットされる
  const withReadyAt = { ...wave3State, skillReadyAt: 999 };
  const startedWave3 = GameState.startWave(withReadyAt);
  check('startWaveでskillReadyAtが0にリセットされる', startedWave3.skillReadyAt === 0);

  // useSkill: 未解禁では状態を変えない
  const earlyWave = GameState.startWave(early);
  const unchangedByLock = GameState.useSkill(earlyWave, 0, 5);
  check('useSkill: 未解禁(wave<3)では状態を変えない', unchangedByLock === earlyWave);

  // useSkill: wave3・phase=wave・CD0で発動しskillReadyAtが更新される
  const readyState = GameState.startWave({ ...wave3State, skillReadyAt: 0 });
  const afterUse = GameState.useSkill(readyState, 1, 10);
  check('useSkill: 条件を満たせばskillReadyAtがnow+cooldownになる', afterUse.skillReadyAt === 10 + Config.SKILL.cooldown);

  // useSkill: CD中は状態を変えない
  const onCooldown = { ...readyState, skillReadyAt: 20 };
  const unchangedByCooldown = GameState.useSkill(onCooldown, 1, 10);
  check('useSkill: CD中(now<skillReadyAt)では状態を変えない', unchangedByCooldown === onCooldown);

  // useSkill: phase!=='wave'では状態を変えない
  const placePhase = { ...readyState, phase: 'place' };
  const unchangedByPhase = GameState.useSkill(placePhase, 1, 10);
  check('useSkill: phase!=="wave"では状態を変えない', unchangedByPhase === placePhase);

  // useSkill: 不正なlaneでは状態を変えない
  const unchangedByLane = GameState.useSkill(readyState, 5, 10);
  check('useSkill: lane不正(0〜2以外)では状態を変えない', unchangedByLane === readyState);
}

// --- enemies.js（CP2: applyHeatToLane） ---
console.log('--- enemies.js (CP2: applyHeatToLane) ---');
{
  const laneEnemies = [
    { genome: { resist: 0 }, lane: 0, alive: true, spawnAt: 0, reached: false, slowUntil: 0, slowFactor: 1 },
    { genome: { resist: 2 }, lane: 0, alive: true, spawnAt: 0, reached: false, slowUntil: 0, slowFactor: 1 }, // cold耐性
    { genome: { resist: 0 }, lane: 1, alive: true, spawnAt: 0, reached: false, slowUntil: 0, slowFactor: 1 }, // 別レーン
    { genome: { resist: 0 }, lane: 0, alive: true, spawnAt: 2, reached: false, slowUntil: 0, slowFactor: 1 }, // 未出現
    { genome: { resist: 0 }, lane: 0, alive: false, spawnAt: 0, reached: false, slowUntil: 0, slowFactor: 1 }, // 撃破済み
  ];
  Enemies.applyHeatToLane(laneEnemies, 0, 5);
  check('applyHeatToLane: 対象レーンの出現済み生存個体に減速が適用される', laneEnemies[0].slowFactor === Config.SKILL.slowFactor);
  check('applyHeatToLane: cold耐性個体は弱い減速(coldResistFactor)が適用される', laneEnemies[1].slowFactor === Config.SKILL.coldResistFactor);
  check('applyHeatToLane: 別レーンの個体には適用されない', laneEnemies[2].slowFactor === 1);
  check('applyHeatToLane: 未出現の個体には適用されない', laneEnemies[3].slowFactor === 1);
  check('applyHeatToLane: 撃破済みの個体には適用されない', laneEnemies[4].slowFactor === 1);
}

// --- 結果出力 ---
console.log('---');
if (failed > 0) {
  console.log(`FAILED: ${failed}/${count}`);
  process.exit(1);
} else {
  console.log(`ok (${count} tests)`);
}
