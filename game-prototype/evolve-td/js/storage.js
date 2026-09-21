// storage.js
// localStorageへの永続化（bestWave / survey / challengeReceived / seenIntro / sessions / wave2Started）。
// globalThis.localStorageが存在しない環境（Node.jsのテスト実行時など）でも
// 例外を投げずに動作するようガードする（巡室 storage.js の初期化ガードを踏襲）。
// キー接頭辞: "evolveTd."

const PREFIX = 'evolveTd.';
const BEST_WAVE_KEY = `${PREFIX}bestWave`;
const SURVEY_RESPONSES_KEY = `${PREFIX}surveyResponses`;
const CHALLENGE_RECEIVED_KEY = `${PREFIX}challengeReceived`;
const SEEN_INTRO_KEY = `${PREFIX}seenIntro`;
const SESSIONS_KEY = `${PREFIX}sessions`;
const WAVE2_STARTED_KEY = `${PREFIX}wave2Started`;

function hasLocalStorage() {
  return typeof globalThis.localStorage !== 'undefined' && globalThis.localStorage !== null;
}

function readInt(key, fallback = 0) {
  if (!hasLocalStorage()) return fallback;
  try {
    const raw = globalThis.localStorage.getItem(key);
    if (raw === null || raw === undefined) return fallback;
    const parsed = parseInt(raw, 10);
    return Number.isNaN(parsed) ? fallback : parsed;
  } catch {
    return fallback;
  }
}

function readBool(key) {
  if (!hasLocalStorage()) return false;
  try {
    return globalThis.localStorage.getItem(key) === 'true';
  } catch {
    return false;
  }
}

function writeValue(key, value) {
  if (!hasLocalStorage()) return;
  try {
    globalThis.localStorage.setItem(key, String(value));
  } catch {
    // QuotaExceededErrorやプライベートブラウジングでの失敗はゲーム進行を止めない
  }
}

// --- bestWave: seedごとではなく全体の自己ベストのみ保存 ---

/**
 * @param {number} n
 */
export function saveBestWave(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return;
  const current = loadBestWave();
  if (n > current) writeValue(BEST_WAVE_KEY, n);
}

/**
 * @returns {number}
 */
export function loadBestWave() {
  return readInt(BEST_WAVE_KEY, 0);
}

// --- アンケート ---

/**
 * @param {object} obj
 */
export function saveSurveyResponse(obj) {
  if (!hasLocalStorage()) return;
  const responses = loadSurveyResponses();
  responses.push(obj);
  try {
    globalThis.localStorage.setItem(SURVEY_RESPONSES_KEY, JSON.stringify(responses));
  } catch {
    // 容量超過等は無視（回答自体が失敗してもゲーム進行を止めない）
  }
}

/**
 * @returns {Array<object>}
 */
export function loadSurveyResponses() {
  if (!hasLocalStorage()) return [];
  try {
    const raw = globalThis.localStorage.getItem(SURVEY_RESPONSES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * アンケート回答＋計測値をJSON文字列で返す。
 * キー: responses, bestWave, challengeReceived, sessions, wave2Started
 * @returns {string}
 */
export function exportSurveyAsJSON() {
  return JSON.stringify({
    responses: loadSurveyResponses(),
    bestWave: loadBestWave(),
    challengeReceived: hasChallengeReceived(),
    sessions: readInt(SESSIONS_KEY, 0),
    wave2Started: readInt(WAVE2_STARTED_KEY, 0),
  });
}

// --- チャレンジリンク受領（届け方の効果測定） ---

export function markChallengeReceived() {
  writeValue(CHALLENGE_RECEIVED_KEY, 'true');
}

/**
 * @returns {boolean}
 */
export function hasChallengeReceived() {
  return readBool(CHALLENGE_RECEIVED_KEY);
}

// --- 教えない導入（初回起動のみ） ---

export function markSeenIntro() {
  writeValue(SEEN_INTRO_KEY, 'true');
}

/**
 * @returns {boolean}
 */
export function hasSeenIntro() {
  return readBool(SEEN_INTRO_KEY);
}

// --- 計測フラグ（離脱計測点「ウェーブ2開始率」） ---

export function recordSessionStart() {
  writeValue(SESSIONS_KEY, readInt(SESSIONS_KEY, 0) + 1);
}

export function recordWave2Started() {
  writeValue(WAVE2_STARTED_KEY, readInt(WAVE2_STARTED_KEY, 0) + 1);
}
