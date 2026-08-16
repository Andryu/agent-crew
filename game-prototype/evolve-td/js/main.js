// main.js
// 画面遷移・ゲームループ・入力（配置/売却/ボタン）を担当するエントリーポイント。
// CP1: 進化本体・変異レポートUI・次ウェーブプレビュー・発熱・チャレンジリンク・
//      アンケート・音・粒子・吹き出しは実装しない（CP2/CP3で追加）。

import {
  GRID,
  TOWERS,
  TOWER_ORDER,
  ECONOMY,
  LANE_LENGTH,
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
} from './game-state.js';
import { spawnFromPopulation, stepEnemies, collectResults, livesLostFor } from './enemies.js';
import { stepTowers } from './towers.js';
import { render, drawTowerIcon } from './renderer.js';

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
let lastTimestamp = null;
let loopRunning = false;

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
}

function updateHud() {
  hudGold.textContent = `${state.gold}G`;
  hudLives.textContent = `♥ ${state.lives}`;
  hudWave.textContent = `WAVE ${state.wave}/15`;
  speedToggleButton.disabled = state.phase !== 'wave';
}

function hideSellButton() {
  sellButton.classList.add('hidden');
  sellTarget = null;
}

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
  if (!state || (state.phase !== 'place' && state.phase !== 'wave')) return;
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
  if (!sellTarget) return;
  if (e.target === sellButton) return;
  if (e.target === canvas) return; // canvasのクリックはhandleBoardTapが処理
  hideSellButton();
});

window.addEventListener('keydown', (e) => {
  if (!state) return;
  if (e.key >= '1' && e.key <= '4') {
    const index = Number(e.key) - 1;
    const towerId = TOWER_ORDER[index];
    if (towerId) selectTower(towerId);
  } else if (e.key === 'Escape') {
    selectedTowerId = null;
    hideSellButton();
    updatePalette();
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
  screen = 'result';
  resultHeading.textContent = 'あなたを倒した群れ';
  resultWaveCount.textContent = `到達ウェーブ ${state.wave} / 15`;
  endlessButton.classList.add('hidden');
  showScreen('result');
}

function goToClearResult() {
  screen = 'result';
  resultHeading.textContent = '防衛完了';
  resultWaveCount.textContent = '到達ウェーブ 15';
  endlessButton.classList.remove('hidden');
  showScreen('result');
}

function finishWave() {
  const results = collectResults(enemies, LANE_LENGTH);
  const { state: newState } = endWave(state, results, masterRng);
  state = newState;

  if (isCleared(state)) {
    goToClearResult();
    return;
  }

  state = closeReport(state);
  pulseNewlyUnlocked();
  updatePalette();
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
    render(ctx, {
      towers: state.towers,
      enemies,
      shots: activeShots,
      rangePreview: selectedTowerId ? lastHoverCell && { ...lastHoverCell, towerId: selectedTowerId } : null,
    });
    if (flashCell) drawFlash();
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
  enemies = [];
  activeShots = [];
  selectedTowerId = null;
  hideSellButton();
  updateHud();
  updatePalette();
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
  showScreen('playing');
});
titleFromResultButton.addEventListener('click', () => {
  loopRunning = false;
  screen = 'title';
  showScreen('title');
});

showScreen('title');
