// survey.js
// アンケート画面のUI制御。回答収集・storage.js経由での保存・クリップボードへのJSON出力を担当する。
// 巡室 survey.js の構造（フォーム送信→保存→結果コピー→タイトルへ）を踏襲。

import { saveSurveyResponse, exportSurveyAsJSON } from './storage.js';

let onBackToTitleCallback = null;
let getReachedWaveCallback = null;

/**
 * @param {{onBackToTitle?:()=>void, onSkip?:()=>void, getReachedWave?:()=>number}} opts
 */
export function initSurvey({ onBackToTitle, onSkip, getReachedWave } = {}) {
  onBackToTitleCallback = onBackToTitle || null;
  getReachedWaveCallback = getReachedWave || null;

  const form = document.getElementById('survey-form');
  const afterSubmit = document.getElementById('survey-after-submit');
  const skipButton = document.getElementById('survey-skip-button');
  const backTitleButton = document.getElementById('survey-back-title-button');
  const copyStatus = document.getElementById('survey-copy-status');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const response = {
      wantToPlayAgain: Number(formData.get('wantToPlayAgain')),
      adaptationFelt: Number(formData.get('adaptationFelt')),
      difficultyLevel: Number(formData.get('difficultyLevel')),
      goodMoment: String(formData.get('goodMoment') || ''),
      badMoment: String(formData.get('badMoment') || ''),
      reachedWave: getReachedWaveCallback ? getReachedWaveCallback() : 0,
      timestamp: new Date().toISOString(),
    };
    saveSurveyResponse(response);
    form.classList.add('hidden');
    afterSubmit.classList.remove('hidden');
    copyStatus.textContent = '';

    const json = exportSurveyAsJSON();
    try {
      await navigator.clipboard.writeText(json);
      copyStatus.textContent = 'コピーしました';
    } catch {
      copyStatus.textContent = 'コピーに失敗しました（クリップボード権限を確認してください）';
    }
  });

  skipButton.addEventListener('click', () => {
    resetSurveyScreen();
    if (onSkip) onSkip();
    else if (onBackToTitleCallback) onBackToTitleCallback();
  });

  backTitleButton.addEventListener('click', () => {
    resetSurveyScreen();
    if (onBackToTitleCallback) onBackToTitleCallback();
  });
}

export function resetSurveyScreen() {
  const form = document.getElementById('survey-form');
  const afterSubmit = document.getElementById('survey-after-submit');
  const copyStatus = document.getElementById('survey-copy-status');
  form.reset();
  form.classList.remove('hidden');
  afterSubmit.classList.add('hidden');
  copyStatus.textContent = '';
}
