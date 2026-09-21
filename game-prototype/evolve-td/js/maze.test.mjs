import test from 'node:test';
import assert from 'node:assert/strict';
import { MAP, createField, tracePath, entrancePaths, placementCheck, initMazeEnemy, refreshDistances, stepMazeEnemies } from './maze.js';

const makeEnemy = (field, extra = {}) => initMazeEnemy({ lane: 0, alive: true, spawnAt: 0, realSpeed: 1, ...extra }, field);
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} ≠ ${expected}`);
const index = p => p.row * MAP.cols + p.col;

test('初期盤面の3入口から曲がる最短経路が決定的に得られる', () => {
  const field = createField([]);
  assert.equal(field.dist.length, 96);
  assert.equal(field.blocked.size, 8);
  entrancePaths(field).forEach((path, i) => {
    assert.deepEqual(path[0], MAP.entrances[i]);
    assert.deepEqual(path.at(-1), MAP.goal);
    assert.equal(path.length - 1, field.dist[index(path[0])]);
    assert.ok(path.some((p, n) => n > 0 && p.row !== path[n - 1].row));
    path.slice(1).forEach((p, n) => {
      assert.equal(Math.abs(p.col - path[n].col) + Math.abs(p.row - path[n].row), 1);
      assert.equal(field.blocked.has(index(p)), false);
    });
    assert.deepEqual(tracePath(field, MAP.entrances[i]), path);
  });
  assert.deepEqual(tracePath(field, MAP.rocks[0]), []);
  assert.deepEqual(tracePath(field, { col: -1, row: 0 }), []);
});

test('配置で迂回が伸び、完全な壁は拒否される', () => {
  const initial = createField([]);
  const extension = placementCheck([], [], 4, 4);
  assert.equal(extension.ok, true);
  assert.ok(extension.paths[0].length > entrancePaths(initial)[0].length);
  const towers = [4, 5, 6].map(row => ({ col: 4, row }));
  const snapshot = structuredClone(towers);
  const result = placementCheck(towers, [], 4, 7);
  assert.equal(result.ok, false);
  assert.ok(result.paths.some(p => p.length === 0));
  assert.deepEqual(towers, snapshot);
});

test('整数・範囲・予約列・岩・重複・存在しない移設元を検証する', () => {
  for (const [col, row] of [[0, 0], [11, 0], [-1, 0], [12, 0], [3, -1], [3, 8], [2.1, 1], [2, NaN], [4, 1]]) {
    assert.equal(placementCheck([], [], col, row).ok, false);
  }
  assert.equal(placementCheck([{ col: 3, row: 3 }], [], 3, 3).ok, false);
  assert.equal(placementCheck([], [], 3, 3, { col: 2, row: 2 }).ok, false);
});

test('通過中の辺の両端を保護し、敵だけが閉じ込められる配置も拒否する', () => {
  const enemy = { alive: true, spawnAt: 0, cell: { col: 6, row: 6 }, nextCell: { col: 6, row: 5 } };
  const snapshot = structuredClone(enemy);
  assert.equal(placementCheck([], [enemy], 6, 6).ok, false);
  assert.equal(placementCheck([], [enemy], 6, 5).ok, false);
  const trapped = { ...enemy, nextCell: null };
  const around = [{ col: 5, row: 6 }, { col: 7, row: 6 }, { col: 6, row: 7 }];
  const result = placementCheck(around, [trapped], 6, 5);
  assert.equal(result.ok, false);
  assert.ok(result.paths.every(p => p.length));
  assert.deepEqual(enemy, snapshot);
});

test('移設は元を除いた最終盤面で検証され、失敗時も原子的', () => {
  const towers = [0, 1, 2, 3, 5, 6, 7].map(row => ({ col: 6, row }));
  const snapshot = structuredClone(towers);
  assert.equal(placementCheck(towers, [], 6, 4).ok, false);
  const moved = placementCheck(towers, [], 6, 4, { col: 6, row: 3 });
  assert.equal(moved.ok, true);
  assert.equal(moved.field.blocked.has(3 * 12 + 6), false);
  assert.equal(moved.field.blocked.has(4 * 12 + 6), true);
  assert.equal(placementCheck(towers, [], 6, 5, { col: 6, row: 3 }).ok, false);
  assert.deepEqual(towers, snapshot);
});

test('死体・未出現は占有せず、未出現でも入口の閉鎖は許可しない', () => {
  const enemies = [
    { alive: false, spawnAt: 0, cell: { col: 3, row: 3 } },
    { alive: true, spawnAt: 2, cell: { col: 3, row: 3 } },
  ];
  assert.equal(placementCheck([], enemies, 3, 3).ok, true);
  assert.equal(placementCheck([4, 5, 6].map(row => ({ col: 4, row })), enemies, 4, 7).ok, false);
});

test('XY連続移動と複数セルの時間消費、出口のちょうど到達を処理する', () => {
  const field = createField([]);
  const enemy = makeEnemy(field);
  const initialDistance = enemy.distanceToGoal;
  stepMazeEnemies([enemy], .25, .25, field);
  near(enemy.x, .75);
  near(enemy.y, 1.5);
  near(enemy.distanceToGoal, initialDistance - .25);
  stepMazeEnemies([enemy], 4.25, 4.5, field);
  const path = tracePath(field, MAP.entrances[0]);
  near(enemy.x, (path[4].col + path[5].col) / 2 + .5);
  near(enemy.y, (path[4].row + path[5].row) / 2 + .5);
  near(enemy.distanceToGoal, initialDistance - 4.5);
  stepMazeEnemies([enemy], initialDistance - 4.5, initialDistance, field);
  assert.equal(enemy.reached, true);
  assert.equal(enemy.alive, false);
  near(enemy.distanceToGoal, 0);
  near(enemy.x, 11.5);
  near(enemy.y, 4.5);
});

test('再配置で経路が変わっても横断完了までは次セルを固定する', () => {
  const field = createField([]);
  const enemy = makeEnemy(field);
  stepMazeEnemies([enemy], .4, .4, field);
  const next = { ...enemy.nextCell };
  const changed = placementCheck([], [enemy], 2, 1);
  assert.equal(changed.ok, true);
  refreshDistances([enemy], changed.field);
  near(enemy.distanceToGoal, changed.field.dist[index(next)] + .6);
  stepMazeEnemies([enemy], .2, .6, changed.field);
  assert.deepEqual(enemy.nextCell, next);
  near(enemy.x, 1.1);
  near(enemy.y, 1.5);
});

test('逆向き移動でも残距離は次セルからの経路長と残りの辺の長さ', () => {
  const field = createField([]);
  const enemy = { alive: true, spawnAt: 0, realSpeed: 1, cell: { col: 6, row: 4 }, nextCell: { col: 5, row: 4 }, x: 6.2, y: 4.5 };
  refreshDistances([enemy], field);
  near(enemy.distanceToGoal, field.dist[4 * 12 + 5] + .7);
  stepMazeEnemies([enemy], .2, .2, field);
  near(enemy.x, 6);
  near(enemy.distanceToGoal, field.dist[4 * 12 + 5] + .5);
});

test('出現待ちの残時間、死体、減速と期限切れを扱う', () => {
  const field = createField([]);
  const enemy = makeEnemy(field, { spawnAt: .75, slowUntil: 2, slowFactor: .5 });
  stepMazeEnemies([enemy], .5, .5, field);
  near(enemy.x, .5);
  near(enemy.spawnAt, .25);
  stepMazeEnemies([enemy], .5, 1, field);
  near(enemy.x, .625);
  stepMazeEnemies([enemy], .5, 2, field);
  near(enemy.x, 1.125);
  enemy.alive = false;
  const snapshot = structuredClone(enemy);
  stepMazeEnemies([enemy], 100, 102, field);
  assert.deepEqual(enemy, snapshot);
});
