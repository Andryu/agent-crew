// audio.js
// Web Audio APIによるプロシージャル音響合成のみでSE 4種（配置・撃破・到達被害・ウェーブ開始）を生成する。
// 外部音声ファイル・外部CDNは一切使用しない。BGMなし。
// 巡室 audio.js の初期化ガード（AudioContext生成・再生いずれも失敗時は無音で続行）を踏襲。

let audioCtx = null;
let muted = false;

function safeCreateAudioContext() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    return new Ctx();
  } catch {
    return null;
  }
}

/**
 * AudioContextを初期化する。ユーザー操作（クリック等）のハンドラ内から呼ぶこと。
 * 失敗しても例外は投げず、以後の再生関数は無音で続行する。
 */
export async function initAudio() {
  if (audioCtx) return;
  try {
    audioCtx = safeCreateAudioContext();
    if (audioCtx && audioCtx.state === 'suspended') {
      await audioCtx.resume().catch(() => {});
    }
  } catch {
    audioCtx = null;
  }
}

function currentMuteGain() {
  return muted ? 0 : 1;
}

function playTone({ freq, type = 'sine', duration = 0.1, peakGain = 0.2, freqEnd = null }) {
  if (!audioCtx) return;
  try {
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    const now = audioCtx.currentTime;
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(freq, now);
    if (freqEnd !== null) {
      oscillator.frequency.linearRampToValueAtTime(freqEnd, now + duration);
    }
    gainNode.gain.setValueAtTime(0.0001, now);
    gainNode.gain.linearRampToValueAtTime(peakGain * currentMuteGain(), now + 0.01);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    oscillator.start(now);
    oscillator.stop(now + duration + 0.02);
  } catch {
    // 再生失敗はゲーム進行を止めない（無音で続行）
  }
}

/**
 * 配置音。塔の売却時（低ピッチ再生）にも流用する。
 * @param {boolean} [lowPitch] trueで売却時の低ピッチ版を再生する
 */
export function playPlace(lowPitch = false) {
  playTone({
    freq: lowPitch ? 320 : 520,
    type: 'triangle',
    duration: 0.08,
    peakGain: 0.15,
  });
}

/** 撃破音 */
export function playKill() {
  playTone({
    freq: 700,
    freqEnd: 300,
    type: 'square',
    duration: 0.08,
    peakGain: 0.12,
  });
}

/** 到達被害音（臓器へのダメージ） */
export function playHit() {
  playTone({
    freq: 160,
    freqEnd: 80,
    type: 'sawtooth',
    duration: 0.2,
    peakGain: 0.2,
  });
}

/** ウェーブ開始音 */
export function playWaveStart() {
  playTone({
    freq: 300,
    freqEnd: 700,
    type: 'sine',
    duration: 0.25,
    peakGain: 0.15,
  });
}

/**
 * @param {boolean} value
 */
export function setMuted(value) {
  muted = value;
}

/**
 * @returns {boolean}
 */
export function isMuted() {
  return muted;
}
