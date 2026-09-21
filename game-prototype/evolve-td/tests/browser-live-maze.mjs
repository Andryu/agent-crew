// 実ポインター/タッチだけで戦闘中配置と道変更を検証。製品状態は注入しない。
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const {default:puppeteer}=await import(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const browser=await puppeteer.launch({executablePath:process.env.CHROME_EXECUTABLE,headless:true,args:['--no-sandbox']});
const evidence=new URL('../../../docs/plans/evolve-td-evidence/',import.meta.url).pathname;
const checks=[],errors=[];
try {
const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));
await page.evaluateOnNewDocument(()=>{let q=[],t=0;requestAnimationFrame=f=>q.push(f);window.framesForTest=n=>{while(n--){t+=100;const batch=q;q=[];batch.forEach(f=>f(t));}};});
const frames=n=>page.evaluate(n=>window.framesForTest(n),n);
const cell=async(col,row,touch=false)=>{await page.$eval('#board-canvas',e=>e.scrollIntoView({block:'center'}));const p=await page.$eval('#board-canvas',(e,{col,row})=>{const r=e.getBoundingClientRect();return{x:r.x+(col+.5)*r.width/12,y:r.y+(row+.5)*r.height/8};},{col,row});if(touch)await page.touchscreen.tap(p.x,p.y);else await page.mouse.click(p.x,p.y);};
const gold=async()=>Number(await page.$eval('#hud-gold',e=>e.textContent));
const pathText=()=>page.$eval('.board-caption span:last-child',e=>e.textContent);
await page.setViewport({width:1440,height:1050});await page.goto((process.env.GAME_URL || 'http://127.0.0.1:8768/')+'#seed=42');await page.click('#start-button');await frames(1);
const original=await pathText();await page.click('#wave-start-button');await frames(20);
assert.equal(await gold(),420);assert.equal(await page.$eval('[data-tower-id="basic"]',e=>e.disabled),false);
await cell(5,4);await frames(1);assert.equal(await gold(),370);assert.notEqual(await pathText(),original);checks.push('戦闘開始2秒後に実ポインター建設、即時に道変更、開始補給60C');
await cell(5,4);await page.click('#upgrade-button');assert.equal(await gold(),330);
await cell(6,5);assert.equal(await gold(),315);assert.match(await page.$eval('#selection-description',e=>e.textContent),/Lv.2/);checks.push('戦闘中の強化と15C移設');
await page.click('#recycle-button');assert.equal(await gold(),378);checks.push('戦闘中Lv2回収63C（70%）');
await page.click('[data-tower-id="basic"]');await cell(4,2);assert.equal(await gold(),378);assert.match(await page.$eval('#toast',e=>e.textContent),/岩/);checks.push('岩への配置拒否と理由表示');
await cell(5,4);await cell(6,4);await frames(70);await page.screenshot({path:evidence+'live-maze-battle-desktop.png',fullPage:true});
await page.click('#pause-button');const frozen=await gold();await frames(100);assert.equal(await gold(),frozen);await page.click('#resume-button');checks.push('戦闘建設後の一時停止');
await page.setViewport({width:390,height:844,isMobile:true,hasTouch:true});await page.goto((process.env.GAME_URL || 'http://127.0.0.1:8768/')+'#seed=42');await page.reload();await page.tap('#start-button');await page.tap('#wave-start-button');await frames(20);
const beforePreview=await pathText();
await page.$eval('#board-canvas',e=>e.scrollIntoView({block:'center'}));
const pos=await page.$eval('#board-canvas',e=>{const r=e.getBoundingClientRect();return{x:r.x+5.5*r.width/12,y:r.y+4.5*r.height/8};});
await page.touchscreen.touchStart(pos.x,pos.y);await frames(2);
assert.equal(await gold(),420);assert.notEqual(await pathText(),beforePreview);
await page.screenshot({path:evidence+'live-maze-touch-preview.png',fullPage:true});
await page.touchscreen.touchEnd();await frames(1);assert.equal(await gold(),370);
checks.push('タッチを保持中に未課金で経路を予告し、離した時に1回だけ建設');
assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
assert.equal(await page.$eval('#tower-palette',e=>getComputedStyle(e).display==='none'),false);
await page.screenshot({path:evidence+'live-maze-battle-mobile.png',fullPage:true});checks.push('390pxで戦闘中タッチ建設・道変更・横溢れなし');
assert.deepEqual(errors,[]);await fs.writeFile(evidence+'browser-live-maze.json',JSON.stringify({checks,errors},null,2));console.log(JSON.stringify({checks,errors},null,2));
} finally {await browser.close();}
