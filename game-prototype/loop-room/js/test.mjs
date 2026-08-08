// test.mjs
// Node.js単体で実行できるロジックテスト。
// DOM操作を含むmain.js/room-renderer.jsの描画/survey.jsのUI部分は対象外。
// 実行: node js/test.mjs

import { VARIANTS, computeMagnitude } from './variants.js';
import { judgeChoice, nextRound, startNewGame } from './game-state.js';

let failed = false;

function check(label, condition) {
  if (condition) {
    console.log(`PASS: ${label}`);
  } else {
    console.log(`FAIL: ${label}`);
    failed = true;
  }
}

// --- localStorageの簡易モック（Map実装）をNode.js環境に注入 ---
function createMockLocalStorage() {
  const store = new Map();
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
    clear() {
      store.clear();
    },
  };
}

globalThis.localStorage = createMockLocalStorage();

// storage.jsはglobalThis.localStorageの存在チェックを行うため、モック注入後にimportする。
const { saveBestRound, loadBestRound, saveSurveyResponse, loadSurveyResponses, exportSurveyAsJSON } =
  await import('./storage.js');

// --- 1. VARIANTS ---
console.log('--- VARIANTS ---');
check('VARIANTSが配列である', Array.isArray(VARIANTS));
check('VARIANTSが15〜20個である', VARIANTS.length >= 15 && VARIANTS.length <= 20);
check(
  '各要素がid, name, applyを持つ',
  VARIANTS.every(
    (v) =>
      typeof v.id === 'string' &&
      v.id.length > 0 &&
      typeof v.name === 'string' &&
      v.name.length > 0 &&
      typeof v.apply === 'function'
  )
);
check(
  'idがすべてユニークである',
  new Set(VARIANTS.map((v) => v.id)).size === VARIANTS.length
);

// --- 2. computeMagnitude ---
console.log('--- computeMagnitude ---');
const mag0 = computeMagnitude(100, 0);
const mag25 = computeMagnitude(100, 25);
check(`computeMagnitude(100, 0) が100に近い値 (実際: ${mag0})`, Math.abs(mag0 - 100) < 0.001);
check(`computeMagnitude(100, 25) が下限0.6により60になる (実際: ${mag25})`, Math.abs(mag25 - 60) < 0.001);
const mag100 = computeMagnitude(100, 100);
check(
  `computeMagnitude(100, 100) が下限60を下回らない (実際: ${mag100})`,
  Math.abs(mag100 - 60) < 0.001
);

// --- apply()がroomStateを破壊的変更しないことの確認 ---
console.log('--- variants apply() の非破壊性 ---');
const sampleRoomState = {
  furniture: [{ x: 10, y: 10, w: 20, h: 20 }],
  wallPattern: { type: 'stripe', count: 8, spacing: 90 },
  lightSource: { x: 400, y: 60, angle: 100 },
  clock: { hourHand: 3, minuteHand: 15 },
  calendarDate: '3',
  window: { sceneId: 0 },
};
let allNonDestructive = true;
for (const variant of VARIANTS) {
  const before = JSON.stringify(sampleRoomState);
  variant.apply(sampleRoomState, 5);
  const after = JSON.stringify(sampleRoomState);
  if (before !== after) {
    allNonDestructive = false;
    console.log(`  -> ${variant.id} が入力roomStateを破壊的に変更した`);
  }
}
check('全variantのapply()が入力roomStateを破壊的変更しない', allNonDestructive);

// --- wall-pattern-count-offの難易度減衰確認 ---
console.log('--- wall-pattern-count-off の難易度減衰 ---');
const wallVariant = VARIANTS.find((v) => v.id === 'wall-pattern-count-off');
const wallSampleRoomState = {
  furniture: [{ x: 10, y: 10, w: 20, h: 20 }],
  wallPattern: { type: 'stripe', count: 8, spacing: 90 },
  lightSource: { x: 400, y: 60, angle: 100 },
  clock: { hourHand: 3, minuteHand: 15 },
  calendarDate: '3',
  window: { sceneId: 0 },
};

function countChangedTrials(round, trials) {
  let changed = 0;
  for (let i = 0; i < trials; i++) {
    const result = wallVariant.apply(wallSampleRoomState, round);
    if (result.wallPattern.count !== wallSampleRoomState.wallPattern.count) {
      changed++;
    }
  }
  return changed;
}

const TRIALS = 500;
const changedAtRound0 = countChangedTrials(0, TRIALS);
const changedAtRound30 = countChangedTrials(30, TRIALS);
check(
  `round=0では常に変化が発生する (実際: ${changedAtRound0}/${TRIALS})`,
  changedAtRound0 === TRIALS
);
check(
  `round=30では変化の発生率がround=0より明確に低い (実際: ${changedAtRound30}/${TRIALS})`,
  changedAtRound30 < TRIALS * 0.8
);
check(
  `computeMagnitude(1, 30)が確率の下限0.6付近になっている (実際: ${computeMagnitude(1, 30)})`,
  Math.abs(computeMagnitude(1, 30) - 0.6) < 0.001
);

// --- 3. judgeChoice ---
console.log('--- judgeChoice ---');
function makeState(isVariant) {
  return {
    round: 3,
    bestRound: 5,
    isVariant,
    currentVariantId: isVariant ? VARIANTS[0].id : null,
    roomLayoutIndex: 0,
    recentVariantIds: [],
  };
}

const case1 = judgeChoice(makeState(true), true); // 異変あり + 戻る = 正解
check('異変あり + 戻る = 正解', case1.correct === true);
check('異変あり + 戻る = 正解 でroundが進む', case1.newState.round === 4);

const case2 = judgeChoice(makeState(true), false); // 異変あり + 進む = 不正解
check('異変あり + 進む = 不正解', case2.correct === false);

const case3 = judgeChoice(makeState(false), false); // 異変なし + 進む = 正解
check('異変なし + 進む = 正解', case3.correct === true);
check('異変なし + 進む = 正解 でroundが進む', case3.newState.round === 4);

const case4 = judgeChoice(makeState(false), true); // 異変なし + 戻る = 不正解
check('異変なし + 戻る = 不正解', case4.correct === false);

// --- nextRoundの導入強制（最初の2周は必ず異変なし） ---
console.log('--- nextRound: 最初の2周は強制的に異変なし ---');
const introState0 = startNewGame(); // round=0の周回
check('round=0はisVariantが常にfalse', introState0.isVariant === false);

const introState1 = nextRound({ ...introState0, round: 1 }); // round=1の周回
check('round=1はisVariantが常にfalse', introState1.isVariant === false);

let round2SawTrue = false;
let round2SawFalse = false;
for (let i = 0; i < 200; i++) {
  const round2State = nextRound({ ...introState1, round: 2 });
  if (round2State.isVariant) {
    round2SawTrue = true;
  } else {
    round2SawFalse = true;
  }
}
check('round=2以降はisVariantがtrueになることがある', round2SawTrue);
check('round=2以降はisVariantがfalseになることもある', round2SawFalse);

// --- 4. storage.js ---
console.log('--- storage.js ---');
saveBestRound(7);
check('saveBestRound/loadBestRoundが正しく動作する', loadBestRound() === 7);

saveBestRound(3);
check('saveBestRoundで上書きできる', loadBestRound() === 3);

check('初期状態でloadSurveyResponsesが空配列', Array.isArray(loadSurveyResponses()));

const beforeCount = loadSurveyResponses().length;
saveSurveyResponse({ wantToPlayAgain: 5, fearLevel: 4, difficultyLevel: 3, goodMoment: 'a', badMoment: 'b' });
saveSurveyResponse({ wantToPlayAgain: 2, fearLevel: 1, difficultyLevel: 2, goodMoment: 'c', badMoment: 'd' });
const afterResponses = loadSurveyResponses();
check('saveSurveyResponseで回答が蓄積される', afterResponses.length === beforeCount + 2);

const exported = exportSurveyAsJSON();
let exportedParsed = null;
try {
  exportedParsed = JSON.parse(exported);
} catch {
  exportedParsed = null;
}
check('exportSurveyAsJSONが有効なJSON文字列を返す', Array.isArray(exportedParsed));
check(
  'exportSurveyAsJSONの内容がloadSurveyResponsesと一致する',
  JSON.stringify(exportedParsed) === JSON.stringify(afterResponses)
);

// --- roundsReachedフィールドの保存・読み出し ---
console.log('--- roundsReached ---');
const beforeRoundsReachedCount = loadSurveyResponses().length;
saveSurveyResponse({
  wantToPlayAgain: 4,
  fearLevel: 3,
  difficultyLevel: 3,
  goodMoment: 'e',
  badMoment: 'f',
  roundsReached: 6,
  timestamp: new Date().toISOString(),
});
const afterRoundsReachedResponses = loadSurveyResponses();
check(
  'saveSurveyResponseで保存したroundsReachedが件数として蓄積される',
  afterRoundsReachedResponses.length === beforeRoundsReachedCount + 1
);
const savedResponse = afterRoundsReachedResponses[afterRoundsReachedResponses.length - 1];
check(
  '保存したレスポンスにroundsReachedフィールドが含まれる',
  typeof savedResponse.roundsReached === 'number'
);
check('roundsReachedの値が正しく読み出される', savedResponse.roundsReached === 6);

// --- localStorage未定義環境でのフォールバック確認 ---
console.log('--- localStorage未定義環境でのフォールバック ---');
const savedLocalStorage = globalThis.localStorage;
delete globalThis.localStorage;
try {
  const { loadBestRound: loadWithoutStorage, saveBestRound: saveWithoutStorage } = await import(
    `./storage.js?nocache=${Date.now()}`
  );
  let threw = false;
  try {
    saveWithoutStorage(9);
    loadWithoutStorage();
  } catch {
    threw = true;
  }
  check('localStorage未定義でも例外を投げない', !threw);
} finally {
  globalThis.localStorage = savedLocalStorage;
}

// --- 5. audio.js（window/AudioContext未定義のNode環境でも安全に動作すること） ---
console.log('--- audio.js（window未定義環境でのフォールバック） ---');
const {
  initAudio,
  startAmbientDrone,
  stopAmbientDrone,
  startHeartbeat,
  stopHeartbeat,
  playCorrectSound,
  playGameOverSound,
  setMuted,
  isMuted,
} = await import('./audio.js');

let audioThrew = false;
try {
  await initAudio();
  startAmbientDrone();
  startHeartbeat(3000);
  playCorrectSound();
  playGameOverSound();
  setMuted(true);
  isMuted();
  setMuted(false);
  stopHeartbeat();
  stopAmbientDrone();
} catch {
  audioThrew = true;
}
check('window未定義環境でaudio.jsの全関数呼び出しが例外を投げない', !audioThrew);
check('isMuted()がbooleanを返す', typeof isMuted() === 'boolean');

// --- 結果出力 ---
console.log('---');
if (failed) {
  console.log('TESTS FAILED');
  process.exit(1);
} else {
  console.log('ALL TESTS PASSED');
}
