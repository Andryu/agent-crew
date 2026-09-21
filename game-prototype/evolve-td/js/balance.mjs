// 実際の戦闘更新を使う固定seed比較。代理fitnessではなくコア被害を記録。
import { newCampaign, build, upgrade, recycle, launch, tick, scout, score } from './campaign.js';
import { placementCheck } from './maze.js';
import { TOWERS, GRID } from './config.js';
import { upgradeCost } from './game-state.js';

export function deploy(s, strategy = 'adaptive') {
  const adaptive = strategy === 'adaptive';
  if (adaptive) [...s.towers].forEach(t => recycle(s, t.col, t.row));
  const ids = adaptive ? (s.plan.resistant === 4 ? ['heat', 'bolt', 'cold'] : s.plan.resistant === 1 ? ['bolt', 'basic', 'cold'] : s.plan.resistant === 3 ? ['heat', 'basic', 'cold'] : ['heat', 'bolt', 'basic']) : ['basic'];
  for (let attempt = 0; attempt < 70; attempt++) {
    let id = ids[s.towers.length % ids.length];
    if (s.credits < TOWERS[id].cost) id = 'basic';
    const candidates = [];
    if (s.credits >= TOWERS[id].cost) for (let row = 0; row < 8; row++) for (let col = 1; col < 11; col++) {
      const check = placementCheck(s.towers, s.enemies, col, row);
      if (!check.ok) continue;
      // 道の長さではなく、候補塔と既存火力が道を射程に収める量で配置する。
      const coverage = check.paths.reduce((sum,path) => sum + path.filter(p => Math.hypot(p.col-col,p.row-row) <= TOWERS[id].range).length, 0);
      const support = s.towers.reduce((sum,t) => sum + check.paths.reduce((n,path) => n + path.filter(p => Math.hypot(p.col-t.col,p.row-t.row)<=TOWERS[t.id].range).length,0),0);
      candidates.push({col,row,value:coverage+support*.18});
    }
    candidates.sort((a,b)=>b.value-a.value);
    if(candidates.length && build(s,id,candidates[0].col,candidates[0].row)) continue;
    const candidate = s.towers.filter(t=>t.level<3 && s.credits>=upgradeCost(t)).sort((a,b)=>a.level-b.level)[0];
    if(candidate && upgrade(s,candidate.col,candidate.row)) continue;
    break;
  }
}
export function simulate(seed, strategy = 'adaptive', difficulty = 'standard') {
  const state = newCampaign({ seed, difficulty });
  let ticks = 0;
  while (!['victory', 'defeat'].includes(state.phase) && ticks < 60000) {
    if (state.phase === 'prepare') { deploy(state, strategy); launch(state); }
    tick(state); state.events.length = 0; ticks++;
  }
  return { seed, strategy, outcome: state.phase, wave: state.wave, lives: state.lives, leaks: state.totalLeaks, score: score(state), seconds: +(ticks / 60).toFixed(1) };
}
if (process.argv[1]?.endsWith('balance.mjs')) {
  const results = Array.from({ length: 12 }, (_, i) => [simulate(i + 1, 'static'), simulate(i + 1, 'adaptive')]).flat();
  console.log(JSON.stringify(results, null, 2));
}
