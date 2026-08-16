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
  check(
    'initialPopulationのlaneが均等[1/3,1/3,1/3]',
    pop.every((g) => g.lane.every((w) => Math.abs(w - 1 / 3) < 1e-9))
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

  const nextPop = Evolution.evolve(pop, fitness.concat(Array(47).fill(0)), { wave: 1, towerDiversity: 0.25, nextSize: 24 }, rng);
  check('evolve(CP1スタブ)がnextSize件のinitialPopulationを返す', nextPop.length === 24 && nextPop.every((g) => g.resist === 0));

  check('diffReport(CP1スタブ)が空配列を返す', Array.isArray(Evolution.diffReport(summary, summary)) && Evolution.diffReport(summary, summary).length === 0);
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

// --- 結果出力 ---
console.log('---');
if (failed > 0) {
  console.log(`FAILED: ${failed}/${count}`);
  process.exit(1);
} else {
  console.log(`ok (${count} tests)`);
}
