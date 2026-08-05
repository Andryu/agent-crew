import { interpolate } from "remotion";
import type { CameraEffect } from "./types";

/**
 * カメラ演出のCSS transformを計算する。
 * zoom-in / zoom-out / pan はCapCut風の滑らかな動き。
 * shake はフレーム単位のステップ関数で、手描きアニメらしいカクカク感を出す（補間しない）。
 */
export const getCameraTransform = (
  camera: CameraEffect | undefined,
  frame: number,
  durationInFrames: number,
): string => {
  const progress = interpolate(frame, [0, Math.max(durationInFrames - 1, 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  switch (camera) {
    case "zoom-in": {
      const scale = interpolate(progress, [0, 1], [1, 1.18]);
      return `scale(${scale})`;
    }
    case "zoom-out": {
      const scale = interpolate(progress, [0, 1], [1.18, 1]);
      return `scale(${scale})`;
    }
    case "pan": {
      const x = interpolate(progress, [0, 1], [-3, 3]);
      return `scale(1.08) translateX(${x}%)`;
    }
    case "kenburns": {
      // イラスト日記モード用のごく控えめなKen Burns。カット全体でscale 1.0→1.05のみ、パン無し
      const scale = interpolate(progress, [0, 1], [1.0, 1.05]);
      return `scale(${scale})`;
    }
    case "shake": {
      // 6パターンのジッターを frame % 6 でステップ切り替え（補間しない＝カクカク）
      const pattern: Array<[number, number]> = [
        [0, 0],
        [4, -3],
        [-3, 3],
        [3, 2],
        [-4, -2],
        [2, -4],
      ];
      const [x, y] = pattern[frame % pattern.length];
      return `scale(1.06) translate(${x}px, ${y}px)`;
    }
    case "none":
    default:
      return "none";
  }
};
