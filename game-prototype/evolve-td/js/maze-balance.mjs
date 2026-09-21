// 同じseed・予算・塔種で、遠回り偏重と射程集中を比較する実戦実験。
import {newCampaign,createWave,build,launch,tick} from './campaign.js';
import {placementCheck} from './maze.js';
function run(seed,strategy,composition='basic'){
 const ids=composition==='mixed'?['heat','cold','basic','basic','basic']:Array(7).fill('basic');
 const s=newCampaign({seed});s.wave=4;s.plan=createWave(seed,4,null);
 for(const id of ids){
  let candidates=[];
  for(let row=0;row<8;row++)for(let col=1;col<11;col++){
   const c=placementCheck(s.towers,[],col,row);if(!c.ok)continue;
   const length=c.paths.reduce((n,p)=>n+p.length,0);
   const coverage=[...s.towers,{col,row,id}].reduce((sum,t)=>sum+c.paths.reduce((n,p)=>n+p.filter(v=>Math.hypot(v.col-t.col,v.row-t.row)<=(t.id==='cold'?2.5:2)).length,0),0);
   candidates.push({col,row,value:strategy==='length'?length:coverage});
  }
  candidates.sort((a,b)=>b.value-a.value);build(s,id,candidates[0].col,candidates[0].row);
 }
 const layout=s.towers.map(({col,row})=>[col,row]),lengths=s.paths.map(p=>p.length-1);launch(s);
 let frames=0;while(s.phase==='battle'&&frames++<12000){tick(s);s.events.length=0;}
 return {seed,strategy,composition,budget:350,layout,lengths,kills:s.kills,leaks:s.totalLeaks,seconds:+s.clock.toFixed(2)};
}
console.log(JSON.stringify(['basic','mixed'].flatMap(composition=>[1,7,42].flatMap(seed=>['length','coverage'].map(strategy=>run(seed,strategy,composition)))),null,2));
