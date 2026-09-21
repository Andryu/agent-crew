import type { CSSProperties } from "react";

// SVGの feTurbulence フィルターは Remotion のヘッドレスレンダリング（フレーム書き出し）で
// 反映されないことを実測で確認したため、フィルタープリミティブに依存しない
// 複数の radial-gradient を互いに素に近いタイルサイズで重ねることで斑点/ざらつきを表現する。
// （タイルサイズをずらすことでモアレ状の非周期パターンになり、単調な繰り返しに見えにくい）
const SPECKLE_LAYERS: Array<{ x: string; y: string; alpha: number; tile: number }> = [
  { x: "12%", y: "18%", alpha: 0.05, tile: 37 },
  { x: "68%", y: "52%", alpha: 0.045, tile: 53 },
  { x: "38%", y: "82%", alpha: 0.05, tile: 61 },
  { x: "84%", y: "12%", alpha: 0.04, tile: 43 },
  { x: "22%", y: "60%", alpha: 0.045, tile: 29 },
];

const SPECKLE_BACKGROUND_IMAGE = SPECKLE_LAYERS.map(
  ({ x, y, alpha }) =>
    `radial-gradient(circle at ${x} ${y}, rgba(0,0,0,${alpha}) 0px, rgba(0,0,0,${alpha}) 1.4px, transparent 2px)`,
).join(", ");

const SPECKLE_BACKGROUND_SIZE = SPECKLE_LAYERS.map(({ tile }) => `${tile}px ${tile}px`).join(", ");
const SPECKLE_BACKGROUND_REPEAT = SPECKLE_LAYERS.map(() => "repeat").join(", ");

/**
 * 単色背景の代わりに使う「薄い紙風テクスチャ」。
 * Cutの背景（画像が全面を覆わない場合の下地）とPlaceholderCutの両方で共通利用する。
 */
export const paperTextureStyle = (baseColor: string): CSSProperties => ({
  backgroundColor: baseColor,
  backgroundImage: `${SPECKLE_BACKGROUND_IMAGE}, radial-gradient(ellipse at 50% 0%, rgba(0,0,0,0.045), rgba(0,0,0,0) 70%)`,
  backgroundRepeat: `${SPECKLE_BACKGROUND_REPEAT}, no-repeat`,
  backgroundSize: `${SPECKLE_BACKGROUND_SIZE}, 100% 100%`,
});
