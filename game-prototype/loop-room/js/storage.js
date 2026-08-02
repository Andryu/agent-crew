// storage.js
// localStorageへの永続化を担当する。globalThis.localStorageが存在しない環境
// （Node.jsのテスト実行時など）でも例外を投げずに動作するようガードする。

const BEST_ROUND_KEY = 'loopRoom.bestRound';
const SURVEY_RESPONSES_KEY = 'loopRoom.surveyResponses';

function hasLocalStorage() {
  return typeof globalThis.localStorage !== 'undefined' && globalThis.localStorage !== null;
}

export function saveBestRound(n) {
  if (!hasLocalStorage()) return;
  try {
    globalThis.localStorage.setItem(BEST_ROUND_KEY, String(n));
  } catch {
    // QuotaExceededErrorやプライベートブラウジングでの失敗はゲーム進行を止めない
  }
}

export function loadBestRound() {
  if (!hasLocalStorage()) return 0;
  const raw = globalThis.localStorage.getItem(BEST_ROUND_KEY);
  const parsed = raw === null || raw === undefined ? 0 : parseInt(raw, 10);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function saveSurveyResponse(obj) {
  if (!hasLocalStorage()) return;
  const responses = loadSurveyResponses();
  responses.push(obj);
  try {
    globalThis.localStorage.setItem(SURVEY_RESPONSES_KEY, JSON.stringify(responses));
  } catch {
    // QuotaExceededErrorやプライベートブラウジングでの失敗はゲーム進行を止めない
  }
}

export function loadSurveyResponses() {
  if (!hasLocalStorage()) return [];
  const raw = globalThis.localStorage.getItem(SURVEY_RESPONSES_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function exportSurveyAsJSON() {
  return JSON.stringify(loadSurveyResponses());
}
