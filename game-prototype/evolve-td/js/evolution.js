// evolution.js
// 進化ロジック（純粋関数・DOM非依存・乱数は注入）。
// CP2でevolve/diffReportを本実装、representativeを追加。

import {
  GENOME_BASE,
  GENOME_RANGES,
  INITIAL_JITTER,
  INITIAL_LANE_NOISE,
  EVOLUTION,
  DIFF_THRESHOLDS,
  RESIST_LABELS,
  LANE_LABELS,
} from './config.js';

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

function jittered(base, range, rng) {
  const factor = 1 + (rng() * 2 - 1) * INITIAL_JITTER; // ±20%
  return clamp(base * factor, range[0], range[1]);
}

/**
 * 均等(1/3)に±noiseの一様ノイズを加え、負値を0にクランプして再正規化したlaneを返す。
 * @param {number} noise
 * @param {ReturnType<import('./rng.js').makeRng>} rng
 * @returns {number[]}
 */
function jitteredLane(noise, rng) {
  const noisy = [0, 1, 2].map(() => Math.max(0, 1 / 3 + (rng() * 2 - 1) * noise));
  const total = noisy[0] + noisy[1] + noisy[2];
  return total > 0 ? noisy.map((w) => w / total) : [1 / 3, 1 / 3, 1 / 3];
}

/**
 * 初期集団を生成する。speed/hp/sizeを基準値±20%でジッター、resistは全て0、
 * laneは均等(1/3)に各要素±0.15の一様ノイズを加えて再正規化する。
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
      lane: jitteredLane(INITIAL_LANE_NOISE, rng),
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

function crossover(parentA, parentB, rng) {
  return {
    speed: rng() < 0.5 ? parentA.speed : parentB.speed,
    hp: rng() < 0.5 ? parentA.hp : parentB.hp,
    resist: rng() < 0.5 ? parentA.resist : parentB.resist,
    size: rng() < 0.5 ? parentA.size : parentB.size,
    lane: (rng() < 0.5 ? parentA.lane : parentB.lane).slice(),
  };
}

function mutateStat(value, range, rng) {
  const factor = 1 + rng.normal(0, EVOLUTION.mutationSigma);
  return clamp(value * factor, range[0], range[1]);
}

/**
 * resistを「現在値を除く」0..resistCount-1から再抽選する。
 * 同値への再抽選（実質何も変わらない）を防ぎ、ボトルネックによる
 * 遺伝的浮動（単一resistへの固着）を抑える（2026-08-16 team-lead判断）。
 * @param {number} current
 * @param {number} count
 * @param {ReturnType<import('./rng.js').makeRng>} rng
 * @returns {number}
 */
function rerollResistExcluding(current, count, rng) {
  const next = rng.int(count - 1);
  return next >= current ? next + 1 : next;
}

function mutate(child, p, rng) {
  if (rng() < p) child.speed = mutateStat(child.speed, GENOME_RANGES.speed, rng);
  if (rng() < p) child.hp = mutateStat(child.hp, GENOME_RANGES.hp, rng);
  if (rng() < p) child.size = mutateStat(child.size, GENOME_RANGES.size, rng);
  if (rng() < p) child.resist = rerollResistExcluding(child.resist, GENOME_RANGES.resistCount, rng);
  if (rng() < p) {
    const noisy = child.lane.map((w) => Math.max(0, w + (rng() * 2 - 1) * EVOLUTION.laneNoise));
    const total = noisy[0] + noisy[1] + noisy[2];
    child.lane = total > 0 ? noisy.map((w) => w / total) : [1 / 3, 1 / 3, 1 / 3];
  }
}

/**
 * 次世代個体群を生成する。
 * 1. fitness上位30%（最低4体）を親プールに
 * 2. 子は親2体からの遺伝子ごとの一様交叉
 * 3. 突然変異: 遺伝子ごとに確率 p = 0.08*(1+(1-towerDiversity))
 * 4. 多様性保険: 子集団の10%をinitialPopulationの個体で置換
 * @param {Array<object>} population
 * @param {number[]} fitness
 * @param {{wave:number, towerDiversity:number, nextSize:number}} ctx
 * @param {ReturnType<import('./rng.js').makeRng>} rng
 * @returns {Array<object>}
 */
export function evolve(population, fitness, ctx, rng) {
  const parentCount = Math.max(EVOLUTION.parentMin, Math.ceil(population.length * EVOLUTION.parentRatio));
  const ranked = population
    .map((genome, i) => ({ genome, fitness: fitness[i] }))
    .sort((a, b) => b.fitness - a.fitness);
  const parents = ranked.slice(0, Math.min(parentCount, ranked.length)).map((entry) => entry.genome);

  const p = EVOLUTION.mutationBaseRate * (1 + (1 - ctx.towerDiversity));

  const children = [];
  for (let i = 0; i < ctx.nextSize; i++) {
    const parentA = rng.pick(parents);
    const parentB = rng.pick(parents);
    const child = crossover(parentA, parentB, rng);
    mutate(child, p, rng);
    children.push(child);
  }

  // 多様性保険: 子集団のうちceil(nextSize*0.1)体をinitialPopulationの個体で置換（追加ではない）
  const insuranceCount = Math.min(children.length, Math.ceil(ctx.nextSize * EVOLUTION.diversityInsuranceRatio));
  if (insuranceCount > 0) {
    const freshPool = initialPopulation(insuranceCount, rng);
    const indices = Array.from({ length: children.length }, (_, i) => i);
    for (let i = 0; i < insuranceCount; i++) {
      const j = i + rng.int(indices.length - i);
      const tmp = indices[i];
      indices[i] = indices[j];
      indices[j] = tmp;
    }
    for (let i = 0; i < insuranceCount; i++) {
      children[indices[i]] = freshPool[i];
    }
  }

  return children;
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

function pctChange(prev, next) {
  if (prev === 0) return next === 0 ? 0 : 1;
  return (next - prev) / prev;
}

function formatSignedPercent(fraction) {
  const v = Math.round(fraction * 100);
  return `${v >= 0 ? '+' : ''}${v}%`;
}

function formatSharePercent(share) {
  return `${Math.round(share * 100)}%`;
}

/**
 * 前世代と今世代の要約を比較し、変化量の大きい順に最大3行の日本語文を返す。
 * |変化|が閾値未満（速度・体力・体格 ±4%未満、割合 ±8pt未満）の項目は出さない。
 * 耐性・レーンの「増えた」は変化後の割合が shareMinAfter(15%) 以上のときだけ閾値通過。
 * 全て閾値未満なら、最大の変化を「わずかに〜」1行（softStat/softShare 以上のとき）、それも無ければ「群れに目立った変化はない」1行。
 * @param {ReturnType<typeof summarize>} prevSummary
 * @param {ReturnType<typeof summarize>} nextSummary
 * @returns {string[]}
 */
export function diffReport(prevSummary, nextSummary) {
  const T = DIFF_THRESHOLDS;
  // 候補: { magnitude(閾値比で正規化), passes(閾値以上か), text, softText }
  const candidates = [];
  const statItems = [
    ['speedMean', '群れは高速化した', '群れは低速化した', '速く', '遅く'],
    ['hpMean', '群れは頑丈になった', '群れはひ弱になった', '頑丈に', 'ひ弱に'],
    ['sizeMean', '体格が大きくなった', '体格が小さくなった', '大きく', '小さく'],
  ];
  for (const [key, up, down, softUp, softDown] of statItems) {
    const change = pctChange(prevSummary[key], nextSummary[key]);
    const abs = Math.abs(change);
    if (abs < T.softStatPercent) continue;
    const pct = formatSignedPercent(change);
    candidates.push({
      magnitude: abs / T.statPercent,
      passes: abs >= T.statPercent,
      text: `${change > 0 ? up : down}（${pct}）`,
      softText: `わずかに${change > 0 ? softUp : softDown}なった（${pct}）`,
    });
  }
  // resist: index0(なし)は「耐性」ではないため対象外
  for (let i = 1; i <= 3; i++) {
    const from = prevSummary.resistShare[i];
    const to = nextSummary.resistShare[i];
    const change = to - from;
    const abs = Math.abs(change);
    if (abs < T.softSharePoint) continue;
    const label = RESIST_LABELS[i];
    const range = `${formatSharePercent(from)}→${formatSharePercent(to)}`;
    // 「増えた」は変化後の割合が shareMinAfter 以上のときだけ閾値通過扱い（ノイズ抑制）
    const passes = abs >= T.sharePoint && (change < 0 || to >= T.shareMinAfter);
    candidates.push({
      magnitude: abs / T.sharePoint,
      passes,
      text: change > 0 ? `${label}への耐性を持つ個体が増えた（${range}）` : `${label}への耐性を持つ個体が減った（${range}）`,
      softText: change > 0 ? `わずかに${label}への耐性を持つ個体が増えた（${range}）` : `わずかに${label}への耐性を持つ個体が減った（${range}）`,
    });
  }
  for (let i = 0; i < 3; i++) {
    const from = prevSummary.laneShare[i];
    const to = nextSummary.laneShare[i];
    const change = to - from;
    const abs = Math.abs(change);
    if (abs < T.softSharePoint) continue;
    const label = LANE_LABELS[i];
    const range = `${formatSharePercent(from)}→${formatSharePercent(to)}`;
    const passes = abs >= T.sharePoint && (change < 0 || to >= T.shareMinAfter);
    candidates.push({
      magnitude: abs / T.sharePoint,
      passes,
      text: change > 0 ? `${label}レーンを好むようになった（${range}）` : `${label}レーンを好まなくなった（${range}）`,
      softText: change > 0 ? `わずかに${label}レーンを好むようになった（${range}）` : `わずかに${label}レーンを好まなくなった（${range}）`,
    });
  }

  const passing = candidates.filter((c) => c.passes).sort((a, b) => b.magnitude - a.magnitude);
  if (passing.length > 0) return passing.slice(0, 3).map((c) => c.text);
  // 全項目が閾値未満: 最大の変化を「わずかに」1行で見せる（変化がほぼゼロなら定型1行）
  if (candidates.length > 0) {
    candidates.sort((a, b) => b.magnitude - a.magnitude);
    return [candidates[0].softText];
  }
  return ['群れに目立った変化はない'];
}

/**
 * summarizeが返す平均遺伝子に正規化距離が最も近い個体を1体返す。
 * distance = |speed-mean|/1.4 + |hp-mean|/2.4 + |size-mean|/0.8（resist/laneは見ない）
 * @param {Array<object>} population
 * @param {ReturnType<typeof summarize>} summary
 * @returns {object} genome
 */
export function representative(population, summary) {
  const speedRange = GENOME_RANGES.speed[1] - GENOME_RANGES.speed[0];
  const hpRange = GENOME_RANGES.hp[1] - GENOME_RANGES.hp[0];
  const sizeRange = GENOME_RANGES.size[1] - GENOME_RANGES.size[0];
  let best = null;
  let bestDistance = Infinity;
  for (const genome of population) {
    const distance =
      Math.abs(genome.speed - summary.speedMean) / speedRange +
      Math.abs(genome.hp - summary.hpMean) / hpRange +
      Math.abs(genome.size - summary.sizeMean) / sizeRange;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = genome;
    }
  }
  return best;
}
