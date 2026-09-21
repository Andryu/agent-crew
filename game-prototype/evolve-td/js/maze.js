// 経路の同距離候補は右・下・上・左の固定順で選ぶ。
export const MAP = {
  cols: 12, rows: 8,
  entrances: [{ col: 0, row: 1 }, { col: 0, row: 4 }, { col: 0, row: 7 }],
  goal: { col: 11, row: 4 },
  rocks: [0, 1, 2, 3].map(row => ({ col: 4, row }))
    .concat([4, 5, 6, 7].map(row => ({ col: 8, row }))),
};
const key = ({ col, row }) => row * MAP.cols + col;
const valid = p => p && Number.isInteger(p.col) && Number.isInteger(p.row)
  && p.col >= 0 && p.col < MAP.cols && p.row >= 0 && p.row < MAP.rows;
const same = (a, b) => a && b && a.col === b.col && a.row === b.row;
const neighbors = p => [[1, 0], [0, 1], [0, -1], [-1, 0]]
  .map(([dc, dr]) => ({ col: p.col + dc, row: p.row + dr })).filter(valid);
const active = e => e.alive && !e.reached && !(e.spawnAt > 0);

export function createField(towers = []) {
  const blocked = new Set([...MAP.rocks, ...towers].filter(valid).map(key));
  const dist = Array(MAP.cols * MAP.rows).fill(Infinity);
  const queue = [];
  if (!blocked.has(key(MAP.goal))) {
    dist[key(MAP.goal)] = 0;
    queue.push(MAP.goal);
  }
  for (let i = 0; i < queue.length; i++) {
    for (const next of neighbors(queue[i])) {
      const k = key(next);
      if (blocked.has(k) || Number.isFinite(dist[k])) continue;
      dist[k] = dist[key(queue[i])] + 1;
      queue.push(next);
    }
  }
  return { blocked, dist };
}

function nextStep(field, cell) {
  return neighbors(cell).find(p => field.dist[key(p)] < field.dist[key(cell)]);
}

export function tracePath(field, start) {
  if (!valid(start) || !Number.isFinite(field.dist[key(start)])) return [];
  const path = [{ col: start.col, row: start.row }];
  while (!same(path.at(-1), MAP.goal)) {
    const next = nextStep(field, path.at(-1));
    if (!next) return [];
    path.push(next);
  }
  return path;
}

export function entrancePaths(field) {
  return MAP.entrances.map(start => tracePath(field, start));
}

// 検証対象は常に移設後の盤面。呼び出し元の塔・敵は変更しない。
export function placementCheck(towers, enemies, col, row, moveFrom = null) {
  const target = { col, row };
  const failure = reason => ({ ok: false, reason, field: null, paths: [] });
  if (!valid(target)) return failure('盤面のマスを選択してください');
  if (col === 0 || col === MAP.cols - 1) return failure('入口・出口の列には配置できません');
  if (MAP.rocks.some(p => same(p, target))) return failure('岩には配置できません');
  if (moveFrom && !towers.some(p => same(p, moveFrom))) return failure('移設元のタワーがありません');
  const remaining = towers.filter(p => !same(p, moveFrom));
  if (remaining.some(p => same(p, target))) return failure('すでにタワーがあります');
  const occupied = enemies.filter(active).flatMap(e => [e.cell, e.nextCell].filter(Boolean));
  if (occupied.some(p => same(p, target))) return failure('敵が通過中のマスには配置できません');
  const field = createField([...remaining, target]);
  const paths = entrancePaths(field);
  if (paths.some(path => path.length === 0)
    || occupied.some(p => !valid(p) || !Number.isFinite(field.dist[key(p)]))) {
    return { ok: false, reason: '出口までの経路を残してください', field, paths };
  }
  return { ok: true, reason: '', field, paths };
}

function updateDistance(enemy, field) {
  if (enemy.reached) enemy.distanceToGoal = 0;
  else if (enemy.nextCell) {
    enemy.distanceToGoal = field.dist[key(enemy.nextCell)]
      + Math.hypot(enemy.nextCell.col + .5 - enemy.x, enemy.nextCell.row + .5 - enemy.y);
  } else enemy.distanceToGoal = valid(enemy.cell) ? field.dist[key(enemy.cell)] : Infinity;
}

export function initMazeEnemy(enemy, field) {
  enemy.cell = { ...(MAP.entrances[enemy.lane] ?? MAP.entrances[0]) };
  enemy.nextCell = null;
  enemy.x = enemy.cell.col + .5;
  enemy.y = enemy.cell.row + .5;
  updateDistance(enemy, field);
  return enemy;
}

export function refreshDistances(enemies, field) {
  for (const enemy of enemies) updateDistance(enemy, field);
}

export function stepMazeEnemies(enemies, dt, now, field) {
  if (!(dt > 0) || !Number.isFinite(dt)) return;
  for (const enemy of enemies) {
    if (!enemy.alive || enemy.reached) continue;
    let movingTime = dt;
    if (enemy.spawnAt > 0) {
      movingTime = Math.max(0, dt - enemy.spawnAt);
      enemy.spawnAt -= dt;
    }
    if (!enemy.cell) initMazeEnemy(enemy, field);
    const slowed = now < (enemy.slowUntil ?? 0);
    let distance = Math.max(0, enemy.realSpeed * (slowed ? (enemy.slowFactor ?? 1) : 1) * movingTime);
    if (!Number.isFinite(distance)) distance = 0;
    while (true) {
      if (same(enemy.cell, MAP.goal) && !enemy.nextCell) {
        enemy.alive = false;
        enemy.reached = true;
        break;
      }
      if (distance <= 0) break;
      if (!enemy.nextCell) enemy.nextCell = nextStep(field, enemy.cell) ?? null;
      // 配置検証を通らない不正な盤面でも、無限ループは起こさない。
      if (!enemy.nextCell) break;
      const dx = enemy.nextCell.col + .5 - enemy.x;
      const dy = enemy.nextCell.row + .5 - enemy.y;
      const remaining = Math.hypot(dx, dy);
      if (distance < remaining) {
        enemy.x += dx * distance / remaining;
        enemy.y += dy * distance / remaining;
        break;
      }
      enemy.x = enemy.nextCell.col + .5;
      enemy.y = enemy.nextCell.row + .5;
      enemy.cell = enemy.nextCell;
      enemy.nextCell = null;
      distance -= remaining;
    }
    updateDistance(enemy, field);
  }
}
