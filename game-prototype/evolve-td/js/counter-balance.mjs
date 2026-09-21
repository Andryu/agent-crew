// 同じ生成済み群れ・同額投資で対抗策を比較する。レーンと属性を別々に測る。
import { newCampaign, createWave, build, launch, tick, observeDefense } from './campaign.js';
import { towerInvested } from './game-state.js';
const finish = s => { launch(s); let n = 0; while (s.phase === 'battle' && n++ < 10000) { tick(s); s.events.length = 0; } return { killed: s.waveKills, damage: s.waveLeaks }; };
const rows = [0, 2, 3, 5, 6];
const observation = observeDefense([{ id: 'basic', col: 4, row: 6, level: 2 }, { id: 'basic', col: 7, row: 3, level: 2 }]);
const result = [];
for(let seed=1;seed<=12;seed++) {
  const run = (kind) => {
    const s=newCampaign({seed}); s.wave=5; s.credits=300; s.plan=createWave(seed,5,observation);
    if(kind==='armor-ignored') for(const col of [2,3,5,6,9,10]) {build(s,'basic',col,3);}
    if(kind==='armor-countered') for(const col of [2,6,10]) {build(s,'heat',col,3);}
    if(kind==='lane-ignored') for(const col of [2,6,10]) {build(s,'heat',col,6);}
    const invested=s.towers.reduce((n,t)=>n+towerInvested(t),0);
    return {kind, invested, ...finish(s)};
  };
  result.push({seed, results:['armor-ignored','armor-countered','lane-ignored'].map(run)});
}
console.log(JSON.stringify(result,null,2));
