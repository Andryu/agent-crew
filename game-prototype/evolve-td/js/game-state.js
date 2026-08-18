// game-state.js
// 資金・ライフ・ウェーブ・塔配置の状態と純粋な更新関数。
// GameState: { seed, gold, lives, wave, phase, towers, population, prevSummary,
//              lastSummary, unlocked, waveDiversity, cleared, endless, bestWave,
//              skillReadyAt }
// phase: 'place' | 'wave' | 'report'

import { makeRng } from './rng.js';
import { initialPopulation, evaluate, evolve, summarize, diffReport } from './evolution.js';
import {
  TOWERS,
  TOWER_ORDER,
  UNLOCK_WAVES,
  GRID,
  LIVES_START,
  ECONOMY,
  POPULATION,
  populationSizeForWave,
  SKILL,
  WAVE_COUNT,
  UPGRADE,
} from './config.js';

function isLaneRow(row) {
  return GRID.laneRows.includes(row);
}

function inBounds(col, row) {
  return col >= 0 && col < GRID.cols && row >= 0 && row < GRID.rows;
}

function findTowerAt(state, col, row) {
  return state.towers.find((t) => t.col === col && t.row === row) || null;
}

/**
 * 累積解禁される塔id配列を返す。
 * @param {number} wave
 * @returns {string[]}
 */
export function unlockedTowers(wave) {
  return TOWER_ORDER.filter((id) => wave >= UNLOCK_WAVES[id]);
}

/**
 * 新規ゲーム状態を生成する。
 * @param {{seed:number, gold?:number}} opts
 * @returns {object} GameState
 */
export function startNewGame({ seed, gold }) {
  const rng = makeRng(seed);
  const population = initialPopulation(POPULATION.initialSize, rng);
  return {
    seed,
    gold: typeof gold === 'number' ? gold : ECONOMY.initialGoldDefault,
    lives: LIVES_START,
    wave: 1,
    phase: 'place',
    towers: [],
    population,
    prevSummary: null,
    lastSummary: null,
    unlocked: unlockedTowers(1),
    waveDiversity: 0,
    cleared: false,
    endless: false,
    bestWave: 0,
    skillReadyAt: 0,
  };
}

/**
 * col,rowに towerId を配置できるかを判定する。
 * レーン上・重複・資金不足で false。
 * @param {object} state
 * @param {string} towerId
 * @param {number} col
 * @param {number} row
 * @returns {boolean}
 */
export function canPlace(state, towerId, col, row) {
  const def = TOWERS[towerId];
  if (!def) return false;
  if (!state.unlocked.includes(towerId)) return false;
  if (!inBounds(col, row)) return false;
  if (isLaneRow(row)) return false;
  if (findTowerAt(state, col, row)) return false;
  if (state.gold < def.cost) return false;
  return true;
}

/**
 * 塔を配置する。canPlaceがfalseの場合は状態を変更せず返す。
 * @param {object} state
 * @param {string} towerId
 * @param {number} col
 * @param {number} row
 * @returns {object} GameState
 */
export function placeTower(state, towerId, col, row) {
  if (!canPlace(state, towerId, col, row)) return state;
  const def = TOWERS[towerId];
  return {
    ...state,
    gold: state.gold - def.cost,
    towers: [...state.towers, { id: towerId, col, row, level: 1 }],
  };
}

/**
 * 塔の初期費用＋支払った強化費用の合計を返す（売却額の算出に使う）。
 * costMulは初期費用に対する倍率のため、levelから遡って再計算する（強化ごとの支払額を別途保持しない）。
 * @param {{id:string, level?:number}} tower
 * @returns {number}
 */
export function towerInvested(tower) {
  const def = TOWERS[tower.id];
  if (!def) return 0;
  const level = tower.level || 1;
  let invested = def.cost;
  for (let lv = 1; lv < level; lv++) {
    invested += def.cost * UPGRADE.costMul[lv - 1];
  }
  return invested;
}

/**
 * 塔をLv+1へ強化する費用（Lv1→2はcostMul[0]、Lv2→3はcostMul[1]倍。共に初期費用基準）。
 * Lv3（UPGRADE.maxLevel）の塔に対しては呼び出し側でcanUpgradeを先に確認すること。
 * @param {{id:string, level?:number}} tower
 * @returns {number}
 */
export function upgradeCost(tower) {
  const def = TOWERS[tower.id];
  if (!def) return Infinity;
  const level = tower.level || 1;
  const mul = UPGRADE.costMul[level - 1];
  if (typeof mul !== 'number') return Infinity;
  return Math.round(def.cost * mul);
}

/**
 * col,rowの塔を強化できるかを判定する。塔が存在しない・Lv3(最大)・資金不足でfalse。
 * @param {object} state
 * @param {number} col
 * @param {number} row
 * @returns {boolean}
 */
export function canUpgrade(state, col, row) {
  const tower = findTowerAt(state, col, row);
  if (!tower) return false;
  if ((tower.level || 1) >= UPGRADE.maxLevel) return false;
  const cost = upgradeCost(tower);
  if (state.gold < cost) return false;
  return true;
}

/**
 * col,rowの塔をLv+1へ強化する。canUpgradeがfalseの場合は状態を変更せず返す。
 * @param {object} state
 * @param {number} col
 * @param {number} row
 * @returns {object} GameState
 */
export function upgradeTower(state, col, row) {
  if (!canUpgrade(state, col, row)) return state;
  const tower = findTowerAt(state, col, row);
  const cost = upgradeCost(tower);
  return {
    ...state,
    gold: state.gold - cost,
    towers: state.towers.map((t) =>
      t.col === col && t.row === row ? { ...t, level: (t.level || 1) + 1 } : t
    ),
  };
}

/**
 * col,rowの塔を売却する（投資額=towerInvested()の70%返金）。塔が存在しなければ状態を変更せず返す。
 * @param {object} state
 * @param {number} col
 * @param {number} row
 * @returns {object} GameState
 */
export function sellTower(state, col, row) {
  const tower = findTowerAt(state, col, row);
  if (!tower) return state;
  const refund = Math.floor(towerInvested(tower) * ECONOMY.sellRatio);
  return {
    ...state,
    gold: state.gold + refund,
    towers: state.towers.filter((t) => !(t.col === col && t.row === row)),
  };
}

/**
 * 盤面に存在する塔の種類数/4を返す（towerDiversity）。
 * @param {object} state
 * @returns {number}
 */
function computeTowerDiversity(state) {
  const kinds = new Set(state.towers.map((t) => t.id));
  return kinds.size / TOWER_ORDER.length;
}

/**
 * ウェーブを開始する。phase='wave'、waveDiversityをその時点でスナップショットする。
 * @param {object} state
 * @returns {object} GameState
 */
export function startWave(state) {
  return {
    ...state,
    phase: 'wave',
    waveDiversity: computeTowerDiversity(state),
    skillReadyAt: 0,
  };
}

/**
 * 発熱スキルが解禁済みか（wave>=SKILL.unlockWave）。
 * @param {object} state
 * @returns {boolean}
 */
export function skillUnlocked(state) {
  return state.wave >= SKILL.unlockWave;
}

/**
 * 発熱スキルを使用する。解禁済み・ウェーブ中・CD0（now>=skillReadyAt）・
 * laneが0〜2の場合のみskillReadyAtをnow+SKILL.cooldownに更新する。
 * 条件を満たさない場合は状態を変更せず返す。
 * 実際の減速適用は enemies.js の applyHeatToLane を別途呼ぶこと（本関数は状態更新のみ）。
 * @param {object} state
 * @param {number} lane 0..2
 * @param {number} now waveClock基準の現在時刻（秒）
 * @returns {object} GameState
 */
export function useSkill(state, lane, now) {
  if (!skillUnlocked(state)) return state;
  if (state.phase !== 'wave') return state;
  if (!(lane === 0 || lane === 1 || lane === 2)) return state;
  if (now < (state.skillReadyAt ?? 0)) return state;
  return { ...state, skillReadyAt: now + SKILL.cooldown };
}

/**
 * ライフをn減らす（0未満にはならない）。
 * @param {object} state
 * @param {number} n
 * @returns {object} GameState
 */
export function loseLives(state, n) {
  return { ...state, lives: Math.max(0, state.lives - n) };
}

/**
 * ウェーブ終了処理。evaluate→evolve→summarize→diffReportを実行し、
 * phase='report'にする。W15終了時はcleared=trueにする。
 * ウェーブクリアボーナス（ECONOMY.waveClearBonus）を加算する
 * （到達／撃破に関わらずウェーブ終了時に加算。ゲームオーバー時はendWave自体が呼ばれない）。
 * @param {object} state
 * @param {Array<{progress:number, reachedBase:boolean, damageDealtToBase:number}>} results
 * @param {ReturnType<import('./rng.js').makeRng>} rng
 * @returns {{state:object, report:string[]}}
 */
export function endWave(state, results, rng) {
  const prevSummary = state.lastSummary ?? summarize(state.population);
  const fitness = evaluate(results);
  const nextSize = populationSizeForWave(state.wave + 1);
  const ctx = { wave: state.wave, towerDiversity: state.waveDiversity, nextSize };
  const nextPopulation = evolve(state.population, fitness, ctx, rng);
  const nextSummary = summarize(nextPopulation);
  const report = diffReport(prevSummary, nextSummary);
  const cleared = state.wave === WAVE_COUNT && !state.endless;
  const newState = {
    ...state,
    gold: state.gold + ECONOMY.waveClearBonus,
    population: nextPopulation,
    prevSummary,
    lastSummary: nextSummary,
    phase: 'report',
    cleared,
    bestWave: Math.max(state.bestWave, state.wave),
  };
  return { state: newState, report };
}

/**
 * 変異レポートを閉じ、次ウェーブの配置フェーズへ進む。
 * wave+1、unlockedを更新し、phase='place'にする。
 * @param {object} state
 * @returns {object} GameState
 */
export function closeReport(state) {
  const wave = state.wave + 1;
  return {
    ...state,
    wave,
    unlocked: unlockedTowers(wave),
    phase: 'place',
  };
}

/**
 * エンドレスモードへ移行する（cleared解除）。
 * この後closeReportを呼んで次ウェーブへ進める。
 * @param {object} state
 * @returns {object} GameState
 */
export function continueEndless(state) {
  return { ...state, endless: true, cleared: false };
}

/**
 * @param {object} state
 * @returns {boolean}
 */
export function isCleared(state) {
  return !!state.cleared;
}

/**
 * @param {object} state
 * @returns {boolean}
 */
export function isGameOver(state) {
  return state.lives <= 0;
}
