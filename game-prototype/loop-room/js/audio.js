// audio.js
// Web Audio APIによるプロシージャル音響合成のみで恐怖演出用のサウンドを生成する。
// 外部音声ファイル・外部CDNは一切使用しない。

let audioCtx = null;
let muted = false;

// ルート音(130Hz)を基準にした不穏な音程比。ルート／短3度／トライトーン(増4度)／オクターブ。
const DRONE_ROOT_FREQ = 130;
const DRONE_INTERVAL_RATIOS = [1, 1.1892, 1.4142, 2];
const DRONE_OSC_GAINS = [0.15, 0.1, 0.08, 0.04];
// 音色をゆっくり揺らす対象は短3度・トライトーンのみ（ルートとオクターブは支柱として固定する）
const DRONE_WANDER_INDEXES = [1, 2];

let droneState = null; // { oscillators[], gainNodes[], masterGain, lfos[], currentRatios[], shiftTimerId }
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

function scheduleDroneTimbralShift() {
  // 30〜45秒間隔で、短3度／トライトーンのどちらか1本を3〜5秒かけて別の不穏な音程へ遷移させる
  const delay = 30000 + Math.random() * 15000;
  droneState.shiftTimerId = setTimeout(() => {
    if (!droneState) return;
    try {
      const idx = DRONE_WANDER_INDEXES[Math.floor(Math.random() * DRONE_WANDER_INDEXES.length)];
      const candidates = DRONE_INTERVAL_RATIOS.filter((r) => r !== droneState.currentRatios[idx]);
      const newRatio = candidates[Math.floor(Math.random() * candidates.length)];
      const rampDuration = 3 + Math.random() * 2;
      const now = audioCtx.currentTime;
      const osc = droneState.oscillators[idx];
      osc.frequency.cancelScheduledValues(now);
      osc.frequency.setValueAtTime(osc.frequency.value, now);
      osc.frequency.linearRampToValueAtTime(DRONE_ROOT_FREQ * newRatio, now + rampDuration);
      droneState.currentRatios[idx] = newRatio;
    } catch {
      // 何もしない
    }
    scheduleDroneTimbralShift();
  }, delay);
}

export function startAmbientDrone() {
  if (!audioCtx || droneState) return;
  try {
    const now = audioCtx.currentTime;

    const masterGain = audioCtx.createGain();
    masterGain.gain.setValueAtTime(0.0001, now);
    masterGain.connect(audioCtx.destination);

    const oscillators = [];
    const gainNodes = [];
    const lfos = [];
    const currentRatios = [...DRONE_INTERVAL_RATIOS];

    DRONE_INTERVAL_RATIOS.forEach((ratio, i) => {
      const freq = DRONE_ROOT_FREQ * ratio;

      const oscillator = audioCtx.createOscillator();
      oscillator.type = 'sine';
      oscillator.frequency.value = freq;

      const gainNode = audioCtx.createGain();
      gainNode.gain.value = DRONE_OSC_GAINS[i];

      oscillator.connect(gainNode);
      gainNode.connect(masterGain);
      oscillator.start();

      // 有機的な揺らぎ（ビブラート）: LFOオシレーターでこの音のfrequencyを微変調する
      const lfo = audioCtx.createOscillator();
      lfo.type = 'sine';
      lfo.frequency.value = 0.1 + Math.random() * 0.2; // 0.1〜0.3Hz
      const lfoDepth = audioCtx.createGain();
      lfoDepth.gain.value = freq * 0.006; // 元周波数の1%未満の変動幅
      lfo.connect(lfoDepth);
      lfoDepth.connect(oscillator.frequency);
      lfo.start();

      oscillators.push(oscillator);
      gainNodes.push(gainNode);
      lfos.push({ oscillator: lfo, depthGain: lfoDepth });
    });

    droneState = { oscillators, gainNodes, masterGain, lfos, currentRatios, shiftTimerId: null };

    // フェードイン（1.5秒かけて目標音量へ）。ループ処理で経過した時間を無視しないよう、ここで現在時刻を取り直す
    const fadeStart = audioCtx.currentTime;
    masterGain.gain.setValueAtTime(0.0001, fadeStart);
    masterGain.gain.linearRampToValueAtTime(currentMuteGain(), fadeStart + 1.5);

    scheduleDroneTimbralShift();
  } catch (err) {
    console.error('[audio] startAmbientDrone failed:', err);
    droneState = null;
  }
}

export function stopAmbientDrone() {
  if (!droneState || !audioCtx) return;
  const state = droneState;
  droneState = null;
  try {
    if (state.shiftTimerId !== null) clearTimeout(state.shiftTimerId);

    const now = audioCtx.currentTime;
    const fadeOutSeconds = 0.4;
    state.masterGain.gain.cancelScheduledValues(now);
    state.masterGain.gain.setValueAtTime(state.masterGain.gain.value, now);
    state.masterGain.gain.linearRampToValueAtTime(0.0001, now + fadeOutSeconds);

    setTimeout(() => {
      try {
        state.oscillators.forEach((osc) => {
          osc.stop();
          osc.disconnect();
        });
        state.gainNodes.forEach((g) => g.disconnect());
        state.lfos.forEach((lfo) => {
          lfo.oscillator.stop();
          lfo.oscillator.disconnect();
          lfo.depthGain.disconnect();
        });
        state.masterGain.disconnect();
      } catch (err) {
        console.error('[audio] stopAmbientDrone failed:', err);
      }
    }, fadeOutSeconds * 1000 + 50);
  } catch (err) {
    console.error('[audio] stopAmbientDrone failed:', err);
  }
}

function playHeartbeatPulse() {
  if (!audioCtx) return;
  try {
    playSinglePulse(1);
    setTimeout(() => playSinglePulse(0.6), 60);
  } catch (err) {
    console.error('[audio] playHeartbeatPulse failed:', err);
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
  } catch (err) {
    console.error('[audio] playSinglePulse failed:', err);
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
  } catch (err) {
    console.error('[audio] playCorrectSound failed:', err);
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
  } catch (err) {
    console.error('[audio] playGameOverSound failed:', err);
  }
}

export function setMuted(value) {
  muted = value;
  if (droneState) {
    try {
      droneState.masterGain.gain.value = currentMuteGain();
    } catch {
      // 何もしない
    }
  }
}

export function isMuted() {
  return muted;
}
