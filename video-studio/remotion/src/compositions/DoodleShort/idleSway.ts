const STEP_FPS = 6;

// あらかじめ用意した8パターンのゆらぎ（上下±1〜2% + 微小回転±1.5度程度）。
// Math.random は使わず、固定テーブルを frame からステップ的に選ぶことで
// レンダリングごとの再現性を保ちつつ、滑らかな補間をしない（手書きのカクカク感）。
const SWAY_PATTERN: Array<{ y: number; r: number }> = [
  { y: 0, r: 0 },
  { y: -1.4, r: 0.9 },
  { y: 0.8, r: -1.2 },
  { y: -0.6, r: 1.5 },
  { y: 1.6, r: -0.7 },
  { y: -0.9, r: 0.6 },
  { y: 1.1, r: -1.4 },
  { y: -1.7, r: 1.1 },
];

// 画像/プレースホルダー用の安全マージン（回転・平行移動で端が透けないよう気持ち拡大しておく）
const SWAY_SAFETY_SCALE = 1.05;

/**
 * 「手書き風の揺れ」の transform を計算する。
 * カメラ演出（cameraEffect.ts）とは独立したレイヤーに適用し、両方を重ねがけできるようにする。
 * seed をカット番号などからずらして渡すと、カットごとに揺れの位相が変わる。
 */
export const getIdleSwayTransform = (frame: number, fps: number, seed = 0): string => {
  const framesPerStep = Math.max(1, Math.round(fps / STEP_FPS));
  const step = Math.floor(frame / framesPerStep) + seed;
  const index = ((step % SWAY_PATTERN.length) + SWAY_PATTERN.length) % SWAY_PATTERN.length;
  const { y, r } = SWAY_PATTERN[index];
  return `scale(${SWAY_SAFETY_SCALE}) translateY(${y}%) rotate(${r}deg)`;
};
