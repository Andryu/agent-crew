// towers.js
// 塔の索敵・攻撃（ヒットスキャン即着弾）。弾は即着弾扱いとし、
// 描画用に0.1秒の軌跡を shots 配列として返す（実装者裁量の範囲）。

import { TOWERS, RESIST_DAMAGE_MULT } from './config.js';
import { applySlow } from './enemies.js';

const TRAIL_TTL = 0.1; // 秒

const ATTR_TO_RESIST = { none: 0, heat: 1, cold: 2, bolt: 3 };

function towerCenter(tower) {
  return { x: tower.col + 0.5, y: tower.row + 0.5 };
}

function enemyPos(enemy, laneRows) {
  return { x: enemy.x, y: laneRows[enemy.lane] + 0.5 };
}

function distance(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * 射程内で最も臓器に近い（xが最大の）生存個体を選ぶ。
 * @param {object} tower
 * @param {Array<object>} enemies
 * @param {object} def TOWERS[tower.id]
 * @param {number[]} laneRows
 * @returns {object|null}
 */
function findTarget(tower, enemies, def, laneRows) {
  const center = towerCenter(tower);
  let best = null;
  let bestX = -Infinity;
  for (const enemy of enemies) {
    if (!enemy.alive || enemy.spawnAt > 0) continue;
    const pos = enemyPos(enemy, laneRows);
    if (distance(center, pos) > def.range) continue;
    if (enemy.x > bestX) {
      bestX = enemy.x;
      best = enemy;
    }
  }
  return best;
}

function applyDamage(enemy, rawDamage, attr) {
  const resisted = attr !== 'none' && enemy.genome.resist === ATTR_TO_RESIST[attr];
  const damage = resisted ? rawDamage * RESIST_DAMAGE_MULT : rawDamage;
  enemy.hp -= damage;
  if (enemy.hp <= 0) {
    enemy.alive = false;
    enemy.reached = false;
  }
}

/**
 * 全塔インスタンスを1フレーム分処理する。towerInstance要素へ
 * `cooldown` フィールドを破壊的に付与・更新して連射間隔を管理する。
 * @param {Array<{id:string, col:number, row:number, cooldown?:number}>} towerInstances
 * @param {Array<object>} enemies Enemy[]
 * @param {number} dt
 * @param {number[]} laneRows GRID.laneRows相当
 * @param {number} [now] waveClock基準の現在時刻（秒）。cold の減速適用に使用
 * @returns {Array<{x1:number,y1:number,x2:number,y2:number,towerId:string,ttl:number}>} shots
 */
export function stepTowers(towerInstances, enemies, dt, laneRows, now = 0) {
  const shots = [];
  for (const tower of towerInstances) {
    const def = TOWERS[tower.id];
    if (!def) continue;
    if (typeof tower.cooldown !== 'number') tower.cooldown = 0;
    tower.cooldown -= dt;
    if (tower.cooldown > 0) continue;

    const target = findTarget(tower, enemies, def, laneRows);
    if (!target) continue;

    tower.cooldown = def.interval;
    const center = towerCenter(tower);
    const targetPos = enemyPos(target, laneRows);

    if (def.special === 'splash') {
      const radius = def.splashRadius;
      for (const enemy of enemies) {
        if (!enemy.alive || enemy.spawnAt > 0) continue;
        const pos = enemyPos(enemy, laneRows);
        if (distance(targetPos, pos) <= radius) {
          applyDamage(enemy, def.damage, def.attr);
        }
      }
    } else {
      applyDamage(target, def.damage, def.attr);
      if (def.special === 'slow' && target.alive) {
        applySlow(target, def.slowFactor, def.slowDuration, now);
      }
    }

    shots.push({
      x1: center.x,
      y1: center.y,
      x2: targetPos.x,
      y2: targetPos.y,
      towerId: tower.id,
      ttl: TRAIL_TTL,
    });
  }
  return shots;
}
