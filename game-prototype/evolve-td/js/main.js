// main.js
// 画面遷移・ゲームループ・入力（配置/売却/ボタン）を担当するエントリーポイント。
// CP2: 変異レポートmodal・次ウェーブプレビュー・発熱スキルを追加。
// CP3: チャレンジリンク・アンケート・保存・SE・撃破ジュース・負けた画・教えない導入を追加。

import {
  GRID,
  TOWERS,
  TOWER_ORDER,
  ECONOMY,
  LANE_LENGTH,
  SKILL,
  JUICE,
  WAVE_COUNT,
  RESIST_COLORS,
  RESIST_LABELS,
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
  pickGameOverRepresentative,
} from './enemies.js';
import { stepTowers } from './towers.js';
import { render, drawTowerIcon, renderGenomeIcon, renderGenomeGroup } from './renderer.js';
import { representative, evaluate, summarize } from './evolution.js';
import { encodeChallenge, decodeChallenge } from './share.js';
import {
  saveBestWave,
  markChallengeReceived,
  markSeenIntro,
  hasSeenIntro,
  recordSessionStart,
  recordWave2Started,
} from './storage.js';
import { initSurvey, resetSurveyScreen } from './survey.js';
import {
  initAudio,
  playPlace,
  playKill,
  playHit,
  playWaveStart,
  setMuted,
  isMuted,
} from './audio.js';

const screens = {
  title: document.getElementById('title-screen'),
  playing: document.getElementById('playing-screen'),
  result: document.getElementById('result-screen'),
  survey: document.getElementById('survey-screen'),
};

const startButton = document.getElementById('start-button');
const canvas = document.getElementById('board-canvas');
const ctx = canvas.getContext('2d');
const hudGold = document.getElementById('hud-gold');
const hudLives = document.getElementById('hud-lives');
const hudWave = document.getElementById('hud-wave');
const muteButton = document.getElementById('mute-button');
const sellButton = document.getElementById('sell-button');
const paletteEl = document.getElementById('tower-palette');
const paletteSlots = Array.from(document.querySelectorAll('.tower-slot'));
const waveStartButton = document.getElementById('wave-start-button');
const speedToggleButton = document.getElementById('speed-toggle-button');
const resultHeading = document.getElementById('result-heading');
const resultWaveCount = document.getElementById('result-wave-count');
const resultGenomeCanvas = document.getElementById('result-genome-canvas');
const resultGenomeCaption = document.getElementById('result-genome-caption');
const endlessButton = document.getElementById('endless-button');
const retryButton = document.getElementById('retry-button');
const titleFromResultButton = document.getElementById('title-from-result-button');
const challengeSendButton = document.getElementById('challenge-send-button');
const surveyOpenButton = document.getElementById('survey-open-button');
const previewPanel = document.getElementById('preview-panel');
const previewCanvases = Array.from(document.querySelectorAll('.preview-icon'));
const skillButton = document.getElementById('skill-button');
const skillLabel = document.getElementById('skill-label');
const skillSelectBanner = document.getElementById('skill-select-banner');
const introBubble = document.getElementById('intro-bubble');
const reportModal = document.getElementById('report-modal');
const reportHeading = document.getElementById('report-heading');
const reportIntro = document.getElementById('report-intro');
const reportLinesEl = document.getElementById('report-lines');
const reportPrevCanvas = document.getElementById('report-prev-canvas');
const reportNextCanvas = document.getElementById('report-next-canvas');
const reportCloseButton = document.getElementById('report-close-button');
const challengeBanner = document.getElementById('challenge-banner');
const challengeBannerText = document.getElementById('challenge-banner-text');
const challengeAcceptButton = document.getElementById('challenge-accept-button');
const challengeDeclineButton = document.getElementById('challenge-decline-button');
const vignetteOverlay = document.getElementById('vignette-overlay');
const toastEl = document.getElementById('toast');

let state = null;
let screen = 'title'; // 'title' | 'playing' | 'result' | 'survey'（画面状態はここで管理。state.phaseはplace/wave/reportのみ）
let masterRng = null;
let enemies = [];
let activeShots = [];
let particles = []; // 撃破ジュースの粒子 {x,y,color,vx,vy,ttl,life}
let goldPopups = []; // 撃破報酬の数字ポップ {x,y,text,ttl,life}
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
let pendingChallenge = null; // {seed, gold} タイトルで検出した挑戦状
let initialGold = ECONOMY.initialGoldDefault; // このランの開始時資金（挑戦状リンク生成に使う。state.goldは変動するため別管理）
let seenIntroThisSession = false; // このプレイ開始前に既にhasSeenIntro()済みだったか（初回吹き出し・レポート初回1行の連動に使う）
let introBubbleTimerId = null;
let toastTimerId = null;
let lastKillSoundAt = -Infinity;

if (!ctx) {
  const msg = document.createElement('p');
  msg.textContent = 'お使いのブラウザではこのゲームを表示できません。';
  document.getElementById('app').prepend(msg);
  startButton.disabled = true;
}

function prefersReducedMotion() {
  return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

// --- トースト（コピー完了通知） ---

function showToast(text) {
  toastEl.textContent = text;
  toastEl.classList.remove('hidden');
  if (toastTimerId !== null) clearTimeout(toastTimerId);
  toastTimerId = setTimeout(() => {
    toastEl.classList.add('hidden');
    toastTimerId = null;
  }, JUICE.toastDurationMs);
}

// --- 到達時の赤ビネット（0.25秒、box-shadow inset） ---

function flashVignette() {
  vignetteOverlay.classList.remove('flash');
  // eslint-disable-next-line no-unused-expressions
  void vignetteOverlay.offsetWidth; // 強制リフローで同じクラスの再付与でもアニメーションを再生させる
  vignetteOverlay.classList.add('flash');
}

// --- ミュート ---

function updateMuteButton() {
  muteButton.textContent = isMuted() ? '🔇' : '🔊';
  muteButton.setAttribute('aria-label', isMuted() ? 'ミュート解除' : 'ミュート');
}

muteButton.addEventListener('click', () => {
  setMuted(!isMuted());
  updateMuteButton();
});
updateMuteButton();

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

// --- 教えない導入（初回吹き出し） ---

function showIntroBubbleIfFirstTime() {
  if (seenIntroThisSession) return; // 既にhasSeenIntro()済み（初回ではない）
  introBubble.classList.remove('hidden');
  introBubble.classList.remove('is-fading');
  if (introBubbleTimerId !== null) clearTimeout(introBubbleTimerId);
  introBubbleTimerId = setTimeout(dismissIntroBubble, JUICE.introBubbleTimeoutMs); // タイムアウト消去
}

function dismissIntroBubble() {
  if (introBubbleTimerId !== null) {
    clearTimeout(introBubbleTimerId);
    introBubbleTimerId = null;
  }
  if (introBubble.classList.contains('hidden') || introBubble.classList.contains('is-fading')) return;
  // 0.3秒フェードアウト後にhiddenへ切り替える（即時非表示にしない）
  introBubble.classList.add('is-fading');
  setTimeout(() => {
    introBubble.classList.add('hidden');
    introBubble.classList.remove('is-fading');
  }, 300);
  markSeenIntro();
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

function showReportModal({ wave, lines, prevGroup, nextGroup, isFirst }) {
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
  // 2026-08-17: 代表1体ではなく前後の群れサンプル6体を並べる（色・形の変化を一目で）
  if (prevCtx) renderGenomeGroup(prevCtx, prevGroup, reportPrevCanvas.width, reportPrevCanvas.height);
  if (nextCtx) renderGenomeGroup(nextCtx, nextGroup, reportNextCanvas.width, reportNextCanvas.height);
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

// aboveがtrueならセルの上側に出す座標（cellの上端）、falseなら下側に出す座標（cellの下端）を返す。
// CP3確定回答#10: row>=6（下2行）はaboveをtrueにして呼ぶ。それ以外（現状どおり）はfalse。
function cellCenterToClientPx(col, row, above) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = rect.width / (GRID.cols * GRID.cellSize);
  const scaleY = rect.height / (GRID.rows * GRID.cellSize);
  const x = (col + 0.5) * GRID.cellSize * scaleX;
  const y = (above ? row : row + 1) * GRID.cellSize * scaleY;
  return { x, y };
}

function showSellButtonFor(col, row, towerId) {
  const def = TOWERS[towerId];
  const refund = Math.floor(def.cost * ECONOMY.sellRatio);
  sellButton.textContent = `売る (+${refund}G)`;
  const above = row >= 6; // 下2行はボタンをセルの上側に出す（main.jsの座標計算で分岐）
  const { x, y } = cellCenterToClientPx(col, row, above);
  const wrapRect = canvas.parentElement.getBoundingClientRect();
  const canvasRect = canvas.getBoundingClientRect();
  sellButton.classList.toggle('sell-button-above', above);
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
      playPlace();
      dismissIntroBubble();
    } else if (GRID.laneRows.includes(row)) {
      // レーン上セルへの配置拒否: 赤フラッシュ＋振動50ms、選択は継続
      flashCell = { col, row, until: performance.now() + 150 };
      if (navigator.vibrate) navigator.vibrate(JUICE.vibrateMs);
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
  playPlace(true); // 配置音を低ピッチ再生（新規SEは追加しない）
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
  dismissIntroBubble();
  if (state.wave === 2) recordWave2Started(); // 離脱計測点「ウェーブ2開始率」
  state = startWave(state);
  enemies = spawnFromPopulation(state.population, state.wave, masterRng);
  activeShots = [];
  particles = [];
  goldPopups = [];
  playWaveStart();
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

// --- 撃破ジュース（粒子・資金ポップ） ---

function enemyCenterPx(enemy) {
  return {
    x: enemy.x * GRID.cellSize + GRID.cellSize / 2,
    y: GRID.laneRows[enemy.lane] * GRID.cellSize + GRID.cellSize / 2,
  };
}

function spawnKillParticles(enemy) {
  if (prefersReducedMotion()) return; // reduced-motionでは粒子を省略
  const { x, y } = enemyCenterPx(enemy);
  const color = RESIST_COLORS[enemy.genome.resist];
  const count = JUICE.particleMin + Math.floor(Math.random() * (JUICE.particleMax - JUICE.particleMin + 1));
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = JUICE.particleSpeedMin + Math.random() * (JUICE.particleSpeedMax - JUICE.particleSpeedMin);
    particles.push({
      x,
      y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      color,
      life: JUICE.particleLife,
      ttl: JUICE.particleLife,
    });
  }
}

function spawnGoldPopup(enemy, amount) {
  const { x, y } = enemyCenterPx(enemy);
  goldPopups.push({ x, y, text: `+${amount}`, life: JUICE.goldPopupLife, ttl: JUICE.goldPopupLife });
}

function playKillThrottled(now) {
  // 同時多数撃破は約40ms間隔でクランプし音の飽和を防ぐ
  if (now - lastKillSoundAt < JUICE.killSoundThrottleSec) return;
  lastKillSoundAt = now;
  playKill();
}

function processReachedAndKilled() {
  for (const enemy of enemies) {
    if (enemy.reached && !enemy._lifeGiven) {
      enemy._lifeGiven = true;
      const n = livesLostFor(enemy.genome);
      state = loseLives(state, n);
      flashVignette();
      playHit();
      if (isGameOver(state)) {
        return true;
      }
    } else if (!enemy.alive && !enemy.reached && !enemy._rewardGiven) {
      enemy._rewardGiven = true;
      const reward = killReward(state.wave);
      state = { ...state, gold: state.gold + reward };
      spawnKillParticles(enemy);
      spawnGoldPopup(enemy, reward);
      playKillThrottled(waveClock);
    }
  }
  return false;
}

// --- 負けた画／クリア画面の代表個体 ---

// ゲームオーバー時点の代表個体genomeを選ぶ（選出ロジック本体はenemies.jsの純粋関数）。
// 出現済み個体が1体もいない極端なケースはフォールバックする。
function pickGameOverRepresentativeGenome() {
  return pickGameOverRepresentative(enemies, LANE_LENGTH) ?? representative(state.population, summarize(state.population));
}

// クリア時: W15のcollectResultsに基づくevaluate最大の1体
function pickClearRepresentative(prevPopulation) {
  const results = collectResults(enemies, LANE_LENGTH);
  const fitness = evaluate(results);
  let bestIndex = 0;
  let bestFitness = -Infinity;
  fitness.forEach((f, i) => {
    if (f > bestFitness) {
      bestFitness = f;
      bestIndex = i;
    }
  });
  return prevPopulation[bestIndex] ?? representative(prevPopulation, summarize(prevPopulation));
}

// 「第{n}世代・速度×{speedMean 小数1桁}・{resist最多}耐性」を生成する。
// resist最多がnone(index0)の場合は耐性句を省略する。
function formatResultCaption(wave, summary) {
  const speedStr = summary.speedMean.toFixed(1);
  const shares = summary.resistShare;
  let maxIndex = 0;
  for (let i = 1; i < shares.length; i++) {
    if (shares[i] > shares[maxIndex]) maxIndex = i;
  }
  const resistPart = maxIndex === 0 ? '' : `・${RESIST_LABELS[maxIndex]}耐性`;
  return `第${wave}世代・速度×${speedStr}${resistPart}`;
}

function showResultGenome(genome, summary) {
  const genomeCtx = resultGenomeCanvas.getContext('2d');
  if (genomeCtx && genome) renderGenomeIcon(genomeCtx, genome, resultGenomeCanvas.width);
  resultGenomeCaption.textContent = formatResultCaption(state.wave, summary);
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
  retryButton.classList.remove('hidden');
  showResultGenome(pickGameOverRepresentativeGenome(), summarize(state.population));
  saveBestWave(state.wave);
  showScreen('result');
}

function goToClearResult(prevPopulation) {
  screen = 'result';
  resultHeading.textContent = '防衛完了';
  resultWaveCount.textContent = `到達ウェーブ ${WAVE_COUNT}`;
  endlessButton.classList.remove('hidden');
  retryButton.classList.add('hidden'); // UX§7.2: クリア画面はエンドレス／挑戦状／アンケート／タイトルの4つ
  showResultGenome(pickClearRepresentative(prevPopulation), state.prevSummary);
  saveBestWave(state.wave);
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
    goToClearResult(prevPopulation);
    return;
  }

  showReportModal({
    wave: state.wave,
    lines: report,
    prevGroup: prevPopulation.slice(0, 6),
    nextGroup: state.population.slice(0, 6),
    // CP3: 初回1行はセッション開始時点でhasSeenIntro()が未設定だった場合のみ（storage.seenIntroに連動）
    isFirst: state.wave === 1 && !seenIntroThisSession,
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
  particles = particles
    .map((p) => ({ ...p, x: p.x + p.vx * dt, y: p.y + p.vy * dt, ttl: p.ttl - dt }))
    .filter((p) => p.ttl > 0);
  goldPopups = goldPopups
    .map((p) => ({ ...p, y: p.y + JUICE.goldPopupRiseSpeed * dt, ttl: p.ttl - dt }))
    .filter((p) => p.ttl > 0);

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
      particles,
      goldPopups,
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

/**
 * @param {{seed?:number, gold?:number}} [options] 挑戦状受領時にseed/goldを上書きする
 */
function startGame(options = {}) {
  const seed = typeof options.seed === 'number' ? options.seed : Math.floor(Math.random() * 0xffffffff) >>> 0;
  const gold = typeof options.gold === 'number' ? options.gold : ECONOMY.initialGoldDefault;
  initialGold = gold; // チャレンジリンク生成に使う開始時資金（state.goldは以後変動する）
  seenIntroThisSession = hasSeenIntro(); // マーク前に捕捉（初回吹き出し・レポート初回1行の判定に使う）
  recordSessionStart();
  initAudio(); // ユーザー操作(クリック)ハンドラ内なのでAudioContext初期化が許可される
  masterRng = makeRng(seed);
  state = startNewGame({ seed, gold });
  screen = 'playing';
  previousUnlocked = ['basic'];
  previousSkillUnlocked = false;
  enemies = [];
  activeShots = [];
  particles = [];
  goldPopups = [];
  selectedTowerId = null;
  skillSelectMode = false;
  laneFlash = null;
  skillSelectBanner.classList.add('hidden');
  reportModal.classList.add('hidden');
  challengeBanner.classList.add('hidden');
  startButton.classList.remove('hidden');
  hideSellButton();
  updateHud();
  updatePalette();
  updateSkillButton();
  renderPreview();
  showScreen('playing');
  showIntroBubbleIfFirstTime();
  startLoop();
}

startButton.addEventListener('click', () => startGame());
retryButton.addEventListener('click', () => startGame());
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

function goToTitle() {
  loopRunning = false;
  screen = 'title';
  skillSelectMode = false;
  skillSelectBanner.classList.add('hidden');
  checkForChallenge();
  showScreen('title');
}

titleFromResultButton.addEventListener('click', goToTitle);

// --- チャレンジリンク（届け方） ---

function clearChallengeHash() {
  if (window.location.hash) {
    history.replaceState(null, '', window.location.pathname + window.location.search);
  }
}

function checkForChallenge() {
  const decoded = decodeChallenge(window.location.hash);
  if (!decoded) {
    pendingChallenge = null;
    challengeBanner.classList.add('hidden');
    startButton.classList.remove('hidden');
    return;
  }
  pendingChallenge = decoded;
  challengeBannerText.textContent = `挑戦状が届いています（seed: ${decoded.seed}）`;
  challengeBanner.classList.remove('hidden');
  startButton.classList.add('hidden');
}

challengeAcceptButton.addEventListener('click', () => {
  if (!pendingChallenge) return;
  const { seed, gold } = pendingChallenge;
  markChallengeReceived();
  clearChallengeHash();
  startGame({ seed, gold });
});

challengeDeclineButton.addEventListener('click', () => {
  // 通常ではじめる: ハッシュを消してランダムseedで開始する
  clearChallengeHash();
  pendingChallenge = null;
  challengeBanner.classList.add('hidden');
  startButton.classList.remove('hidden');
  startGame();
});

async function handleChallengeSend() {
  if (!state) return;
  const encoded = encodeChallenge({ seed: state.seed, gold: initialGold });
  const url = `${window.location.origin}${window.location.pathname}#c=${encoded}`;
  const text = `群変 seed:${state.seed} で ${state.wave} ウェーブ耐えた。あなたは？ ${url}`;
  try {
    await navigator.clipboard.writeText(text);
    showToast('コピーしました');
  } catch {
    showToast('コピーに失敗しました');
  }
}

challengeSendButton.addEventListener('click', handleChallengeSend);

// --- アンケート ---

initSurvey({
  onBackToTitle: goToTitle,
  getReachedWave: () => (state ? state.wave : 0),
});

surveyOpenButton.addEventListener('click', () => {
  resetSurveyScreen();
  screen = 'survey';
  showScreen('survey');
});

checkForChallenge();
showScreen('title');
