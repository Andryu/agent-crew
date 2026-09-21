import test from 'node:test';
import assert from 'node:assert/strict';
import {
  newCampaign, createWave, scout, build, upgrade, recycle, relocate, launch, pulse,
  tick, observeDefense, observeBattle, score, TOTAL_WAVES, START_CREDITS, START_LIVES, STEP,
  COMBAT_SUPPLY, LIVE_MOVE_COST,
} from './campaign.js';
import { GRID, TOWERS, TOWER_ORDER } from './config.js';
import { stepTowers } from './towers.js';

function finishWave(state) {
  let frames = 0;
  while (state.phase === 'battle' && frames++ < 12000) tick(state);
  assert.notEqual(state.phase, 'battle', '実 tick でウェーブが制限時間内に終了する');
}

function near(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} ≈ ${expected}`);
}

test('初期状態と seed・難度の正規化', () => {
  const state = newCampaign({ seed: '42', difficulty: 'unknown' });
  assert.equal(state.seed, 42);
  assert.equal(state.difficulty, 'standard');
  assert.equal(state.phase, 'prepare');
  assert.equal(state.wave, 1);
  assert.equal(state.lives, START_LIVES);
  assert.equal(state.credits, START_CREDITS);
  assert.deepEqual(state.towers, []);
  const hard = newCampaign({ seed: 42, difficulty: 'challenge' });
  state.plan.enemies.forEach((enemy, i) => near(hard.plan.enemies[i].hp, enemy.hp * 1.3));
});

test('同 seed・同防衛の生成と実戦は再現し、異 seed は個体が変わる', () => {
  const run = seed => {
    const state = newCampaign({ seed });
    for (const row of [0, 3, 6]) assert.equal(build(state, 'basic', 3, row), true);
    assert.equal(launch(state), true);
    finishWave(state);
    return state;
  };
  const a = run(1234);
  assert.deepEqual(a, run(1234));
  assert.notDeepEqual(newCampaign({ seed: 1234 }).plan.enemies, newCampaign({ seed: 1235 }).plan.enemies);
  assert.equal(a.phase, 'prepare');
  assert.deepEqual(a.plan, createWave(1234, 2, a.observation));
});

test('偵察人数・耐性・精鋭数は生成された全個体の実数と一致する', () => {
  for (const id of TOWER_ORDER) {
    const observation = observeDefense([{ id, col: 2, row: 0, level: 1 }]);
    for (const wave of [2, 3, 9]) {
      const plan = createWave(987, wave, observation);
      const report = scout(plan);
      assert.equal(report.total, 16 + wave * 2);
      assert.deepEqual(report.lanes, [0, 1, 2].map(lane => plan.enemies.filter(e => e.lane === lane).length));
      assert.deepEqual(report.resist, [0, 1, 2, 3, 4].map(resist => plan.enemies.filter(e => (e.genome.armor ? 4 : e.genome.resist) === resist).length));
      assert.equal(report.elites, wave % 3 === 0 ? 2 : 0);
      assert.ok(report.resist[plan.resistant] >= Math.floor(report.total / 5) * 3);
      assert.ok(plan.enemies.every(e => !e.genome.armor || e.genome.resist === 0));
    }
  }
});

test('準備中の建設・強化・全額回収は偵察計画を変えず、資金を増殖させない', () => {
  const state = newCampaign({ seed: 23 });
  const plan = structuredClone(state.plan);
  const originalPlan = state.plan;
  for (let cycle = 0; cycle < 3; cycle++) {
    for (const id of TOWER_ORDER) {
      assert.equal(build(state, id, 2, 2), true);
      assert.equal(upgrade(state, 2, 2), true);
      assert.equal(upgrade(state, 2, 2), true);
      assert.equal(upgrade(state, 2, 2), false);
      assert.equal(recycle(state, 2, 2), true);
      assert.equal(recycle(state, 2, 2), false);
      assert.equal(state.credits, START_CREDITS);
      assert.equal(state.plan, originalPlan);
      assert.deepEqual(state.plan, plan);
    }
  }
});

function assertRejected(state, operation) {
  const before = structuredClone(state);
  delete before.lastError;
  const field = state.field;
  assert.equal(operation(), false);
  const after = structuredClone(state);
  delete after.lastError;
  assert.deepEqual(after, before, '拒否で lastError 以外の状態が変わらない');
  assert.equal(state.field, field, '拒否で経路場の参照を変更しない');
}

test('不正な配置・重複・資金不足の拒否は原子的', () => {
  const state = newCampaign();
  for (const [id, col, row] of [['bad', 2, 0], ['basic', -1, 0], ['basic', 12, 0], ['basic', 2, 8], ['basic', .5, 0], ['basic', 4, 2], ['basic', 8, 6], ...GRID.laneRows.map(row => ['basic', 0, row]), ['basic', 11, 4]]) {
    assertRejected(state, () => build(state, id, col, row));
    assert.ok(state.lastError);
  }
  for (const col of [2, 3, 5]) assert.equal(build(state, 'bolt', col, 2), true);
  assertRejected(state, () => build(state, 'basic', 2, 2));
  assertRejected(state, () => build(state, 'basic', 6, 2));
  assertRejected(state, () => upgrade(state, 2, 2));
  assert.equal(launch(state), true);
  assert.equal(state.credits, 60);
  assertRejected(state, () => launch(state));
  assert.equal(state.credits, 60);
  assert.equal(build(state, 'basic', 6, 2), true);
  assert.equal(state.credits, 10);
  assertRejected(state, () => relocate(state, 6, 2, 7, 2));
});

test('開始補給60Cはwaveごとに一度だけ受け取れ、戦闘中に建設できる', () => {
  const state = newCampaign();
  assert.equal(COMBAT_SUPPLY, 60);
  const initialPlan = structuredClone(state.plan);
  launch(state);
  assert.equal(state.credits, START_CREDITS + 60);
  assertRejected(state, () => launch(state));
  const paths = structuredClone(state.paths);
  assert.equal(build(state, 'basic', 1, 1), true);
  const tower = state.towers[0];
  assert.equal(tower.cooldown, TOWERS.basic.interval);
  assert.notDeepEqual(state.paths, paths, 'live建設で実際の経路が変わる');
  assert.deepEqual(state.plan, initialPlan, '個体数・耐性は道が変わっても不変');
  const hp = state.enemies[0].hp;
  tick(state);
  assert.equal(state.enemies[0].hp, hp, '新設直後は起動待ちで攻撃しない');
  near(tower.cooldown, TOWERS.basic.interval - STEP);
  for (let i = 0; i < 60; i++) tick(state);
  assert.ok(state.damageByType.basic > 0, '起動後は実戦に作用する');
});

test('移設は準備中無料、戦闘中15Cと0.8秒以上の起動待ちを課し強化CDを保持する', () => {
  const state = newCampaign();
  build(state, 'basic', 3, 2);
  upgrade(state, 3, 2);
  const credits = state.credits;
  const plan = structuredClone(state.plan);
  assert.equal(relocate(state, 3, 2, 5, 6), true);
  assert.equal(state.credits, credits);
  assert.equal(state.towers[0].level, 2);
  assert.deepEqual(state.plan, plan);
  launch(state);
  const tower = state.towers[0];
  const liveCredits = state.credits;
  assert.equal(LIVE_MOVE_COST, 15);
  assert.equal(relocate(state, 5, 6, 3, 2), true);
  assert.equal(state.credits, liveCredits - 15);
  assert.equal(tower.cooldown, .8);
  assert.equal(upgrade(state, 3, 2), true);
  assert.equal(tower.level, 3);
  assert.equal(tower.cooldown, .8);
  tower.cooldown = 1.2;
  assert.equal(relocate(state, 3, 2, 5, 6), true);
  assert.equal(tower.cooldown, 1.2, '移設で残CDを短縮しない');
  assert.equal(state.credits, liveCredits - 30 - 60);
  assert.deepEqual(state.plan, plan);
});

test('戦闘中の強化塔回収は投資額の70%で、再建設しても資金・CDは増殖しない', () => {
  for (const id of TOWER_ORDER) {
    const state = newCampaign();
    build(state, id, 2, 2);
    upgrade(state, 2, 2);
    upgrade(state, 2, 2);
    launch(state);
    const credits = state.credits;
    assert.equal(recycle(state, 2, 2), true);
    const refund = { basic: 105, heat: 210, cold: 210, bolt: 252 }[id];
    assert.equal(state.credits, credits + refund);
    assert.ok(state.credits < START_CREDITS + 60);
    assertRejected(state, () => recycle(state, 2, 2));
    assert.equal(build(state, id, 2, 2), true);
    assert.equal(state.towers[0].level, 1);
    assert.equal(state.towers[0].cooldown, TOWERS[id].interval);
  }
});

test('回収額は固定の金額表に一致し、90Cの70%を62Cへ切り下げない', () => {
  // 期待値は製品と同じ浮動小数点式で計算せず、仕様上の金額を固定する。
  const cases = [
    ['basic', 1, 50, 35], ['basic', 2, 90, 63], ['basic', 3, 150, 105],
    ['heat', 2, 180, 126], ['cold', 2, 180, 126], ['bolt', 2, 216, 151],
  ];
  for (const [id, level, invested, refund] of cases) {
    const state = newCampaign();
    assert.equal(build(state, id, 2, 2), true);
    for (let current = 1; current < level; current++) assert.equal(upgrade(state, 2, 2), true);
    assert.equal(START_CREDITS - state.credits, invested);
    launch(state);
    const before = state.credits;
    assert.equal(recycle(state, 2, 2), true);
    assert.equal(state.credits - before, refund, `${id} Lv${level}: ${invested}C → ${refund}C`);
  }
});

test('同一マスへの移設は準備中・戦闘中ともに拒否し、lastError以外を変更しない', () => {
  const state = newCampaign();
  assert.equal(build(state, 'basic', 2, 2), true);
  assertRejected(state, () => relocate(state, 2, 2, 2, 2));
  assert.ok(state.lastError);
  launch(state);
  state.towers[0].cooldown = .35;
  state.lastError = '';
  assertRejected(state, () => relocate(state, 2, 2, 2, 2));
  assert.ok(state.lastError);
});

test('閉鎖・占有マスへの建設や移設の失敗は資金・塔・CD・fieldを維持する', () => {
  const state = newCampaign();
  for (const row of [5, 6, 7]) assert.equal(build(state, 'basic', 4, row), true);
  assert.equal(build(state, 'basic', 2, 2), true);
  launch(state);
  assertRejected(state, () => build(state, 'basic', 4, 4));
  assertRejected(state, () => relocate(state, 2, 2, 4, 4));
  assert.match(state.lastError, /経路/);
  tick(state);
  const enemy = state.enemies[0];
  assert.ok(enemy.nextCell);
  const { col, row } = enemy.nextCell;
  assertRejected(state, () => build(state, 'basic', col, row));
  assertRejected(state, () => relocate(state, 2, 2, col, row));
  assert.match(state.lastError, /通過/);
  assertRejected(state, () => relocate(state, 2, 2, 4, 2));
  assertRejected(state, () => relocate(state, 10, 2, 3, 2));
});

test('戦闘の個体変更は次回偵察用の計画に影響しない', () => {
  const state = newCampaign();
  const before = structuredClone(state.plan);
  launch(state);
  state.enemies[0].genome.armor = true;
  for (let i = 0; i < 60; i++) tick(state);
  assert.deepEqual(state.plan, before);
});

test('装甲は無属性のみ半減し、属性耐性は一致する属性のみ半減する', () => {
  for (const id of TOWER_ORDER) {
    for (const armor of [false, true]) {
      for (const resist of [0, 1, 2, 3]) {
        const enemy = { x: 2.5, y: 1.5, distanceToGoal: 10, lane: 0, hp: 1000, alive: true, spawnAt: 0, genome: { armor, resist } };
        const shots = stepTowers([{ id, col: 2, row: 0, level: 1 }], [enemy], STEP, GRID.laneRows, STEP);
        assert.equal(shots.length, 1);
        const attr = { heat: 1, cold: 2, bolt: 3 }[id];
        const multiplier = (id === 'basic' ? armor : resist === attr) ? .5 : 1;
        near(1000 - enemy.hp, TOWERS[id].damage * multiplier);
      }
    }
  }
});

test('無配置と同率の防衛観測は決定的で、同率時は先頭属性・先頭レーンを選ぶ', () => {
  assert.deepEqual(observeDefense([]), {
    power: { basic: 0, heat: 0, cold: 0, bolt: 0 }, coverage: [0, 0, 0],
    dominant: null, weakest: 0, share: 0,
  });
  // basic 5 塔と cold 6 塔は推定 DPS がともに 60。盤外 fixture で coverage も同率にする。
  const towers = [
    ...Array.from({ length: 5 }, () => ({ id: 'basic', col: 0, row: 100 })),
    ...Array.from({ length: 6 }, () => ({ id: 'cold', col: 0, row: 100 })),
  ];
  const observation = observeDefense(towers);
  assert.equal(observation.power.basic, observation.power.cold);
  assert.equal(observation.dominant, 'basic');
  assert.equal(observation.share, .5);
  assert.equal(observation.weakest, 0);
  assert.deepEqual(observeDefense([...towers].reverse()), observation);
});

test('pulse は出現済みの指定レーンだけを3秒減速し、9秒間再使用できない', () => {
  const state = newCampaign();
  assert.equal(pulse(state, 0), false);
  launch(state);
  for (const lane of [-1, 3, .5, NaN]) assert.equal(pulse(state, lane), false);
  const enemy = state.enemies[0];
  const lane = enemy.lane;
  const beforeOthers = structuredClone(state.enemies.slice(1));
  assert.equal(pulse(state, lane), true);
  assert.equal(state.pulseReady, 9);
  assert.equal(enemy.slowUntil, 3);
  assert.equal(enemy.slowFactor, .2);
  assert.deepEqual(state.enemies.slice(1), beforeOthers);
  while (state.clock + STEP < 3) {
    const { x, y } = enemy;
    tick(state);
    near(Math.abs(enemy.x - x) + Math.abs(enemy.y - y), enemy.realSpeed * .2 * STEP);
    assert.equal(pulse(state, lane), false);
  }
  const { x, y } = enemy;
  tick(state);
  near(Math.abs(enemy.x - x) + Math.abs(enemy.y - y), enemy.realSpeed * STEP);
  while (state.clock + STEP < 9) {
    tick(state);
    assert.equal(pulse(state, lane), false);
  }
  tick(state);
  assert.equal(pulse(state, lane), true);
  near(state.pulseReady, state.clock + 9);
});

test('9 wave を実 tick で完走し、最終報酬・スコア・終端状態が確定する', () => {
  const state = newCampaign({ seed: 654 });
  // 遷移検証専用の高レベル塔。正規配置の勝率・難度を検証する fixture ではない。
  assert.equal(build(state, 'heat', 5, 3), true);
  state.towers[0].level = 40;
  for (let wave = 1; wave <= TOTAL_WAVES; wave++) {
    assert.equal(state.wave, wave);
    assert.equal(launch(state), true);
    finishWave(state);
    assert.equal(state.history.length, wave);
    assert.equal(state.history[wave - 1].kills, 16 + wave * 2);
    assert.equal(state.history[wave - 1].leaks, 0);
    assert.equal(state.phase, wave < TOTAL_WAVES ? 'prepare' : 'victory');
  }
  const totalEnemies = 234;
  assert.equal(state.kills, totalEnemies);
  assert.equal(state.lives, START_LIVES);
  assert.equal(state.credits, START_CREDITS - TOWERS.heat.cost + totalEnemies * 4 + 8 * 65 + 9 * 60);
  assert.equal(score(state), 2000 + 9 * 250 + totalEnemies * 10 + START_LIVES * 25);
  const before = structuredClone(state);
  tick(state);
  assert.equal(launch(state), false);
  assert.deepEqual(state, before);
});

test('無防衛は実 tick の到達被害で敗北し、敗北後に進行しない', () => {
  const state = newCampaign({ seed: 456 });
  launch(state);
  finishWave(state);
  assert.equal(state.lives, 6);
  assert.equal(state.phase, 'prepare');
  launch(state);
  finishWave(state);
  assert.equal(state.phase, 'defeat');
  assert.equal(state.lives, 0);
  assert.equal(state.totalLeaks, START_LIVES);
  assert.equal(state.kills, 0);
  assert.equal(score(state), 250);
  const before = structuredClone(state);
  tick(state);
  assert.equal(launch(state), false);
  assert.equal(pulse(state, 0), false);
  assert.deepEqual(state, before);
});

test('同時刻のlive操作と固定 tick を異なる描画バッチに分けても状態が一致する', () => {
  const run = batches => {
    const state = newCampaign({ seed: 55 });
    for (const row of [0, 3, 6]) build(state, 'basic', 2, row);
    launch(state);
    pulse(state, state.enemies[0].lane);
    let frame = 0;
    for (const count of batches) for (let i = 0; i < count; i++) {
      if (frame === 60) assert.equal(build(state, 'heat', 5, 3), true);
      if (frame === 120) assert.equal(upgrade(state, 5, 3), true);
      if (frame === 180) assert.equal(relocate(state, 5, 3, 6, 2), true);
      if (frame === 240) assert.equal(recycle(state, 6, 2), true);
      tick(state);
      frame++;
    }
    return state;
  };
  assert.deepEqual(run(Array(600).fill(1)), run(Array(100).fill(6)));
  assert.deepEqual(run(Array(600).fill(1)), run([17, 83, 1, 199, 300]));
});

test('実ダメージは過剰分を除外し、移設・売却後も次waveの適応に残る', () => {
  const state = newCampaign({ seed: 1 });
  assert.equal(build(state, 'bolt', 1, 3), true);
  launch(state);
  const first = state.enemies[0];
  const initialHp = first.hp;
  assert.equal(first.lane, 1);
  assert.ok(initialHp < TOWERS.bolt.damage, '過剰ダメージが発生する個体で検証する');
  tick(state);
  assert.equal(first.alive, false);
  near(state.damageByType.bolt, initialHp);
  assert.deepEqual(state.damageByLane, [0, initialHp, 0]);
  const recorded = observeBattle(state);
  assert.equal(recorded.dominant, 'bolt');
  assert.equal(recorded.share, 1);
  assert.equal(recorded.weakest, 0);
  assert.equal(relocate(state, 1, 3, 2, 3), true);
  assert.deepEqual(observeBattle(state), recorded);
  assert.equal(recycle(state, 2, 3), true);
  assert.equal(state.towers.length, 0);
  assert.deepEqual(observeBattle(state), recorded);
  finishWave(state);
  assert.equal(state.wave, 2);
  assert.deepEqual(state.observation, recorded);
  assert.deepEqual(state.history[0].observation, recorded);
  assert.equal(state.plan.resistant, 3);
  assert.equal(state.plan.weak, 0);
  const previousHistory = structuredClone(state.history);
  const credits = state.credits;
  launch(state);
  assert.equal(state.credits, credits + 60);
  assert.deepEqual(state.damageByType, { basic: 0, heat: 0, cold: 0, bolt: 0 });
  assert.deepEqual(state.damageByLane, [0, 0, 0]);
  assert.deepEqual(state.history, previousHistory, '次wave開始でも過去の実攻撃記録は保持する');
  assertRejected(state, () => launch(state));
});

test('実攻撃ゼロ・同率の観測と、出現元人数で正規化した損害から弱点を選ぶ', () => {
  const state = newCampaign();
  // 強い塔の配置だけでは適応は決まらない。
  build(state, 'bolt', 10, 0);
  assert.deepEqual(observeBattle(state), {
    power: { basic: 0, heat: 0, cold: 0, bolt: 0 }, coverage: [0, 0, 0],
    dominant: null, weakest: 0, share: 0,
  });
  state.plan.enemies = [0, 0, 1, 2].map(lane => ({ lane, genome: { resist: 0 } }));
  state.damageByType = { basic: 12, heat: 12, cold: 0, bolt: 0 };
  state.damageByLane = [8, 5, 4];
  assert.deepEqual(observeBattle(state), {
    power: { basic: 12, heat: 12, cold: 0, bolt: 0 }, coverage: [4, 5, 4],
    dominant: 'basic', weakest: 0, share: .5,
  });
});

test('XY射程・残距離優先の索敵と範囲攻撃の実ダメージ通知', () => {
  const enemy = (x, y, distanceToGoal, lane, hp = 100) => ({
    x, y, distanceToGoal, lane, hp, alive: true, spawnAt: 0,
    genome: { armor: false, resist: 0 },
  });
  const far = enemy(4.5, 3.5, 9, 0);
  const nearGoal = enemy(2.5, 3.5, 2, 2);
  const outside = enemy(3.5, 7.5, 1, 1);
  const shots = stepTowers([{ id: 'basic', col: 3, row: 3 }], [far, nearGoal, outside], STEP, GRID.laneRows);
  assert.equal(shots[0].x2, nearGoal.x, 'xが小さくても出口まで近い個体を狙う');
  assert.equal(nearGoal.hp, 94);
  assert.equal(far.hp, 100);
  assert.equal(outside.hp, 100, '出現元ではなく実Y座標で射程を判定する');

  const targets = [enemy(2.5, 3.5, 2, 0, 3), enemy(2.8, 3.5, 3, 2, 100), enemy(2.5, 5.5, 4, 0, 100)];
  targets[1].genome.resist = 1;
  const damage = [];
  stepTowers([{ id: 'heat', col: 3, row: 3 }], targets, STEP, GRID.laneRows, 0,
    (id, amount, target) => damage.push({ id, amount, lane: target.lane }));
  assert.deepEqual(damage, [{ id: 'heat', amount: 3, lane: 0 }, { id: 'heat', amount: 7, lane: 2 }]);
  assert.equal(targets[2].hp, 100, '同じ出現元でも離れた個体を範囲攻撃に含めない');
});
