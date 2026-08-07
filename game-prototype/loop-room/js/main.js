// main.js
// 画面状態遷移の制御、イベントリスナー登録、ゲームループの起動を担当するエントリーポイント。

import { startNewGame, judgeChoice, isGameOver } from './game-state.js';
import { buildBaseRoomState, render } from './room-renderer.js';
import { VARIANTS } from './variants.js';
import { loadBestRound } from './storage.js';
import { initSurvey } from './survey.js';
import {
  initAudio,
  startAmbientDrone,
  stopAmbientDrone,
  startHeartbeat,
  stopHeartbeat,
  playCorrectSound,
  playGameOverSound,
  setMuted,
  isMuted,
} from './audio.js';

const screens = {
  title: document.getElementById('title-screen'),
  playing: document.getElementById('game-screen'),
  gameover: document.getElementById('gameover-screen'),
  survey: document.getElementById('survey-screen'),
};

const titleBestRound = document.getElementById('title-best-round');
const startButton = document.getElementById('start-button');
const roundDisplay = document.getElementById('round-display');
const canvas = document.getElementById('room-canvas');
const ctx = canvas.getContext('2d');
const backButton = document.getElementById('back-button');
const forwardButton = document.getElementById('forward-button');
const gameoverRound = document.getElementById('gameover-round');
const gameoverBest = document.getElementById('gameover-best');
const retryButton = document.getElementById('retry-button');
const surveyButton = document.getElementById('survey-button');
const titleFromGameoverButton = document.getElementById('title-from-gameover-button');
const flashOverlay = document.getElementById('flash-overlay');
const muteButton = document.getElementById('mute-button');

let gameState = null;
let inputLocked = false;
let previousBestRound = 0;
let lastGameOverRound = 0;

if (!ctx) {
  const unsupportedMessage = document.createElement('p');
  unsupportedMessage.className = 'unsupported-message';
  unsupportedMessage.textContent = 'お使いのブラウザではこのゲームを表示できません。';
  document.getElementById('app').prepend(unsupportedMessage);
  startButton.disabled = true;
}

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    el.classList.toggle('hidden', key !== name);
  });
}

function getVariantById(id) {
  return VARIANTS.find((v) => v.id === id);
}

function renderCurrentRoom() {
  let roomState = buildBaseRoomState(gameState.roomLayoutIndex);
  if (gameState.isVariant && gameState.currentVariantId) {
    const variant = getVariantById(gameState.currentVariantId);
    if (variant) {
      roomState = variant.apply(roomState, gameState.round);
    }
  }
  render(ctx, roomState);
  updateHeartbeatForRound();
}

function updateHeartbeatForRound() {
  const interval = Math.max(800, 3000 - gameState.round * 100);
  startHeartbeat(interval);
}

function updateRoundDisplay() {
  roundDisplay.textContent = `周回 ${gameState.round}`;
}

function updateTitleBestRound() {
  titleBestRound.textContent = `自己ベスト: ${loadBestRound()}周`;
}

function triggerGameOverFlash(callback) {
  flashOverlay.classList.remove('hidden');
  flashOverlay.classList.add('flash-gameover');
  setTimeout(() => {
    flashOverlay.classList.remove('flash-gameover');
    flashOverlay.classList.add('hidden');
    callback();
  }, 400);
}

function triggerRoundTransition(callback) {
  flashOverlay.classList.remove('hidden');
  flashOverlay.classList.add('flash-blackout');
  setTimeout(() => {
    callback();
    requestAnimationFrame(() => {
      flashOverlay.classList.remove('flash-blackout');
      setTimeout(() => {
        flashOverlay.classList.add('hidden');
      }, 300);
    });
  }, 150);
}

function showGameOverScreen() {
  lastGameOverRound = gameState.round;
  gameoverRound.textContent = `到達周回: ${gameState.round}周`;
  const isNewBest = gameState.round > previousBestRound;
  gameoverBest.textContent = isNewBest
    ? '自己ベスト更新！'
    : `自己ベスト: ${gameState.bestRound}周`;
  showScreen('gameover');
}

function handleChoice(playerChoseBack) {
  if (inputLocked || !gameState) return;
  inputLocked = true;

  previousBestRound = gameState.bestRound;
  const result = judgeChoice(gameState, playerChoseBack);
  gameState = result.newState;

  if (isGameOver(result)) {
    playGameOverSound();
    stopAmbientDrone();
    stopHeartbeat();
    triggerGameOverFlash(() => {
      showGameOverScreen();
      inputLocked = false;
    });
  } else {
    playCorrectSound();
    triggerRoundTransition(() => {
      updateRoundDisplay();
      renderCurrentRoom();
      inputLocked = false;
    });
  }
}

function startGame() {
  if (!ctx) return;
  initAudio();
  gameState = startNewGame();
  showScreen('playing');
  updateRoundDisplay();
  renderCurrentRoom();
  startAmbientDrone();
  startHeartbeat(3000);
}

function updateMuteButton() {
  if (!muteButton) return;
  const label = isMuted() ? '音声: OFF' : '音声: ON';
  muteButton.textContent = label;
  muteButton.setAttribute('aria-label', label);
}

startButton.addEventListener('click', startGame);
retryButton.addEventListener('click', startGame);
backButton.addEventListener('click', () => handleChoice(true));
forwardButton.addEventListener('click', () => handleChoice(false));
surveyButton.addEventListener('click', () => {
  stopAmbientDrone();
  stopHeartbeat();
  showScreen('survey');
});
titleFromGameoverButton.addEventListener('click', () => {
  stopAmbientDrone();
  stopHeartbeat();
  updateTitleBestRound();
  showScreen('title');
});
if (muteButton) {
  muteButton.addEventListener('click', () => {
    setMuted(!isMuted());
    updateMuteButton();
  });
}

initSurvey({
  onBackToTitle: () => {
    stopAmbientDrone();
    stopHeartbeat();
    updateTitleBestRound();
    showScreen('title');
  },
  getRoundsReached: () => lastGameOverRound,
});

updateTitleBestRound();
updateMuteButton();
showScreen('title');
