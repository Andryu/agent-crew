// enemies.js
// genome→個体生成、レーン移動、被ダメ、results生成（純粋関数群、DOM非依存）。
//
// Enemy: {
//   genome, lane(0..2), x(セル単位、初期-1), hp, maxHp,
//   spawnAt(秒。出現までの残り時間。0以下で出現済み), realSpeed,
//   slowUntil(秒。waveClock基準の絶対時刻。この時刻未満なら減速中), slowFactor,
//   alive, reached,
// }

import {
  hpBaseForWave,
  POPULATION,
  LANE_LENGTH,
  SKILL,
  RESIST_HP_COST,
  REACHED_DAMAGE_LARGE_SIZE_THRESHOLD,
  REACHED_DAMAGE_LARGE,
  REACHED_DAMAGE_SMALL,
} from './config.js';

/**
 * lane重み配列から1つのレーンindex(0..2)を抽選する。
 * @param {number[]} laneWeights
 * @param {ReturnType<import('./rng.js').makeRng>} rng
 * @returns {number}
 */
function pickLane(laneWeights, rng) {
  const total = laneWeights[0] + laneWeights[1] + laneWeights[2];
  if (total <= 0) return rng.int(3);
  const r = rng() * total;
  let acc = 0;
  for (let i = 0; i < 3; i++) {
    acc += laneWeights[i];
    if (r < acc) return i;
  }
  return 2;
}

/**
 * 個体群から敵インスタンス配列を生成する。個体はPOPULATION.spawnInterval秒間隔で順次出現、初期x=-1。
 * @param {Array<object>} population genome配列
 * @param {number} wave
 * @param {ReturnType<import('./rng.js').makeRng>} rng
 * @returns {Array<object>} Enemy[]
 */
export function spawnFromPopulation(population, wave, rng) {
  const hpBase = hpBaseForWave(wave);
  return population.map((genome, index) => {
    const maxHp = hpBase * genome.hp * genome.size * (genome.resist !== 0 ? RESIST_HP_COST : 1);
    return {
      genome,
      lane: pickLane(genome.lane, rng),
      x: -1,
      hp: maxHp,
      maxHp,
      spawnAt: index * POPULATION.spawnInterval,
      realSpeed: genome.speed / Math.sqrt(genome.size),
      slowUntil: 0,
      slowFactor: 1,
      alive: true,
      reached: false,
    };
  });
}

/**
 * 個体が本拠地に到達した際に失うライフ数を返す（到達被害計算とライフ減算の両方で共有する）。
 * @param {object} genome
 * @returns {number}
 */
export function livesLostFor(genome) {
  return genome.size >= REACHED_DAMAGE_LARGE_SIZE_THRESHOLD ? REACHED_DAMAGE_LARGE : REACHED_DAMAGE_SMALL;
}

/**
 * 新しい減速効果を適用する。
 * 現在より強い(factorが小さい)場合のみ置換、同じならuntilを延長、弱ければ無視。
 * 既存の減速が失効済み(now >= slowUntil)の場合は無条件で新しい効果を適用する。
 * @param {object} enemy
 * @param {number} factor 実速度倍率（小さいほど強い減速）
 * @param {number} durationSec
 * @param {number} now waveClock基準の現在時刻（秒）
 * @returns {object} enemy（同一参照、破壊的更新）
 */
export function applySlow(enemy, factor, durationSec, now) {
  const newUntil = now + durationSec;
  const isActive = now < (enemy.slowUntil ?? 0);
  if (!isActive) {
    enemy.slowFactor = factor;
    enemy.slowUntil = newUntil;
  } else if (factor < enemy.slowFactor) {
    enemy.slowFactor = factor;
    enemy.slowUntil = newUntil;
  } else if (factor === enemy.slowFactor) {
    enemy.slowUntil = Math.max(enemy.slowUntil, newUntil);
  }
  // factor > enemy.slowFactor（弱い）かつ有効中の場合は無視
  return enemy;
}

/**
 * 全個体を1フレーム分進める（破壊的更新、戻り値なし）。
 * @param {Array<object>} enemies
 * @param {number} dt
 * @param {number} [laneLength]
 * @param {number} [now] waveClock基準の現在時刻（秒）。省略時は減速判定を行わない
 */
export function stepEnemies(enemies, dt, laneLength = LANE_LENGTH, now) {
  for (const enemy of enemies) {
    if (!enemy.alive) continue;
    if (enemy.spawnAt > 0) {
      enemy.spawnAt -= dt;
      continue;
    }
    const slowed = typeof now === 'number' && now < (enemy.slowUntil ?? 0);
    const speed = slowed ? enemy.realSpeed * enemy.slowFactor : enemy.realSpeed;
    enemy.x += speed * dt;
    if (enemy.x >= laneLength) {
      enemy.x = laneLength;
      enemy.alive = false;
      enemy.reached = true;
    }
  }
}

/**
 * 発熱スキルをレーンに発動する。出現済み(spawnAt<=0)の生存個体(alive)のうち
 * 指定レーンの個体全てに適用する。cold耐性(resist===2)の個体は SKILL.coldResistFactor
 * （弱い減速）、それ以外は SKILL.slowFactor を「発熱factor」として扱う。
 * applySlow（強い方優先・同じなら延長・弱ければ無視）とは別の専用ロジックで、
 * 対象個体の減速factorを「現在の（有効中の）slowFactorと発熱factorの小さい方」に、
 * slowUntilを「現在のslowUntilとnow+SKILL.durationの大きい方」に更新する。
 * これにより、既にcold塔などでより強い減速がかかっている個体に対しても
 * 発熱がno-opにならず、持続時間だけは必ず延長される（2026-08-16 CP2レビュー対応）。
 * @param {Array<object>} enemies
 * @param {number} lane 0..2
 * @param {number} now waveClock基準の現在時刻（秒）
 */
export function applyHeatToLane(enemies, lane, now) {
  for (const enemy of enemies) {
    if (!enemy.alive || enemy.spawnAt > 0 || enemy.reached) continue;
    if (enemy.lane !== lane) continue;
    const heatFactor = enemy.genome.resist === 2 ? SKILL.coldResistFactor : SKILL.slowFactor;
    const currentlySlowed = typeof now === 'number' && now < (enemy.slowUntil ?? 0);
    const currentFactor = currentlySlowed ? enemy.slowFactor : 1;
    enemy.slowFactor = Math.min(currentFactor, heatFactor);
    enemy.slowUntil = Math.max(enemy.slowUntil ?? 0, now + SKILL.duration);
  }
}

/**
 * evolution.evaluateへの入力resultsを生成する。populationと同じ順序で返す。
 * @param {Array<object>} enemies
 * @param {number} laneLength
 * @returns {Array<{progress:number, reachedBase:boolean, damageDealtToBase:number}>}
 */
export function collectResults(enemies, laneLength) {
  return enemies.map((enemy) => {
    const progress = Math.min(1, Math.max(0, enemy.x / laneLength));
    const reachedBase = !!enemy.reached;
    let damageDealtToBase = 0;
    if (reachedBase) {
      damageDealtToBase = livesLostFor(enemy.genome);
    }
    return { progress, reachedBase, damageDealtToBase };
  });
}
