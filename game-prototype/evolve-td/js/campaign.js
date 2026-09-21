// 群れの適応は直前の防衛を観測する明示的な規則。偵察は生成済み個体の実数。
import { makeRng } from './rng.js';
import { GRID, TOWERS, TOWER_ORDER, UPGRADE } from './config.js';
import { spawnFromPopulation, applySlow, livesLostFor } from './enemies.js';
import { stepTowers } from './towers.js';
import { towerInvested, upgradeCost } from './game-state.js';
import { createField, entrancePaths, placementCheck, initMazeEnemy, stepMazeEnemies, refreshDistances } from './maze.js';

export const TOTAL_WAVES = 9;
export const STEP = 1 / 60;
export const LABELS = { basic: 'パルス', heat: 'フレア', cold: 'フロスト', bolt: 'レール' };
export const ROLES = { basic: '速射・低コスト', heat: '範囲攻撃・密集に強い', cold: '減速・他の塔を支援', bolt: '長射程・重い一撃' };
export const LANES = ['入口A', '入口B', '入口C'];
export const LIVE_MOVE_COST = 15;
export const COMBAT_SUPPLY = 60;
export const START_CREDITS = 360;
export const START_LIVES = 24;
export const RESIST_NAMES = ['適応なし', '熱耐性', '冷耐性', '電耐性', '装甲'];
const ATTR = { basic: 4, heat: 1, cold: 2, bolt: 3 };

export function observeDefense(towers) {
  const power = Object.fromEntries(TOWER_ORDER.map(id => [id, 0]));
  const coverage = [0, 0, 0];
  for (const tower of towers) {
    const def = TOWERS[tower.id];
    const level = tower.level || 1;
    const dps = def.damage * UPGRADE.dmgMul ** (level - 1) / def.interval;
    const range = def.range + UPGRADE.rangeAdd * (level - 1);
    power[tower.id] += dps;
    GRID.laneRows.forEach((row, lane) => {
      const dy = Math.abs(tower.row - row);
      if (dy < range) {
        const dx = Math.sqrt(range * range - dy * dy);
        const length = Math.max(0, Math.min(12, tower.col + .5 + dx) - Math.max(0, tower.col + .5 - dx));
        coverage[lane] += dps * length;
      }
    });
  }
  const total = Object.values(power).reduce((a, b) => a + b, 0);
  const dominant = TOWER_ORDER.reduce((a, b) => power[b] > power[a] ? b : a);
  const weakest = coverage.indexOf(Math.min(...coverage));
  return { power, coverage, dominant: total ? dominant : null, weakest, share: total ? power[dominant] / total : 0 };
}

export function createWave(seed, wave, observation, difficulty = 'standard') {
  const rng = makeRng((seed ^ Math.imul(wave, 0x9e3779b1)) >>> 0);
  const count = 16 + wave * 2;
  const resistant = observation?.dominant ? ATTR[observation.dominant] : 0;
  const weak = observation?.dominant ? observation.weakest : (wave + seed) % 3;
  const bossWave = wave % 3 === 0;
  const population = Array.from({ length: count }, (_, i) => {
    const adapt = wave > 1 && i % 5 < 3 ? resistant : (i % 5 === 4 ? 1 + rng.int(3) : 0);
    const elite = bossWave && i >= count - 2;
    return {
      speed: (elite ? .64 : .82 + rng() * .28) * (wave >= 7 ? 1.06 : 1),
      hp: (elite ? 2.8 : .84 + rng() * .22) * (difficulty === 'challenge' ? 1.3 : 1),
      size: elite ? 1.45 : .85 + rng() * .2,
      resist: adapt === 4 ? 0 : adapt,
      armor: adapt === 4,
      elite,
      lane: [1 / 3, 1 / 3, 1 / 3],
    };
  });
  const enemies = spawnFromPopulation(population, wave, rng);
  enemies.forEach((enemy, i) => {
    // 人数を確定させる。約60%を弱い流路へ優先割当し、残りは3流路へ均等分配する。
    enemy.lane = observation?.dominant && i % 5 < 3 ? weak : (i + seed) % 3;
    enemy.spawnAt = i * .48;
    const mazePressure = 1 + (wave - 1) * .30;
    enemy.hp *= mazePressure; enemy.maxHp *= mazePressure;
  });
  const reason = observation?.dominant
    ? `前戦の実ダメージの${Math.round(observation.share * 100)}%が${LABELS[observation.dominant]}。群れは${RESIST_NAMES[resistant]}を獲得し、損害の少なかった${LANES[weak]}へ集中。`
    : '塔が壁になる。曲がり角へ誘導し、敵が来てからも配置で道を変えよう。';
  return { enemies, wave, resistant, weak, bossWave, reason, observation };
}

export function scout(plan) {
  const lanes = [0, 0, 0];
  const resist = [0, 0, 0, 0, 0];
  for (const e of plan.enemies) {
    lanes[e.lane]++;
    resist[e.genome.armor ? 4 : e.genome.resist]++;
  }
  return { total: plan.enemies.length, lanes, resist, elites: plan.enemies.filter(e => e.genome.elite).length };
}

export function newCampaign({ seed = 1, difficulty = 'standard' } = {}) {
  seed = Number(seed) >>> 0;
  difficulty = difficulty === 'challenge' ? 'challenge' : 'standard';
  const plan = createWave(seed, 1, null, difficulty);
  const field = createField([]);
  return { seed, difficulty, phase: 'prepare', wave: 1, lives: START_LIVES, credits: START_CREDITS,
    towers: [], plan, enemies: [], clock: 0, kills: 0, totalLeaks: 0, waveKills: 0,
    waveLeaks: 0, history: [], observation: null, pulseReady: 0, shots: [], events: [],
    field, paths: entrancePaths(field), revision: 0, lastError: '',
    damageByType: Object.fromEntries(TOWER_ORDER.map(id => [id, 0])), damageByLane: [0, 0, 0] };
}

function editable(state) { return state.phase === 'prepare' || state.phase === 'battle'; }
function reject(state, reason) { state.lastError = reason; return false; }
function commitField(state, result) {
  state.field = result.field;
  state.paths = result.paths;
  state.revision++;
  state.lastError = '';
  refreshDistances(state.enemies, state.field);
}
export function build(state, id, col, row) {
  if (!editable(state)) return reject(state, '作戦は終了しています');
  if (!TOWERS[id]) return reject(state, 'ユニットを選んでください');
  if (state.credits < TOWERS[id].cost) return reject(state, 'クレジットが不足しています');
  const result = placementCheck(state.towers, state.enemies, col, row);
  if (!result.ok) return reject(state, result.reason);
  state.credits -= TOWERS[id].cost;
  state.towers.push({ id, col, row, level: 1, cooldown: state.phase === 'battle' ? TOWERS[id].interval : 0 });
  commitField(state, result);
  return true;
}
export function relocate(state, fromCol, fromRow, col, row) {
  if (!editable(state)) return reject(state, '作戦は終了しています');
  const tower = state.towers.find(t => t.col === fromCol && t.row === fromRow);
  if (!tower) return reject(state, '移設する塔を選んでください');
  if (fromCol === col && fromRow === row) return reject(state, '別のマスを選んでください');
  const cost = state.phase === 'battle' ? LIVE_MOVE_COST : 0;
  if (state.credits < cost) return reject(state, `戦闘中の移設には${cost}C必要です`);
  const result = placementCheck(state.towers, state.enemies, col, row, {col: fromCol, row: fromRow});
  if (!result.ok) return reject(state, result.reason);
  state.credits -= cost;
  tower.col = col; tower.row = row;
  if (state.phase === 'battle') tower.cooldown = Math.max(tower.cooldown || 0, .8);
  commitField(state, result);
  return true;
}
export function upgrade(state, col, row) {
  if (!editable(state)) return reject(state, '作戦は終了しています');
  const tower = state.towers.find(t => t.col === col && t.row === row);
  if (!tower || tower.level >= 3 || state.credits < upgradeCost(tower)) return reject(state, '強化上限または資金不足です');
  state.credits -= upgradeCost(tower);
  tower.level++;
  state.lastError = '';
  return true;
}
export function recycle(state, col, row) {
  if (!editable(state)) return false;
  const index = state.towers.findIndex(t => t.col === col && t.row === row);
  if (index < 0) return false;
  state.credits += Math.floor(towerInvested(state.towers[index]) * (state.phase === 'battle' ? 70 : 100) / 100);
  state.towers.splice(index, 1);
  const field = createField(state.towers);
  commitField(state, {field, paths: entrancePaths(field)});
  return true;
}

// 命中した実HP減少量。過剰ダメージ・減速の支援効果は含めない。
export function observeBattle(state) {
  const power = {...state.damageByType};
  const total = Object.values(power).reduce((a,b) => a+b, 0);
  const dominant = TOWER_ORDER.reduce((a,b) => power[b] > power[a] ? b : a);
  const counts = scout(state.plan).lanes;
  const coverage = state.damageByLane.map((damage,i) => counts[i] ? damage / counts[i] : Infinity);
  return {power, coverage, dominant: total ? dominant : null, weakest: coverage.indexOf(Math.min(...coverage)), share: total ? power[dominant]/total : 0};
}
export function launch(state) {
  if (state.phase !== 'prepare') return false;
  state.damageByType = Object.fromEntries(TOWER_ORDER.map(id => [id, 0]));
  state.damageByLane = [0,0,0];
  state.credits += COMBAT_SUPPLY;
  state.enemies = state.plan.enemies.map(e => ({ ...e, genome: { ...e.genome } }));
  state.enemies.forEach(e => initMazeEnemy(e, state.field));
  state.towers.forEach(t => t.cooldown = 0);
  state.phase = 'battle';
  state.clock = 0;
  state.waveKills = 0;
  state.waveLeaks = 0;
  state.pulseReady = 0;
  return true;
}
export function pulse(state, lane) {
  if (state.phase !== 'battle' || !Number.isInteger(lane) || lane < 0 || lane > 2 || state.clock < state.pulseReady) return false;
  state.enemies.filter(e => e.alive && e.spawnAt <= 0 && e.lane === lane).forEach(e => applySlow(e, .2, 3, state.clock));
  state.pulseReady = state.clock + 9;
  state.events.push({ type: 'pulse', lane });
  return true;
}
export function tick(state) {
  if (state.phase !== 'battle') return;
  state.clock += STEP;
  state.shots = state.shots.filter(s => (s.ttl -= STEP) > 0);
  refreshDistances(state.enemies, state.field);
  state.shots.push(...stepTowers(state.towers, state.enemies, STEP, GRID.laneRows, state.clock, (id, damage, enemy) => {
    state.damageByType[id] += damage;
    state.damageByLane[enemy.lane] += damage;
  }));
  stepMazeEnemies(state.enemies, STEP, state.clock, state.field);
  for (const e of state.enemies) {
    if (e.alive || e.counted) continue;
    e.counted = true;
    if (e.reached) {
      const damage = livesLostFor(e.genome);
      state.lives = Math.max(0, state.lives - damage);
      state.totalLeaks += damage;
      state.waveLeaks += damage;
      state.events.push({ type: 'leak', lane: e.lane });
    } else {
      state.kills++;
      state.waveKills++;
      state.credits += 4;
      state.events.push({ type: 'kill', x: e.x, y: e.y, lane: e.lane, resist: e.genome.resist });
    }
  }
  if (state.lives <= 0) {
    state.phase = 'defeat';
    return;
  }
  if (state.enemies.every(e => !e.alive)) {
    state.observation = observeBattle(state);
    state.history.push({ wave: state.wave, kills: state.waveKills, leaks: state.waveLeaks, observation: state.observation, plan: scout(state.plan) });
    if (state.wave >= TOTAL_WAVES) state.phase = 'victory';
    else {
      state.credits += 65;
      state.wave++;
      state.plan = createWave(state.seed, state.wave, state.observation, state.difficulty);
      state.phase = 'prepare';
    }
  }
}

export function score(state) {
  return (state.phase === 'victory' ? 2000 : 0) + (state.wave - (state.phase === 'victory' ? 0 : 1)) * 250 + state.kills * 10 + state.lives * 25;
}
