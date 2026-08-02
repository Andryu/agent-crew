// survey.js
// アンケート画面のUI制御。回答収集・storage.js経由での保存・
// クリップボードへのJSON出力を担当する。

import { saveSurveyResponse, exportSurveyAsJSON } from './storage.js';

let onBackToTitleCallback = null;

export function initSurvey({ onBackToTitle } = {}) {
  onBackToTitleCallback = onBackToTitle || null;

  const form = document.getElementById('survey-form');
  const afterSubmit = document.getElementById('survey-after-submit');
  const copyButton = document.getElementById('survey-copy-button');
  const backTitleButton = document.getElementById('survey-back-title-button');
  const copyStatus = document.getElementById('survey-copy-status');

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const response = {
      wantToPlayAgain: Number(formData.get('wantToPlayAgain')),
      fearLevel: Number(formData.get('fearLevel')),
      difficultyLevel: Number(formData.get('difficultyLevel')),
      goodMoment: String(formData.get('goodMoment') || ''),
      badMoment: String(formData.get('badMoment') || ''),
      timestamp: new Date().toISOString(),
    };
    saveSurveyResponse(response);
    form.classList.add('hidden');
    afterSubmit.classList.remove('hidden');
  });

  copyButton.addEventListener('click', async () => {
    const json = exportSurveyAsJSON();
    try {
      await navigator.clipboard.writeText(json);
      copyStatus.textContent = 'コピーしました';
    } catch {
      copyStatus.textContent = 'コピーに失敗しました（クリップボード権限を確認してください）';
    }
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
