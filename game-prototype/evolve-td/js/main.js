// 画面と戦闘を分離し、描画速度によらず固定ステップで更新する。
import { GRID, TOWERS, TOWER_ORDER, RESIST_COLORS } from './config.js';
import { render, drawTowerIcon, renderGenomeIcon } from './renderer.js';
import { newCampaign, build, upgrade, recycle, relocate, launch, pulse, tick, scout, score, TOTAL_WAVES, STEP, LABELS, ROLES, LANES, RESIST_NAMES } from './campaign.js';
import { MAP, placementCheck } from './maze.js';
import { towerInvested, upgradeCost } from './game-state.js';
import { initAudio, playPlace, playKill, playHit, playWaveStart, setMuted, isMuted } from './audio.js';

const $ = id => document.getElementById(id);
const canvas = $('board-canvas');
const ctx = canvas.getContext('2d');
const screens = ['title', 'playing', 'result'];
const STORAGE = 'gunpen-live-maze-v3';
let state = null, screen = 'title', difficulty = 'standard', selected = 'basic', target = null;
let hover = null, keyboardCell = { col: 3, row: 2 }, speed = 1, paused = false, accumulator = 0, last = null;
let particles = [], toastTimer, lastKillSound = 0, records = {}, resultRecorded = false;
const suspended = () => paused || $('help-dialog').open || $('pause-dialog').open;
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
try { const data = JSON.parse(localStorage.getItem(STORAGE)); if (data && typeof data === 'object' && !Array.isArray(data)) records = data; } catch { /* 保存不可でもプレイを継続 */ }
const palette = $('tower-palette');
TOWER_ORDER.forEach((id, i) => {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'tower-slot'; button.dataset.towerId = id;
  button.innerHTML = `<span class="key">${i + 1}</span><span class="slot-top"><canvas width="64" height="64" aria-hidden="true"></canvas><span class="unit-name">${LABELS[id]}</span></span><span class="unit-role">${ROLES[id]}</span><span class="unit-cost">${TOWERS[id].cost} C</span>`;
  button.setAttribute('aria-label', `${LABELS[id]}、${ROLES[id]}、${TOWERS[id].cost}クレジット`);
  drawTowerIcon(button.querySelector('canvas').getContext('2d'), id, 64);
  button.addEventListener('click', () => select(id)); palette.append(button);
});
function updateRecord() {
  const values = Object.values(records).filter(r => Number.isFinite(r?.score));
  if (values.length) $('record').textContent = `保存中の自己ベスト ${Math.max(...values.map(r => Number.isFinite(r.bestScore) ? r.bestScore : r.score)).toLocaleString()} / 完了した作戦条件 ${values.length}件`;
}
updateRecord();

function toast(message) {
  $('toast').textContent = message; $('toast').classList.remove('hidden');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 2200);
}
function show(name) {
  screen = name;
  screens.forEach(id => $(`${id}-screen`).classList.toggle('hidden', id !== name));
  window.scrollTo({ top: 0, behavior: 'instant' });
}
function randomSeed() { const a = new Uint32Array(1); crypto.getRandomValues(a); return a[0]; }
function parseChallenge() {
  const params = new URLSearchParams(location.hash.slice(1));
  const seed = params.get('seed');
  if (seed === null || !/^\d{1,10}$/.test(seed) || Number(seed) > 0xffffffff) return null;
  return { seed: Number(seed), difficulty: params.get('mode') === 'challenge' ? 'challenge' : 'standard' };
}
const challenge = parseChallenge();
if (challenge) {
  difficulty = challenge.difficulty;
  $('start-button').innerHTML = '挑戦コードで開始 <span>↗</span>';
  $('record').textContent = `作戦コード ${challenge.seed} / ${difficulty === 'challenge' ? '挑戦' : '標準'}`;
}
function updateDifficulty() {
  document.querySelectorAll('[data-difficulty]').forEach(b => {
    const active = b.dataset.difficulty === difficulty;
    b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active));
  });
}
document.querySelectorAll('[data-difficulty]').forEach(b => b.addEventListener('click', () => { difficulty = b.dataset.difficulty; updateDifficulty(); }));
updateDifficulty();

function start(options = {}) {
  initAudio();
  state = newCampaign({ seed: options.seed ?? randomSeed(), difficulty: options.difficulty ?? difficulty });
  selected = 'basic'; target = null; hover = null; paused = false; speed = 1;
  accumulator = 0; last = null; particles = []; resultRecorded = false;
  $('pause-dialog').close(); $('help-dialog').close();
  $('share-status').textContent = '';
  show('playing'); update();
}
$('start-button').addEventListener('click', () => start({ seed: challenge?.seed, difficulty }));
$('retry-button').addEventListener('click', () => start({ seed: state.seed, difficulty: state.difficulty }));
$('new-button').addEventListener('click', () => start({ difficulty: state.difficulty }));
$('back-button').addEventListener('click', () => { state = null; paused = false; updateRecord(); show('title'); });

function update() {
  if (!state) return;
  const planning = state.phase === 'prepare';
  const editable = planning || state.phase === 'battle';
  $('playing-screen').classList.toggle('in-battle', !planning);
  $('operation-id').textContent = `OPERATION ${String(state.seed).padStart(8, '0')} / ${state.difficulty === 'challenge' ? 'CHALLENGE' : 'STANDARD'}`;
  $('phase-title').textContent = planning ? (state.wave === 1 ? '最初の防衛線' : '適応を読み、組み替える') : '群れ、接近中。';
  $('field-status').textContent = planning ? '防衛配置 / 待機中' : '防衛システム稼働';
  $('hud-lives').textContent = state.lives;
  $('hud-gold').textContent = state.credits;
  $('hud-wave').textContent = String(state.wave).padStart(2, '0');
  $('speed-button').textContent = `速度 ×${speed}`;
  $('wave-start-button').disabled = !planning;
  $('wave-start-button').innerHTML = planning ? `ウェーブ ${state.wave} を開始 <span>→</span>` : '防衛中 <span>◌</span>';
  $('build-note').textContent = planning ? '準備中の回収は100%還元' : '戦闘中も建設可能 / 移設15 C・回収70%';
  $('wave-track').innerHTML = Array.from({ length: TOTAL_WAVES }, (_, i) => `<div class="wave-node ${i + 1 === state.wave ? 'active' : i + 1 < state.wave ? 'done' : ''}">${String(i + 1).padStart(2, '0')}<span>${(i + 1) % 3 === 0 ? '大型種' : 'CONTACT'}</span></div>`).join('');
  document.querySelectorAll('.tower-slot').forEach(b => {
    b.disabled = !editable || state.credits < TOWERS[b.dataset.towerId].cost;
    b.classList.toggle('selected', editable && selected === b.dataset.towerId);
    b.setAttribute('aria-pressed', String(editable && selected === b.dataset.towerId));
  });
  const tower = target && state.towers.find(t => t.col === target.col && t.row === target.row);
  $('tower-actions').classList.toggle('hidden', !tower || !editable);
  if (tower && editable) {
    $('selection-description').textContent = `${LABELS[tower.id]} Lv.${tower.level} / 空マスで移設${planning ? '無料' : '15 C'} / 射程 ${(TOWERS[tower.id].range + .3 * (tower.level - 1)).toFixed(1)}`;
    $('upgrade-button').textContent = tower.level >= 3 ? '最大強化' : `強化 ${upgradeCost(tower)} C`;
    $('upgrade-button').disabled = tower.level >= 3 || state.credits < upgradeCost(tower);
    $('recycle-button').textContent = `回収 +${Math.floor(towerInvested(tower) * (planning ? 100 : 70) / 100)} C`;
  } else $('selection-description').textContent = selected ? `${LABELS[selected]}を配置 / ${ROLES[selected]}。連続配置できます。` : 'ユニットを選ぶか、配置済みユニットを選択。';
  updateIntel(); updatePulse();
}
function updateIntel() {
  const intel = scout(state.plan);
  $('enemy-total').textContent = intel.total;
  $('mobile-intel').textContent = `${intel.lanes.map((n, i) => `${LANES[i]} ${n}体`).join(' / ')} · ${state.plan.resistant ? RESIST_NAMES[state.plan.resistant] : '初回観測'}`;
  $('elite-badge').classList.toggle('hidden', !intel.elites);
  $('elite-badge').textContent = `大型種 ${intel.elites}`;
  $('lane-intel').innerHTML = intel.lanes.map((count, i) => `<div class="lane-row ${count === Math.max(...intel.lanes) ? 'weak' : ''}"><span>${LANES[i]}</span><div class="lane-bar"><i style="width:${count / intel.total * 100}%"></i></div><strong>${count}体</strong></div>`).join('');
  const colors = ['#8fa7b2', '#ef967e', '#7fb9e4', '#f2d574', '#c4b4ed'];
  $('resist-intel').innerHTML = intel.resist.map((count, i) => count ? `<span class="resist-chip" style="--chip:${colors[i]}"><i></i>${RESIST_NAMES[i]} ${count}</span>` : '').join('');
  $('adaptation-title').textContent = state.wave === 1 ? 'まだ、あなたを知らない。' : `${RESIST_NAMES[state.plan.resistant]}への適応`;
  $('adaptation-reason').textContent = state.plan.reason;
  const tips = ['塔は道を塞ぐ壁。合流点に火力を集め、遠回りと集中攻撃を組み合わせよう。', '赤い敵はフレアのダメージを半減。レールやパルスに切り替え、密集には減速を。', '青い敵はフロストのダメージを半減。攻撃をフレアやレールで補おう。', '黄色い敵はレールのダメージを半減。パルスやフレアで手数を増やそう。', '装甲はパルスのダメージを半減。フレア・フロスト・レールは装甲を無視。'];
  $('counter-tip').textContent = tips[state.plan.resistant] + (state.wave > 1 ? ` ${LANES[state.plan.weak]}の防衛を厚く。` : '');
  const previous = state.history.at(-1);
  $('last-report').textContent = previous ? `W${previous.wave}：${previous.kills}体撃破 / コア被害 ${previous.leaks}。${previous.leaks === 0 ? '完全防衛。次の適応にも備えよう。' : '抜けた群れの経路に射程と火力を集中しよう。'} 補給 +65 C。` : '4種類のユニットは最初から使用可能。初期資金 360 C。準備中は何度でも組み直せます。';
}
function updatePulse() {
  if (!state) return;
  const remaining = Math.max(0, state.pulseReady - state.clock);
  document.querySelectorAll('[data-pulse]').forEach(b => b.disabled = state.phase !== 'battle' || suspended() || remaining > 0);
  $('pulse-status').textContent = state.phase !== 'battle' ? '戦闘中に使用' : remaining > 0 ? `あと ${Math.ceil(remaining)} 秒` : '使用可能 / 3秒減速';
}
function select(id) {
  if (suspended() || !['prepare', 'battle'].includes(state?.phase) || state.credits < TOWERS[id].cost) return;
  selected = selected === id ? null : id; target = null; update();
}
function chooseCell(cell) {
  if (suspended() || !['prepare', 'battle'].includes(state?.phase)) return;
  keyboardCell = cell;
  const existing = state.towers.find(t => t.col === cell.col && t.row === cell.row);
  if (existing) { target = cell; selected = null; }
  else if (selected) {
    if (build(state, selected, cell.col, cell.row)) { playPlace(); target = null; }
    else toast(state.lastError);
  } else if (target) {
    if (relocate(state, target.col, target.row, cell.col, cell.row)) { target = cell; playPlace(); }
    else toast(state.lastError);
  }
  update();
}
function pointerCell(event) {
  const box = canvas.getBoundingClientRect();
  return { col: Math.floor((event.clientX - box.left) / box.width * GRID.cols), row: Math.floor((event.clientY - box.top) / box.height * GRID.rows) };
}
let touchPlacement = false;
canvas.addEventListener('pointerdown', event => {
  touchPlacement = event.pointerType === 'touch';
  hover = pointerCell(event);
  if (touchPlacement) canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove', event => hover = pointerCell(event));
canvas.addEventListener('pointerup', event => { if (event.pointerType === 'touch') { chooseCell(pointerCell(event)); hover = null; } });
canvas.addEventListener('pointercancel', () => { hover = null; });
canvas.addEventListener('contextmenu', event => event.preventDefault());
canvas.addEventListener('pointerleave', () => hover = null);
canvas.addEventListener('click', event => { if (!touchPlacement) chooseCell(pointerCell(event)); });
$('upgrade-button').addEventListener('click', () => { if (target && upgrade(state, target.col, target.row)) { playPlace(); update(); } });
$('recycle-button').addEventListener('click', () => { if (target && recycle(state, target.col, target.row)) { playPlace(true); target = null; update(); } });
$('wave-start-button').addEventListener('click', beginWave);
function beginWave() {
  if (suspended() || !state || !launch(state)) return;
  particles = []; accumulator = 0;
  toast('戦闘補給 +60 C。迎撃しながら道を変えよう。');
  playWaveStart(); update();
}
document.querySelectorAll('[data-pulse]').forEach(button => button.addEventListener('click', () => {
  if (!suspended() && pulse(state, Number(button.dataset.pulse))) { playWaveStart(); toast(`${LANES[Number(button.dataset.pulse)]}に緊急スロー`); updatePulse(); }
}));
$('speed-button').addEventListener('click', () => { speed = speed === 1 ? 2 : 1; update(); });
function pause() {
  if (!state || screen !== 'playing') return;
  paused = true; accumulator = 0;
  if (!$('pause-dialog').open) $('pause-dialog').showModal();
  updatePulse();
}
function resume() { paused = false; accumulator = 0; last = null; $('pause-dialog').close(); updatePulse(); }
$('pause-button').addEventListener('click', pause);
$('resume-button').addEventListener('click', resume);
$('pause-dialog').addEventListener('cancel', e => { e.preventDefault(); resume(); });
$('abandon-button').addEventListener('click', () => { $('pause-dialog').close(); state = null; paused = false; updateRecord(); show('title'); });
document.addEventListener('visibilitychange', () => { if (document.hidden && state?.phase === 'battle') pause(); });
$('help').addEventListener('click', () => { $('help-dialog').showModal(); accumulator = 0; });
function closeHelp() { $('help-dialog').close(); accumulator = 0; last = null; }
$('close-help').addEventListener('click', closeHelp); $('help-done').addEventListener('click', closeHelp);
$('help-dialog').addEventListener('cancel', e => { e.preventDefault(); closeHelp(); });
$('sound').addEventListener('click', () => { initAudio(); setMuted(!isMuted()); $('sound').textContent = isMuted() ? '音 OFF' : '音 ON'; $('sound').setAttribute('aria-pressed', String(isMuted())); $('sound').setAttribute('aria-label', isMuted() ? '音をオンにする' : '音をオフにする'); });
window.addEventListener('keydown', event => {
  if (screen !== 'playing' || suspended() || $('help-dialog').open || $('pause-dialog').open) return;
  if (event.key >= '1' && event.key <= '4') { event.preventDefault(); select(TOWER_ORDER[Number(event.key) - 1]); }
  if (event.key === 'Escape') { selected = null; target = null; update(); }
  if (event.key === ' ' && !['BUTTON', 'INPUT'].includes(document.activeElement?.tagName)) { event.preventDefault(); state.phase === 'prepare' ? beginWave() : pause(); }
  if (document.activeElement !== canvas) return;
  const deltas = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (deltas[event.key]) { event.preventDefault(); const [dx, dy] = deltas[event.key]; keyboardCell = { col: Math.max(0, Math.min(11, keyboardCell.col + dx)), row: Math.max(0, Math.min(7, keyboardCell.row + dy)) }; hover = keyboardCell; }
  if (event.key === 'Enter') { event.preventDefault(); chooseCell(keyboardCell); }
});
function result() {
  if (resultRecorded) return;
  resultRecorded = true;
  const won = state.phase === 'victory', points = score(state), key = `${state.seed}:${state.difficulty}`;
  const previous = records[key];
  $('result-emblem').textContent = won ? '◎' : '◈';
  $('result-emblem').style.color = won ? 'var(--mint)' : 'var(--orange)';
  $('result-code').textContent = won ? 'OPERATION COMPLETE / CORE SECURED' : 'SIGNAL LOST / RECONFIGURE';
  $('result-heading').textContent = won ? '適応を、超えた。' : '次は、読み勝てる。';
  $('result-description').textContent = won ? `9つの波を突破。コア耐久 ${state.lives} を残して防衛成功。` : `ウェーブ ${state.wave} でコアが停止。${state.plan.reason}`;
  $('result-stats').innerHTML = `<div><strong>${points.toLocaleString()}</strong><span>作戦スコア</span></div><div><strong>${state.kills}</strong><span>撃破個体</span></div><div><strong>${state.wave} / 9</strong><span>到達ウェーブ</span></div>`;
  $('previous-result').textContent = Number.isFinite(previous?.score) ? `同条件の前回 ${previous.score.toLocaleString()} → 今回 ${points.toLocaleString()}（${points - previous.score >= 0 ? '+' : ''}${points - previous.score}）` : '同じ条件でもう一度。防衛を変えれば、群れの適応も変わる。';
  // 再戦済み条件を末尾へ移し、直近スコアと条件別ベストを別々に保持する。
  delete records[key];
  const bestScore = Math.max(points, Number.isFinite(previous?.bestScore) ? previous.bestScore : (Number.isFinite(previous?.score) ? previous.score : 0));
  records[key] = { score: points, bestScore, wave: state.wave, victory: won };
  // 保存が無制限に増えないよう最新100作戦に絞る。
  const keys = Object.keys(records); keys.slice(0, Math.max(0, keys.length - 100)).forEach(k => delete records[k]);
  try { localStorage.setItem(STORAGE, JSON.stringify(records)); } catch { /* ブラウザの保存制限はゲームを止めない */ }
  show('result');
}
$('share-button').addEventListener('click', async () => {
  const url = `${location.origin}${location.pathname}#seed=${state.seed}&mode=${state.difficulty}`;
  try { await navigator.clipboard.writeText(url); $('share-status').textContent = '挑戦リンクをコピーしました。同じ初期条件で遊べます。'; }
  catch { $('share-status').textContent = url; }
});
function effects() {
  let hit = false;
  for (const event of state.events.splice(0)) {
    if (event.type === 'kill') {
      if (performance.now() - lastKillSound > 70) { playKill(); lastKillSound = performance.now(); }
      if (!reduced) for (let i = 0; i < 7; i++) { const a = Math.random() * Math.PI * 2; particles.push({ x: event.x * 48, y: event.y * 48, vx: Math.cos(a) * 45, vy: Math.sin(a) * 45, ttl: .4, life: .4, color: RESIST_COLORS[event.resist] }); }
    } else if (event.type === 'leak') hit = true;
  }
  if (hit) { playHit(); if (!reduced) canvas.animate([{ opacity: .5 }, { opacity: 1 }], { duration: 180 }); }
}
function draw() {
  if (!ctx || !state) return;
  ctx.setTransform(2, 0, 0, 2, 0, 0);
  const moving = target && state.towers.find(t => t.col === target.col && t.row === target.row);
  const preview = hover && (selected || moving) ? placementCheck(state.towers, state.enemies, hover.col, hover.row, moving ? target : null) : null;
  document.querySelector('.board-caption span:first-child').textContent = preview && !preview.ok ? preview.reason : '塔で道を曲げる / 戦闘中も建設可能';
  document.querySelector('.board-caption span:last-child').textContent = (preview?.ok ? preview.paths : state.paths).map((p,i) => `${['A','B','C'][i]} ${p.length-1}`).join(' / ') + ' マス';
  render(ctx, { maze: { paths: state.paths, rocks: MAP.rocks, previewPaths: preview?.paths, previewValid: preview?.ok }, towers: state.towers, enemies: state.phase === 'prepare' ? [] : state.enemies, shots: state.phase === 'battle' ? state.shots : [], particles,
    planning: ['prepare', 'battle'].includes(state.phase), lives: state.lives / 24 * 20, selectedCell: target, hoverCell: hover,
    rangePreview: hover && (selected || moving) ? { ...hover, towerId: selected || moving.id, level: moving?.level || 1 } : null });
  // 装甲と大型種を色だけに依存せず識別できる表示。
  if (state.phase !== 'prepare') for (const enemy of state.enemies) {
    if (!enemy.alive || enemy.spawnAt > 0) continue;
    const x = enemy.x * 48, y = enemy.y * 48;
    if (enemy.genome.armor) { ctx.strokeStyle = '#c4b4ed'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x - 7, y - 7); ctx.lineTo(x + 7, y - 7); ctx.lineTo(x + 6, y + 3); ctx.lineTo(x, y + 8); ctx.lineTo(x - 6, y + 3); ctx.closePath(); ctx.stroke(); }
    if (enemy.genome.elite) { ctx.fillStyle = '#f8b180'; ctx.font = 'bold 8px monospace'; ctx.textAlign = 'center'; ctx.fillText('ELITE', x, y - 23); }
  }
}
function hero(time) {
  const c = $('hero-canvas'), h = c.getContext('2d'); if (!h) return;
  h.clearRect(0, 0, c.width, c.height);
  const t = reduced ? 0 : time / 1600;
  h.strokeStyle = '#729f8720'; h.lineWidth = 1;
  [100, 160, 225].forEach(r => { h.beginPath(); h.arc(300, 260, r, 0, Math.PI * 2); h.stroke(); });
  for (let i = 0; i < 12; i++) { const a = i * Math.PI / 6; h.beginPath(); h.moveTo(300 + Math.cos(a) * 220, 260 + Math.sin(a) * 220); h.lineTo(300 + Math.cos(a) * 230, 260 + Math.sin(a) * 230); h.stroke(); }
  const points = [[280,250,64],[390,205,43],[207,160,38],[190,321,40],[345,351,47],[407,304,26],[295,120,22],[142,240,23],[365,113,15],[452,360,16],[132,360,12]];
  points.forEach(([cx, cy, radius], i) => {
    const x = cx + Math.sin(t + i) * 4, y = cy + Math.cos(t * .8 + i) * 5;
    h.strokeStyle = '#91d8b829'; h.beginPath(); h.moveTo(280, 250); h.lineTo(x, y); h.stroke();
    h.save(); h.translate(x, y); h.rotate(i + t * .025);
    const g = h.createRadialGradient(-radius * .25, -radius * .25, 2, 0, 0, radius);
    g.addColorStop(0, '#669c7e'); g.addColorStop(.55, '#315545'); g.addColorStop(.85, '#18372c'); g.addColorStop(1, '#7dc8a8');
    h.fillStyle = g; h.strokeStyle = '#ade9c9'; h.lineWidth = 1.2; h.shadowBlur = 22; h.shadowColor = '#6de6a746';
    h.beginPath(); for (let n = 0; n <= 60; n++) { const a = n / 60 * Math.PI * 2; const r = radius * (1 + Math.sin(a * 7 + i) * .065); n ? h.lineTo(Math.cos(a) * r, Math.sin(a) * r) : h.moveTo(r, 0); } h.closePath(); h.fill(); h.stroke(); h.shadowBlur = 0;
    h.fillStyle = '#bdffd98c'; for (let n = 0; n < 8; n++) { const a = n * 2.4 + i; const r = radius * (.25 + n % 3 * .15); h.beginPath(); h.ellipse(Math.cos(a) * r, Math.sin(a) * r, radius * .1, radius * .06, a, 0, Math.PI * 2); h.fill(); }
    h.strokeStyle = '#a5e9c850'; h.beginPath(); h.ellipse(-radius * .12, radius * .05, radius * .4, radius * .3, .5, 0, Math.PI * 2); h.stroke(); h.restore();
  });
}
function frame(time) {
  const dt = Math.min(.1, Math.max(0, (time - (last ?? time)) / 1000)); last = time;
  if (screen === 'title') hero(time);
  if (screen === 'playing' && state) {
    if (!suspended() && state.phase === 'battle') {
      accumulator += dt * speed;
      const before = state.phase;
      while (accumulator >= STEP && state.phase === 'battle') { tick(state); accumulator -= STEP; }
      effects();
      if (state.phase !== before) {
        accumulator = 0;
        if (state.phase === 'victory' || state.phase === 'defeat') result();
        else { update(); toast(`W${state.wave - 1} 完了。次の適応を偵察しました。`); }
      }
      if ($('hud-gold').textContent !== String(state.credits)) update();
      $('hud-lives').textContent = state.lives; updatePulse();
    }
    if (!suspended()) particles = particles.filter(p => { p.x += p.vx * dt; p.y += p.vy * dt; p.ttl -= dt; return p.ttl > 0; });
    draw();
  }
  requestAnimationFrame(frame);
}
if (!ctx) { $('start-button').disabled = true; $('record').textContent = 'このブラウザはCanvas描画に対応していません。別のブラウザでお試しください。'; }
requestAnimationFrame(frame);
