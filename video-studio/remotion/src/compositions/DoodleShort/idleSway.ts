const STEP_FPS = 2;

// あらかじめ用意した8パターンのゆらぎ（上下±0.5%以内 + 微小回転±0.3度以内）。
// 「静かにわずかに息づく」程度まで振幅を絞り、ステップ頻度も落として忙しなさを解消。
// Math.random は使わず、固定テーブルを frame からステップ的に選ぶことで
// レンダリングごとの再現性を保ちつつ、滑らかな補間をしない（手書きのカクカク感）。
const SWAY_PATTERN: Array<{ y: number; r: number }> = [
  { y: 0, r: 0 },
  { y: -0.4, r: 0.2 },
  { y: 0.25, r: -0.3 },
  { y: -0.2, r: 0.3 },
  { y: 0.5, r: -0.15 },
  { y: -0.3, r: 0.15 },
  { y: 0.35, r: -0.25 },
  { y: -0.5, r: 0.25 },
];

// 画像/プレースホルダー用の安全マージン（回転・平行移動で端が透けないよう気持ち拡大しておく）
// 振幅を大幅に縮小したため、マージンも最小限に絞る
const SWAY_SAFETY_SCALE = 1.02;

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
