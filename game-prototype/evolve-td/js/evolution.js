// evolution.js
// 進化ロジック（純粋関数・DOM非依存・乱数は注入）。
// CP1時点でシグネチャは最終形に凍結。evolve/diffReportの本体のみCP2で差し替える。

import { GENOME_BASE, GENOME_RANGES, INITIAL_JITTER } from './config.js';

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

function jittered(base, range, rng) {
  const factor = 1 + (rng() * 2 - 1) * INITIAL_JITTER; // ±10%
  return clamp(base * factor, range[0], range[1]);
}

/**
 * 初期集団を生成する。全遺伝子を基準値±10%でジッター、resistは全て0、laneは均等。
 * @param {number} n
 * @param {ReturnType<import('./rng.js').makeRng>} rng
 * @returns {Array<{speed:number, hp:number, resist:number, lane:number[], size:number}>}
 */
export function initialPopulation(n, rng) {
  const population = [];
  for (let i = 0; i < n; i++) {
    population.push({
      speed: jittered(GENOME_BASE.speed, GENOME_RANGES.speed, rng),
      hp: jittered(GENOME_BASE.hp, GENOME_RANGES.hp, rng),
      resist: 0,
      lane: [1 / 3, 1 / 3, 1 / 3],
      size: jittered(GENOME_BASE.size, GENOME_RANGES.size, rng),
    });
  }
  return population;
}

/**
 * 個体ごとのfitnessを算出する。
 * fitness = progress + (reachedBase ? 1.0 : 0) + damageDealtToBase*0.25
 * @param {Array<{progress:number, reachedBase:boolean, damageDealtToBase:number}>} results
 * @returns {number[]}
 */
export function evaluate(results) {
  return results.map((r) => r.progress + (r.reachedBase ? 1.0 : 0) + r.damageDealtToBase * 0.25);
}

/**
 * 次世代個体群を生成する。
 * CP1ではスタブ: initialPopulation(ctx.nextSize, rng) を返すのみ。
 * @param {Array<object>} population
 * @param {number[]} fitness
 * @param {{wave:number, towerDiversity:number, nextSize:number}} ctx
 * @param {ReturnType<import('./rng.js').makeRng>} rng
 * @returns {Array<object>}
 */
export function evolve(population, fitness, ctx, rng) {
  // CP2: replace body
  return initialPopulation(ctx.nextSize, rng);
}

/**
 * 個体群の要約統計を返す。
 * @param {Array<object>} population
 * @returns {{speedMean:number, hpMean:number, sizeMean:number, resistShare:number[], laneShare:number[]}}
 */
export function summarize(population) {
  const n = population.length;
  if (n === 0) {
    return {
      speedMean: 0,
      hpMean: 0,
      sizeMean: 0,
      resistShare: [0, 0, 0, 0],
      laneShare: [0, 0, 0],
    };
  }
  let speedSum = 0;
  let hpSum = 0;
  let sizeSum = 0;
  const resistCount = [0, 0, 0, 0];
  const laneSum = [0, 0, 0];
  for (const g of population) {
    speedSum += g.speed;
    hpSum += g.hp;
    sizeSum += g.size;
    resistCount[g.resist] = (resistCount[g.resist] || 0) + 1;
    laneSum[0] += g.lane[0];
    laneSum[1] += g.lane[1];
    laneSum[2] += g.lane[2];
  }
  return {
    speedMean: speedSum / n,
    hpMean: hpSum / n,
    sizeMean: sizeSum / n,
    resistShare: resistCount.map((c) => c / n),
    laneShare: laneSum.map((s) => s / n),
  };
}

/**
 * 前世代と今世代の要約を比較し、変化量の大きい順に最大3行の日本語文を返す。
 * CP1ではスタブ: 常に空配列を返す。
 * @param {ReturnType<typeof summarize>} prevSummary
 * @param {ReturnType<typeof summarize>} nextSummary
 * @returns {string[]}
 */
export function diffReport(prevSummary, nextSummary) {
  // CP2: replace body
  return [];
}
