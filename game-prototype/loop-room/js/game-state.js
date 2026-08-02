// game-state.js
// ゲーム全体の状態（周回数・自己ベスト・現在の異変有無など）と、
// 周回の進行・判定ロジックを担当する。

import { VARIANTS } from './variants.js';
import { getLayoutCount } from './room-renderer.js';
import { loadBestRound, saveBestRound } from './storage.js';

const RECENT_HISTORY_LIMIT = 2;

function pickVariantId(recentVariantIds) {
  const excluded = new Set(recentVariantIds.slice(-RECENT_HISTORY_LIMIT));
  const pool = VARIANTS.filter((v) => !excluded.has(v.id));
  const candidates = pool.length > 0 ? pool : VARIANTS;
  const index = Math.floor(Math.random() * candidates.length);
  return candidates[index].id;
}

function drawIsVariant() {
  return Math.random() < 0.5;
}

export function startNewGame() {
  const roomLayoutIndex = Math.floor(Math.random() * getLayoutCount());
  const bestRound = loadBestRound();
  const state = {
    round: 0,
    bestRound,
    isVariant: false,
    currentVariantId: null,
    roomLayoutIndex,
    recentVariantIds: [],
  };
  return nextRound(state);
}

export function nextRound(state) {
  const isVariant = drawIsVariant();
  const currentVariantId = isVariant ? pickVariantId(state.recentVariantIds) : null;
  const recentVariantIds = isVariant
    ? [...state.recentVariantIds, currentVariantId].slice(-RECENT_HISTORY_LIMIT)
    : state.recentVariantIds;

  return {
    ...state,
    isVariant,
    currentVariantId,
    recentVariantIds,
  };
}

export function judgeChoice(state, playerChoseBack) {
  const correct = state.isVariant ? playerChoseBack : !playerChoseBack;

  if (!correct) {
    const bestRound = Math.max(state.bestRound, state.round);
    saveBestRound(bestRound);
    return {
      correct: false,
      newState: { ...state, bestRound },
    };
  }

  const advancedState = { ...state, round: state.round + 1 };
  return {
    correct: true,
    newState: nextRound(advancedState),
  };
}

export function isGameOver(judgeResult) {
  return !judgeResult.correct;
}
