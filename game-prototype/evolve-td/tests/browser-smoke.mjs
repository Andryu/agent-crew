const { default: puppeteer } = await import(process.env.PUPPETEER_MODULE || 'puppeteer-core');
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {newCampaign,launch,tick,score} from '../js/campaign.js';
import {deploy} from '../js/balance.mjs';
const evidence=new URL('../../../docs/plans/evolve-td-evidence/', import.meta.url).pathname;
await fs.mkdir(evidence,{recursive:true});
const gameUrl=process.env.GAME_URL || 'http://127.0.0.1:8768/';
const browser=await puppeteer.launch({executablePath:process.env.CHROME_EXECUTABLE,headless:true,args:['--no-sandbox']});
try {
const page=await browser.newPage(); const errors=[],checks=[];
page.on('pageerror',e=>errors.push(e.message));
await page.evaluateOnNewDocument(()=>{let callbacks=[],clock=0;window.requestAnimationFrame=fn=>{callbacks.push(fn);return callbacks.length;};window.testFrames=(n,step=100)=>{for(let i=0;i<n;i++){clock+=step;const queue=callbacks;callbacks=[];queue.forEach(fn=>fn(clock));}};});
const frames=n=>page.evaluate(n=>window.testFrames(n),n);
const clickCell=async(col,row)=>{await page.evaluate(({col,row})=>{const c=document.querySelector('#board-canvas'),r=c.getBoundingClientRect();c.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:r.left+(col+.5)*r.width/12,clientY:r.top+(row+.5)*r.height/8}));},{col,row});};
await page.setViewport({width:1440,height:1050});
await page.goto(gameUrl+'#seed=42');await frames(1);
await page.screenshot({path:evidence+'title-desktop.png',fullPage:true});
await page.click('#help');assert.equal(await page.$eval('#help-dialog',e=>e.open),true);await page.click('#help-done');checks.push('タイトルの遊び方');
await page.click('#start-button');await frames(1);
assert.equal(await page.$eval('#hud-gold',e=>e.textContent),'360');
// 通常のポインター操作で配置、強化、全額回収。
const box=await page.$eval('#board-canvas',e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height};});
await page.mouse.click(box.x+3.5*box.w/12,box.y+2.5*box.h/8);
assert.equal(await page.$eval('#hud-gold',e=>e.textContent),'310');
await clickCell(3,2);await page.click('#upgrade-button');assert.equal(await page.$eval('#hud-gold',e=>e.textContent),'270');
await page.click('#recycle-button');assert.equal(await page.$eval('#hud-gold',e=>e.textContent),'360');checks.push('実ポインター配置・強化・全額回収');
await page.click('#pause-button');await frames(40);assert.equal(await page.$eval('#pause-dialog',e=>e.open),true);await page.click('#resume-button');checks.push('準備中断と再開');
const ref=newCampaign({seed:42});let previous=[];
for(let wave=1;wave<=9;wave++){
  deploy(ref);
  for(const t of previous){await clickCell(t.col,t.row);await page.click('#recycle-button');}
  for(const t of ref.towers){
    await page.evaluate(id=>{const b=document.querySelector(`[data-tower-id="${id}"]`);if(b.getAttribute('aria-pressed')!=='true')b.click();},t.id);
    await clickCell(t.col,t.row);
    if(t.level>1){await clickCell(t.col,t.row);for(let lv=1;lv<t.level;lv++)await page.click('#upgrade-button');}
  }
  assert.equal(Number(await page.$eval('#hud-gold',e=>e.textContent)),ref.credits);
  previous=ref.towers.map(t=>({...t}));await frames(1);
  if(wave===1)await page.screenshot({path:evidence+'defense-desktop.png',fullPage:true});
  await page.click('#wave-start-button');launch(ref);
  if(wave===1){
    await frames(20);await page.click('#pause-button');const life=await page.$eval('#hud-lives',e=>e.textContent);await frames(80);assert.equal(await page.$eval('#hud-lives',e=>e.textContent),life);await page.click('#resume-button');checks.push('戦闘一時停止・再開');
    await page.click('#speed-button');await frames(30);await page.screenshot({path:evidence+'battle-desktop.png',fullPage:true});await page.click('#speed-button');
  }
  await frames(700);
  let ticks=0;while(ref.phase==='battle'&&ticks++<10000){tick(ref);ref.events.length=0;}
  if(wave<9){assert.equal(Number(await page.$eval('#hud-wave',e=>e.textContent)),ref.wave);assert.equal(Number(await page.$eval('#hud-lives',e=>e.textContent)),ref.lives);}
}
assert.equal(ref.phase,'victory');assert.equal(await page.$eval('#result-heading',e=>e.textContent),'適応を、超えた。');
assert.ok((await page.$eval('#result-stats',e=>e.textContent)).includes(score(ref).toLocaleString()));checks.push('実UIで9wave勝利・速度切替でも参照戦闘と同スコア');
await page.screenshot({path:evidence+'victory-desktop.png',fullPage:true});
await page.click('#retry-button');assert.ok((await page.$eval('#operation-id',e=>e.textContent)).includes('00000042'));assert.equal(await page.$eval('#hud-gold',e=>e.textContent),'360');checks.push('勝利後同seed再挑戦');
// 無防衛で敗北し、結果比較を確認。
await page.click('#wave-start-button');await frames(800);if(await page.$eval('#result-screen',e=>e.classList.contains('hidden'))){await page.click('#wave-start-button');await frames(800);}
assert.equal(await page.$eval('#result-heading',e=>e.textContent),'次は、読み勝てる。');assert.ok((await page.$eval('#previous-result',e=>e.textContent)).includes('同条件の前回'));checks.push('敗北と前回比較');
await page.click('#retry-button');assert.ok((await page.$eval('#operation-id',e=>e.textContent)).includes('00000042'));checks.push('敗北後同seed再挑戦');
// モバイルはemulationで再読込されるので明示ナビゲーション。
await page.setViewport({width:390,height:844,isMobile:true,hasTouch:true});await page.goto(gameUrl+'#seed=42');await frames(1);
await page.screenshot({path:evidence+'title-mobile.png',fullPage:true});await page.tap('#start-button');await frames(1);
assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
await page.tap('[data-tower-id="heat"]');
const mobile=await page.$eval('#board-canvas',e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height};});
await page.touchscreen.tap(mobile.x+3.5*mobile.w/12,mobile.y+2.5*mobile.h/8);assert.equal(await page.$eval('#hud-gold',e=>e.textContent),'260');
await frames(1);await page.screenshot({path:evidence+'defense-mobile.png',fullPage:true});checks.push('390px横溢れなし・タップ配置');
await page.tap('#wave-start-button');await frames(30);await page.tap('[data-pulse="0"]');assert.equal(await page.$eval('[data-pulse="0"]',e=>e.disabled),true);checks.push('モバイル緊急スローとCD');
await page.tap('#sound');assert.equal(await page.$eval('#sound',e=>e.textContent),'音 OFF');checks.push('音切替');
assert.deepEqual(errors,[]);
await fs.writeFile(evidence+'browser-check.json',JSON.stringify({checks,errors,reference:{score:score(ref),lives:ref.lives}},null,2));
console.log(JSON.stringify({checks,errors,reference:{score:score(ref),lives:ref.lives}},null,2));
} finally { await browser.close(); }
