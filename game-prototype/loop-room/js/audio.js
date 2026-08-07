// audio.js
// Web Audio APIによるプロシージャル音響合成のみで恐怖演出用のサウンドを生成する。
// 外部音声ファイル・外部CDNは一切使用しない。

let audioCtx = null;
let muted = false;

let droneNodes = null; // { oscillator, gainNode, oscillator2, gainNode2 }
let heartbeatTimerId = null;
let heartbeatIntervalMs = null;

function safeCreateAudioContext() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    return new Ctx();
  } catch {
    return null;
  }
}

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

export function startAmbientDrone() {
  if (!audioCtx || droneNodes) return;
  try {
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.value = 130;
    gainNode.gain.value = 0.07 * currentMuteGain();
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    oscillator.start();

    // うなり（ビート）を生じさせるため、わずかにずらした周波数の2本目を重ねる
    const oscillator2 = audioCtx.createOscillator();
    const gainNode2 = audioCtx.createGain();
    oscillator2.type = 'sine';
    oscillator2.frequency.value = 130 * 1.03;
    gainNode2.gain.value = 0.035 * currentMuteGain();
    oscillator2.connect(gainNode2);
    gainNode2.connect(audioCtx.destination);
    oscillator2.start();

    droneNodes = { oscillator, gainNode, oscillator2, gainNode2 };
  } catch {
    droneNodes = null;
  }
}

export function stopAmbientDrone() {
  if (!droneNodes) return;
  try {
    droneNodes.oscillator.stop();
    droneNodes.oscillator.disconnect();
    droneNodes.gainNode.disconnect();
    droneNodes.oscillator2.stop();
    droneNodes.oscillator2.disconnect();
    droneNodes.gainNode2.disconnect();
  } catch {
    // 何もしない
  } finally {
    droneNodes = null;
  }
}

function playHeartbeatPulse() {
  if (!audioCtx) return;
  try {
    playSinglePulse(1);
    setTimeout(() => playSinglePulse(0.6), 60);
  } catch {
    // 何もしない
  }
}

function playSinglePulse(gainScale) {
  if (!audioCtx) return;
  try {
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    const now = audioCtx.currentTime;
    oscillator.type = 'sine';
    oscillator.frequency.value = 95;
    gainNode.gain.setValueAtTime(0.0001, now);
    gainNode.gain.linearRampToValueAtTime(0.45 * gainScale * currentMuteGain(), now + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.15);
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.15);
  } catch {
    // 何もしない
  }
}

export function startHeartbeat(intervalMs) {
  if (!audioCtx) return;
  if (heartbeatTimerId !== null && heartbeatIntervalMs === intervalMs) return;
  stopHeartbeat();
  heartbeatIntervalMs = intervalMs;
  try {
    heartbeatTimerId = setInterval(playHeartbeatPulse, intervalMs);
  } catch {
    heartbeatTimerId = null;
  }
}

export function stopHeartbeat() {
  if (heartbeatTimerId !== null) {
    try {
      clearInterval(heartbeatTimerId);
    } catch {
      // 何もしない
    }
  }
  heartbeatTimerId = null;
  heartbeatIntervalMs = null;
}

export function playCorrectSound() {
  if (!audioCtx) return;
  try {
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    const now = audioCtx.currentTime;
    oscillator.type = 'sine';
    oscillator.frequency.value = 800;
    gainNode.gain.setValueAtTime(0.15 * currentMuteGain(), now);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.2);
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.2);
  } catch {
    // 何もしない
  }
}

export function playGameOverSound() {
  if (!audioCtx) return;
  try {
    const now = audioCtx.currentTime;
    const gainNode = audioCtx.createGain();
    gainNode.gain.setValueAtTime(0.2 * currentMuteGain(), now);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.5);
    gainNode.connect(audioCtx.destination);

    const osc1 = audioCtx.createOscillator();
    osc1.type = 'sawtooth';
    osc1.frequency.value = 110;
    osc1.connect(gainNode);

    const osc2 = audioCtx.createOscillator();
    osc2.type = 'sawtooth';
    osc2.frequency.value = 116;
    osc2.connect(gainNode);

    osc1.start(now);
    osc2.start(now);
    osc1.stop(now + 0.5);
    osc2.stop(now + 0.5);
  } catch {
    // 何もしない
  }
}

export function setMuted(value) {
  muted = value;
  if (droneNodes) {
    try {
      droneNodes.gainNode.gain.value = 0.07 * currentMuteGain();
      droneNodes.gainNode2.gain.value = 0.035 * currentMuteGain();
    } catch {
      // 何もしない
    }
  }
}

export function isMuted() {
  return muted;
}
