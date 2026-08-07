// audio.js
// Web Audio APIによるプロシージャル音響合成のみで恐怖演出用のサウンドを生成する。
// 外部音声ファイル・外部CDNは一切使用しない。

let audioCtx = null;
let muted = false;

let droneNodes = null; // { oscillator, gainNode }
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

export function initAudio() {
  if (audioCtx) return;
  try {
    audioCtx = safeCreateAudioContext();
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume().catch(() => {});
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
    oscillator.frequency.value = 68;
    gainNode.gain.value = 0.035 * currentMuteGain();
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    oscillator.start();
    droneNodes = { oscillator, gainNode };
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
  } catch {
    // 何もしない
  } finally {
    droneNodes = null;
  }
}

function playHeartbeatPulse() {
  if (!audioCtx) return;
  try {
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    const now = audioCtx.currentTime;
    oscillator.type = 'sine';
    oscillator.frequency.value = 55;
    gainNode.gain.setValueAtTime(0.0001, now);
    gainNode.gain.linearRampToValueAtTime(0.3 * currentMuteGain(), now + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.1);
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.1);
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
      droneNodes.gainNode.gain.value = 0.035 * currentMuteGain();
    } catch {
      // 何もしない
    }
  }
}

export function isMuted() {
  return muted;
}
