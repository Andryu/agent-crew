// main.js
// 画面遷移・ゲームループ・入力（配置/売却/ボタン）を担当するエントリーポイント。
// CP2: 変異レポートmodal・次ウェーブプレビュー・発熱スキルを追加。
// CP3: チャレンジリンク・アンケート・音・粒子・吹き出しは実装しない。

import {
  GRID,
  TOWERS,
  TOWER_ORDER,
  ECONOMY,
  LANE_LENGTH,
  SKILL,
  WAVE_COUNT,
  killReward,
} from './config.js';
import { makeRng } from './rng.js';
import {
  startNewGame,
  canPlace,
  placeTower,
  sellTower,
  startWave,
  loseLives,
  endWave,
  closeReport,
  continueEndless,
  isCleared,
  isGameOver,
  skillUnlocked,
  useSkill,
} from './game-state.js';
import {
  spawnFromPopulation,
  stepEnemies,
  collectResults,
  livesLostFor,
  applyHeatToLane,
} from './enemies.js';
import { stepTowers } from './towers.js';
import { render, drawTowerIcon, renderGenomeIcon } from './renderer.js';
import { representative } from './evolution.js';

const screens = {
  title: document.getElementById('title-screen'),
  playing: document.getElementById('playing-screen'),
  result: document.getElementById('result-screen'),
};

const startButton = document.getElementById('start-button');
const canvas = document.getElementById('board-canvas');
const ctx = canvas.getContext('2d');
const hudGold = document.getElementById('hud-gold');
const hudLives = document.getElementById('hud-lives');
const hudWave = document.getElementById('hud-wave');
const sellButton = document.getElementById('sell-button');
const paletteEl = document.getElementById('tower-palette');
const paletteSlots = Array.from(document.querySelectorAll('.tower-slot'));
const waveStartButton = document.getElementById('wave-start-button');
const speedToggleButton = document.getElementById('speed-toggle-button');
const resultHeading = document.getElementById('result-heading');
const resultWaveCount = document.getElementById('result-wave-count');
const endlessButton = document.getElementById('endless-button');
const retryButton = document.getElementById('retry-button');
const titleFromResultButton = document.getElementById('title-from-result-button');
const previewPanel = document.getElementById('preview-panel');
const previewCanvases = Array.from(document.querySelectorAll('.preview-icon'));
const skillButton = document.getElementById('skill-button');
const skillLabel = document.getElementById('skill-label');
const skillSelectBanner = document.getElementById('skill-select-banner');
const reportModal = document.getElementById('report-modal');
const reportHeading = document.getElementById('report-heading');
const reportIntro = document.getElementById('report-intro');
const reportLinesEl = document.getElementById('report-lines');
const reportPrevCanvas = document.getElementById('report-prev-canvas');
const reportNextCanvas = document.getElementById('report-next-canvas');
const reportCloseButton = document.getElementById('report-close-button');

let state = null;
let screen = 'title'; // 'title' | 'playing' | 'result'（画面状態はここで管理。state.phaseはplace/wave/reportのみ）
let masterRng = null;
let enemies = [];
let activeShots = [];
let waveClock = 0;
let speedMultiplier = 1;
let selectedTowerId = null;
let sellTarget = null; // {col, row}
let flashCell = null; // {col, row, until}
let previousUnlocked = ['basic'];
let previousSkillUnlocked = false;
let lastTimestamp = null;
let loopRunning = false;
let skillSelectMode = false;
let laneFlash = null; // {lane, until}

if (!ctx) {
  const msg = document.createElement('p');
  msg.textContent = 'お使いのブラウザではこのゲームを表示できません。';
  document.getElementById('app').prepend(msg);
  startButton.disabled = true;
}

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    el.classList.toggle('hidden', key !== name);
  });
}

// --- 塔パレットアイコン初期描画（一度だけ） ---
paletteSlots.forEach((slot) => {
  const towerId = slot.dataset.towerId;
  const iconCanvas = slot.querySelector('.tower-icon');
  const iconCtx = iconCanvas.getContext('2d');
  if (iconCtx) drawTowerIcon(iconCtx, towerId, iconCanvas.width);
});

function updatePalette() {
  paletteSlots.forEach((slot) => {
    const towerId = slot.dataset.towerId;
    const def = TOWERS[towerId];
    const unlocked = state.unlocked.includes(towerId);
    const affordable = state.gold >= def.cost;
    slot.classList.toggle('locked', !unlocked);
    slot.classList.toggle('selected', selectedTowerId === towerId);
    slot.disabled = !unlocked || !affordable;
  });
}

function pulseNewlyUnlocked() {
  const newlyUnlocked = state.unlocked.filter((id) => !previousUnlocked.includes(id));
  paletteSlots.forEach((slot) => {
    if (newlyUnlocked.includes(slot.dataset.towerId)) {
      slot.classList.add('newly-unlocked');
      setTimeout(() => slot.classList.remove('newly-unlocked'), 2000);
    }
  });
  previousUnlocked = state.unlocked;

  const nowSkillUnlocked = skillUnlocked(state);
  if (nowSkillUnlocked && !previousSkillUnlocked) {
    skillButton.classList.add('newly-unlocked');
    setTimeout(() => skillButton.classList.remove('newly-unlocked'), 2000);
  }
  previousSkillUnlocked = nowSkillUnlocked;
}

function updateHud() {
  hudGold.textContent = `${state.gold}G`;
  hudLives.textContent = `♥ ${state.lives}`;
  // エンドレス中は分母(WAVE.../15)を出さない（wave16以降は15を超えるため）
  hudWave.textContent = state.endless ? `WAVE ${state.wave}` : `WAVE ${state.wave}/${WAVE_COUNT}`;
  speedToggleButton.disabled = state.phase !== 'wave';
}

function hideSellButton() {
  sellButton.classList.add('hidden');
  sellTarget = null;
}

// --- 発熱スキル ---

function updateSkillButton() {
  if (!state) return;
  const unlocked = skillUnlocked(state);
  skillButton.classList.toggle('locked', !unlocked);
  skillButton.classList.toggle('selecting', skillSelectMode);
  if (!unlocked) {
    skillButton.disabled = true;
    skillLabel.textContent = '発熱';
    return;
  }
  if (state.phase !== 'wave') {
    skillButton.disabled = true;
    skillLabel.textContent = '発熱';
    return;
  }
  const remaining = (state.skillReadyAt ?? 0) - waveClock;
  if (remaining > 0 && !skillSelectMode) {
    skillButton.disabled = true;
    skillLabel.textContent = `発熱 ${Math.ceil(remaining)}s`;
  } else {
    skillButton.disabled = false;
    skillLabel.textContent = '発熱';
  }
}

function enterSkillSelect() {
  skillSelectMode = true;
  skillSelectBanner.classList.remove('hidden');
  updateSkillButton();
}

function exitSkillSelect() {
  skillSelectMode = false;
  skillSelectBanner.classList.add('hidden');
  updateSkillButton();
}

function onSkillButtonPress() {
  if (!state) return;
  if (!skillUnlocked(state)) return;
  if (skillSelectMode) {
    exitSkillSelect();
    return;
  }
  if (state.phase !== 'wave') return;
  if (waveClock < (state.skillReadyAt ?? 0)) return;
  enterSkillSelect();
}

function rowToLane(row) {
  if (row <= 2) return 0;
  if (row <= 5) return 1;
  return 2;
}

function activateSkill(lane) {
  const before = state.skillReadyAt;
  state = useSkill(state, lane, waveClock);
  if (state.skillReadyAt === before) {
    // 条件を満たさず発動しなかった（CD未了 等）
    exitSkillSelect();
    return;
  }
  applyHeatToLane(enemies, lane, waveClock);
  laneFlash = { lane, until: waveClock + SKILL.laneFlashDuration };
  exitSkillSelect();
}

// --- 次ウェーブ・プレビュー ---

function renderPreview() {
  if (!state) return;
  const show = state.phase === 'place' && state.wave >= 2;
  previewPanel.classList.toggle('hidden', !show);
  if (!show) return;
  const sample = state.population.slice(0, previewCanvases.length);
  previewCanvases.forEach((canvas, i) => {
    const c = canvas.getContext('2d');
    if (!c) return;
    if (sample[i]) {
      canvas.classList.remove('hidden');
      renderGenomeIcon(c, sample[i], canvas.width);
    } else {
      canvas.classList.add('hidden');
    }
  });
}

// --- 変異レポートmodal ---

function showReportModal({ wave, lines, prevGenome, nextGenome, isFirst }) {
  reportHeading.textContent = `第${wave}世代の記録`;
  reportIntro.classList.toggle('hidden', !isFirst);
  reportLinesEl.innerHTML = '';
  lines.slice(0, 3).forEach((line) => {
    const li = document.createElement('li');
    li.textContent = line;
    reportLinesEl.appendChild(li);
  });
  const prevCtx = reportPrevCanvas.getContext('2d');
  const nextCtx = reportNextCanvas.getContext('2d');
  if (prevCtx && prevGenome) renderGenomeIcon(prevCtx, prevGenome, reportPrevCanvas.width);
  if (nextCtx && nextGenome) renderGenomeIcon(nextCtx, nextGenome, reportNextCanvas.width);
  reportModal.classList.remove('hidden');
}

function closeReportModal() {
  if (reportModal.classList.contains('hidden')) return;
  reportModal.classList.add('hidden');
  state = closeReport(state);
  pulseNewlyUnlocked();
  updatePalette();
  updateHud();
  updateSkillButton();
  renderPreview();
}

reportCloseButton.addEventListener('click', closeReportModal);
skillButton.addEventListener('click', onSkillButtonPress);

function cellCenterToClientPx(col, row) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = rect.width / (GRID.cols * GRID.cellSize);
  const scaleY = rect.height / (GRID.rows * GRID.cellSize);
  const x = (col + 0.5) * GRID.cellSize * scaleX;
  const y = row * GRID.cellSize * scaleY;
  return { x, y };
}

function showSellButtonFor(col, row, towerId) {
  const def = TOWERS[towerId];
  const refund = Math.floor(def.cost * ECONOMY.sellRatio);
  sellButton.textContent = `売る (+${refund}G)`;
  const { x, y } = cellCenterToClientPx(col, row);
  const wrapRect = canvas.parentElement.getBoundingClientRect();
  const canvasRect = canvas.getBoundingClientRect();
  sellButton.style.left = `${canvasRect.left - wrapRect.left + x}px`;
  sellButton.style.top = `${canvasRect.top - wrapRect.top + y}px`;
  sellButton.classList.remove('hidden');
  sellTarget = { col, row };
}

function clientToCell(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  const x = (clientX - rect.left) * scaleX;
  const y = (clientY - rect.top) * scaleY;
  return {
    col: Math.floor(x / GRID.cellSize),
    row: Math.floor(y / GRID.cellSize),
  };
}

function findTowerAt(col, row) {
  return state.towers.find((t) => t.col === col && t.row === row) || null;
}

function handleBoardTap(clientX, clientY) {
  if (!state) return;
  if (skillSelectMode) {
    const { col, row } = clientToCell(clientX, clientY);
    if (col < 0 || col >= GRID.cols || row < 0 || row >= GRID.rows) {
      exitSkillSelect();
      return;
    }
    activateSkill(rowToLane(row));
    return;
  }
  if (state.phase !== 'place' && state.phase !== 'wave') return;
  const { col, row } = clientToCell(clientX, clientY);
  if (col < 0 || col >= GRID.cols || row < 0 || row >= GRID.rows) {
    selectedTowerId = null;
    hideSellButton();
    updatePalette();
    return;
  }

  const existing = findTowerAt(col, row);
  if (existing) {
    // 配置済みセルへのタップは常に「売る」パネルを開く（重ね置きはエラー扱いしない）
    showSellButtonFor(col, row, existing.id);
    return;
  }

  hideSellButton();

  if (selectedTowerId) {
    if (canPlace(state, selectedTowerId, col, row)) {
      state = placeTower(state, selectedTowerId, col, row);
      selectedTowerId = null;
    } else if (GRID.laneRows.includes(row)) {
      // レーン上セルへの配置拒否: 赤フラッシュ、選択は継続
      flashCell = { col, row, until: performance.now() + 150 };
    }
    updatePalette();
    updateHud();
  }
}

function handleSell() {
  if (!sellTarget) return;
  state = sellTower(state, sellTarget.col, sellTarget.row);
  hideSellButton();
  selectedTowerId = null; // 売却後はパレット選択と射程円プレビューを解除する
  updatePalette();
  updateHud();
}

function selectTower(towerId) {
  if (!state) return;
  const def = TOWERS[towerId];
  if (!def) return;
  if (!state.unlocked.includes(towerId)) return;
  if (state.gold < def.cost) return;
  selectedTowerId = selectedTowerId === towerId ? null : towerId;
  hideSellButton();
  updatePalette();
}

paletteSlots.forEach((slot) => {
  slot.addEventListener('click', () => selectTower(slot.dataset.towerId));
});

canvas.addEventListener('click', (e) => handleBoardTap(e.clientX, e.clientY));
sellButton.addEventListener('click', (e) => {
  e.stopPropagation();
  handleSell();
});

document.addEventListener('click', (e) => {
  if (skillSelectMode && e.target !== canvas && e.target !== skillButton) {
    exitSkillSelect();
  }
  if (!sellTarget) return;
  if (e.target === sellButton) return;
  if (e.target === canvas) return; // canvasのクリックはhandleBoardTapが処理
  hideSellButton();
});

window.addEventListener('keydown', (e) => {
  if (!state) return;
  // 変異レポートmodal表示中は1-4/Space/Tab/F/Escをすべて無視する
  if (!reportModal.classList.contains('hidden')) return;
  if (e.key >= '1' && e.key <= '4') {
    const index = Number(e.key) - 1;
    const towerId = TOWER_ORDER[index];
    if (towerId) selectTower(towerId);
  } else if (e.key === 'Escape') {
    // Escは1段階のみ解除する: レーン選択モード中はそれだけ解除し、
    // そうでなければ塔選択/売却パネルだけを解除する
    if (skillSelectMode) {
      exitSkillSelect();
    } else {
      selectedTowerId = null;
      hideSellButton();
      updatePalette();
    }
  } else if (e.key === ' ') {
    if (state.phase === 'place') {
      e.preventDefault();
      onWaveStart();
    }
  } else if (e.key === 'Tab') {
    if (state.phase === 'wave') {
      e.preventDefault();
      toggleSpeed();
    }
  } else if (e.key === 'f' || e.key === 'F') {
    if (state.phase === 'wave' || skillSelectMode) {
      e.preventDefault();
      onSkillButtonPress();
    }
  }
});

function toggleSpeed() {
  speedMultiplier = speedMultiplier === 1 ? 2 : 1;
  speedToggleButton.classList.toggle('selected', speedMultiplier === 2);
}

speedToggleButton.addEventListener('click', () => {
  if (!state || state.phase !== 'wave') return;
  toggleSpeed();
});

function onWaveStart() {
  if (!state || state.phase !== 'place') return;
  state = startWave(state);
  enemies = spawnFromPopulation(state.population, state.wave, masterRng);
  activeShots = [];
  waveClock = 0;
  speedMultiplier = 1;
  speedToggleButton.classList.remove('selected');
  selectedTowerId = null;
  hideSellButton();
  updatePalette();
  updateHud();
  updateSkillButton();
  renderPreview();
}

waveStartButton.addEventListener('click', onWaveStart);

function processReachedAndKilled() {
  for (const enemy of enemies) {
    if (enemy.reached && !enemy._lifeGiven) {
      enemy._lifeGiven = true;
      const n = livesLostFor(enemy.genome);
      state = loseLives(state, n);
      if (isGameOver(state)) {
        return true;
      }
    } else if (!enemy.alive && !enemy.reached && !enemy._rewardGiven) {
      enemy._rewardGiven = true;
      state = { ...state, gold: state.gold + killReward(state.wave) };
    }
  }
  return false;
}

function goToGameOver() {
  exitSkillSelect();
  laneFlash = null;
  screen = 'result';
  resultHeading.textContent = 'あなたを倒した群れ';
  // エンドレス中はWAVE_COUNTを超え得るため分母を出さない
  resultWaveCount.textContent = state.endless
    ? `到達ウェーブ ${state.wave}（エンドレス）`
    : `到達ウェーブ ${state.wave} / ${WAVE_COUNT}`;
  endlessButton.classList.add('hidden');
  showScreen('result');
}

function goToClearResult() {
  screen = 'result';
  resultHeading.textContent = '防衛完了';
  resultWaveCount.textContent = `到達ウェーブ ${WAVE_COUNT}`;
  endlessButton.classList.remove('hidden');
  showScreen('result');
}

function finishWave() {
  exitSkillSelect();
  laneFlash = null;
  const prevPopulation = state.population;
  const results = collectResults(enemies, LANE_LENGTH);
  const { state: newState, report } = endWave(state, results, masterRng);
  state = newState;

  if (isCleared(state)) {
    goToClearResult();
    return;
  }

  const prevGenome = representative(prevPopulation, state.prevSummary);
  const nextGenome = representative(state.population, state.lastSummary);
  showReportModal({
    wave: state.wave,
    lines: report,
    prevGenome,
    nextGenome,
    isFirst: state.wave === 1,
  });
  updateHud();
}

function gameStep(dt) {
  waveClock += dt;
  const laneRows = GRID.laneRows;
  const newShots = stepTowers(state.towers, enemies, dt, laneRows, waveClock);
  for (const shot of newShots) activeShots.push(shot);
  activeShots = activeShots
    .map((s) => ({ ...s, ttl: s.ttl - dt }))
    .filter((s) => s.ttl > 0);

  stepEnemies(enemies, dt, LANE_LENGTH, waveClock);

  const overNow = processReachedAndKilled();
  updateHud();
  if (overNow) {
    goToGameOver();
    return;
  }

  const waveComplete = enemies.every((en) => !en.alive);
  if (waveComplete) {
    finishWave();
  }
}

function prefersReducedMotion() {
  return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

function laneSelectAlphaAt(t) {
  if (prefersReducedMotion()) return SKILL.laneBlinkAlphaReducedMotion;
  const period = SKILL.laneBlinkPeriod;
  const phase = ((t % period) + period) % period / period; // 0..1
  const triangle = phase < 0.5 ? phase * 2 : 2 - phase * 2; // 0->1->0
  return SKILL.laneBlinkAlphaMin + triangle * (SKILL.laneBlinkAlphaMax - SKILL.laneBlinkAlphaMin);
}

function frame(timestamp) {
  if (!loopRunning) return;
  if (lastTimestamp === null) lastTimestamp = timestamp;
  const rawDt = Math.min((timestamp - lastTimestamp) / 1000, 0.05);
  lastTimestamp = timestamp;

  if (screen === 'playing' && state && state.phase === 'wave') {
    gameStep(rawDt * speedMultiplier);
  }

  if (state) {
    if (flashCell && performance.now() > flashCell.until) flashCell = null;
    if (laneFlash && waveClock >= laneFlash.until) laneFlash = null;
    render(ctx, {
      towers: state.towers,
      enemies,
      shots: activeShots,
      rangePreview: selectedTowerId ? lastHoverCell && { ...lastHoverCell, towerId: selectedTowerId } : null,
      laneSelectAlpha: skillSelectMode ? laneSelectAlphaAt(waveClock) : null,
      laneFlash: laneFlash ? { lane: laneFlash.lane, alpha: 0.6 } : null,
    });
    if (flashCell) drawFlash();
    updateSkillButton();
  }

  requestAnimationFrame(frame);
}

function drawFlash() {
  ctx.save();
  ctx.fillStyle = 'rgba(224, 90, 58, 0.5)';
  ctx.fillRect(flashCell.col * GRID.cellSize, flashCell.row * GRID.cellSize, GRID.cellSize, GRID.cellSize);
  ctx.restore();
}

let lastHoverCell = null;
// pointermoveはmouse/touch/penを統一して扱うため、mousemoveとtouchmoveを個別実装せず共通化する
canvas.addEventListener('pointermove', (e) => {
  lastHoverCell = clientToCell(e.clientX, e.clientY);
});
// pointerdownでも更新する（タッチの単純タップではpointermoveが発火しないため、
// タップ時にも射程プレビューが一瞬表示されるようにする）
canvas.addEventListener('pointerdown', (e) => {
  lastHoverCell = clientToCell(e.clientX, e.clientY);
});

function startLoop() {
  if (loopRunning) return;
  loopRunning = true;
  lastTimestamp = null;
  requestAnimationFrame(frame);
}

function startGame() {
  const seed = Math.floor(Math.random() * 0xffffffff) >>> 0;
  masterRng = makeRng(seed);
  state = startNewGame({ seed, gold: ECONOMY.initialGoldDefault });
  screen = 'playing';
  previousUnlocked = ['basic'];
  previousSkillUnlocked = false;
  enemies = [];
  activeShots = [];
  selectedTowerId = null;
  skillSelectMode = false;
  laneFlash = null;
  skillSelectBanner.classList.add('hidden');
  reportModal.classList.add('hidden');
  hideSellButton();
  updateHud();
  updatePalette();
  updateSkillButton();
  renderPreview();
  showScreen('playing');
  startLoop();
}

startButton.addEventListener('click', startGame);
retryButton.addEventListener('click', startGame);
endlessButton.addEventListener('click', () => {
  state = continueEndless(state);
  state = closeReport(state);
  screen = 'playing';
  updateHud();
  updatePalette();
  updateSkillButton();
  renderPreview();
  showScreen('playing');
});
titleFromResultButton.addEventListener('click', () => {
  loopRunning = false;
  screen = 'title';
  skillSelectMode = false;
  skillSelectBanner.classList.add('hidden');
  showScreen('title');
});

showScreen('title');
