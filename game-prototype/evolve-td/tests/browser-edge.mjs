// 一時停止の重なり、保存制限、記録更新順を実ブラウザで回帰検証する。
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const { default: puppeteer } = await import(process.env.PUPPETEER_MODULE || 'puppeteer-core');
const browser = await puppeteer.launch({ executablePath: process.env.CHROME_EXECUTABLE, headless: true, args: ['--no-sandbox'] });
const url = process.env.GAME_URL || 'http://127.0.0.1:8768/';
const evidence = new URL('../../../docs/plans/evolve-td-evidence/', import.meta.url).pathname;
const errors = [], checks = [];
async function setup(page) {
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewport({ width: 1280, height: 900 });
  await page.evaluateOnNewDocument(() => {
    let callbacks = [], clock = 0;
    window.requestAnimationFrame = fn => { callbacks.push(fn); return callbacks.length; };
    window.testFrames = count => {
      for (let i = 0; i < count; i++) {
        clock += 100;
        const batch = callbacks; callbacks = [];
        batch.forEach(fn => fn(clock));
      }
    };
  });
}
const frames = (page, count) => page.evaluate(count => window.testFrames(count), count);
async function defeat(page, seed) {
  await page.goto(`${url}#seed=${seed}`);
  // 同一ページのhash変更だけでは再読込されないため、独立した起動として読み直す。
  await page.reload();
  await page.click('#start-button');
  for (let i = 0; i < 3; i++) {
    await page.click('#wave-start-button');
    await frames(page, 800);
    if (!(await page.$eval('#result-screen', e => e.classList.contains('hidden')))) break;
  }
  assert.equal(await page.$eval('#result-heading', e => e.textContent), '次は、読み勝てる。');
}
try {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await setup(page);
  await page.goto(`${url}#seed=42`); await page.click('#start-button');
  // 実ポインター移設で配置数・資金・強化が保たれる。
  async function cell(col, row) {
    const p = await page.$eval('#board-canvas', (e, { col, row }) => {
      const r = e.getBoundingClientRect();
      return { x: r.left + (col + .5) * r.width / 12, y: r.top + (row + .5) * r.height / 8 };
    }, { col, row });
    await page.mouse.click(p.x, p.y);
  }
  await cell(3, 2); await cell(3, 2); await page.click('#upgrade-button');
  const beforeMove = await page.$eval('#hud-gold', e => e.textContent);
  await cell(5, 6);
  assert.equal(await page.$eval('#hud-gold', e => e.textContent), beforeMove);
  assert.match(await page.$eval('#selection-description', e => e.textContent), /Lv.2/);
  await page.click('#recycle-button');
  assert.equal(await page.$eval('#hud-gold', e => e.textContent), '360');
  checks.push('実ポインターによるLv2無料移設・強化費込み回収');
  await page.click('#wave-start-button'); await frames(page, 20); await page.click('#help');
  const frozen = await page.$eval('.hud', e => e.textContent);
  // 別タブを前面へ出し、本物のvisibilitychangeを発生させる。
  const other = await context.newPage(); await other.goto('about:blank'); await other.bringToFront();
  assert.equal(await page.evaluate(() => document.hidden), true);
  assert.equal(await page.$eval('#pause-dialog', e => e.open), true);
  await page.bringToFront(); await page.click('#resume-button');
  assert.equal(await page.$eval('#help-dialog', e => e.open), true);
  await frames(page, 800);
  assert.equal(await page.$eval('.hud', e => e.textContent), frozen);
  await page.click('#help-done'); await frames(page, 800);
  assert.notEqual(await page.$eval('.hud', e => e.textContent), frozen);
  await other.close();
  checks.push('実タブ非表示で自動停止・説明と中断の重複中は進行せず');
  // 100件の旧記録を投入し、再戦条件が最終使用順へ移ることを確認。
  await page.evaluate(() => {
    const fixtures = {};
    for (let i = 0; i < 100; i++) fixtures[`${i}:standard`] = { score: i === 0 ? 9999 : i, wave: 9, victory: true };
    localStorage.setItem('gunpen-live-maze-v3', JSON.stringify(fixtures));
  });
  await defeat(page, 0); await defeat(page, 100);
  const records = await page.evaluate(() => JSON.parse(localStorage.getItem('gunpen-live-maze-v3')));
  assert.equal(Object.keys(records).length, 100);
  assert.ok(records['0:standard']); assert.ok(records['100:standard']); assert.equal(records['1:standard'], undefined);
  assert.equal(records['0:standard'].bestScore, 9999);
  assert.ok(records['0:standard'].score < 9999);
  await page.click('#back-button');
  assert.match(await page.$eval('#record', e => e.textContent), /9,999/);
  checks.push('100件上限・直近再戦保持・自己ベスト維持・タイトル即更新');
  await defeat(page, 42); await page.click('#new-button');
  assert.equal(await page.$eval('#hud-wave', e => e.textContent), '01');
  assert.equal(await page.$eval('#hud-gold', e => e.textContent), '360');
  assert.ok(!(await page.$eval('#operation-id', e => e.textContent)).includes('00000042'));
  checks.push('新作戦ボタンで新seed・初期資金に戻る');
  await context.close();
  // 保存APIが読み書きとも拒否される環境で結果まで進める。
  const noStorageContext = await browser.createBrowserContext();
  const noStorage = await noStorageContext.newPage(); await setup(noStorage);
  await noStorage.evaluateOnNewDocument(() => Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Storage disabled', 'SecurityError'); } }));
  await defeat(noStorage, 5);
  await noStorage.click('#retry-button');
  assert.equal(await noStorage.$eval('#hud-gold', e => e.textContent), '360');
  checks.push('localStorageの読み書き拒否でも開始・結果・再戦できる');
  // キーボードのみで配置可能。選択中basicでEnterし移設/回収に進める。
  await noStorage.focus('#board-canvas'); await noStorage.keyboard.press('Enter');
  assert.equal(await noStorage.$eval('#hud-gold', e => e.textContent), '310');
  await noStorage.keyboard.press('ArrowDown'); await noStorage.keyboard.press('Enter');
  assert.equal(await noStorage.$eval('#hud-gold', e => e.textContent), '260');
  checks.push('キーボード盤面フォーカス・矢印移動・連続配置');
  await noStorageContext.close();
  assert.deepEqual(errors, []);
  await fs.writeFile(evidence + 'browser-edge.json', JSON.stringify({ checks, errors }, null, 2));
  console.log(JSON.stringify({ checks, errors }, null, 2));
} finally { await browser.close(); }
