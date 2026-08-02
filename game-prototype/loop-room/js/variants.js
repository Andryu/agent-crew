// variants.js
// 「異変あり」周回で部屋に適用する変異パターン一覧。
// 各variantのapply(roomState, round)は、baseとなるroomStateを破壊的に変更せず、
// 変異後の新しいroomStateオブジェクトを返す。

import { cloneRoomState } from './room-renderer.js';

export function computeMagnitude(baseMagnitude, round) {
  return baseMagnitude * Math.max(0.25, 1 - round * 0.03);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

export const VARIANTS = [
  {
    id: 'equal-spacing-furniture',
    name: '家具が不自然に等間隔・等距離に配置されている',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const ratio = computeMagnitude(1, round);
      const n = next.furniture.length;
      if (n === 0) return next;
      const startX = next.furniture[0].x;
      const spacing = 90;
      next.furniture = next.furniture.map((f, i) => ({
        ...f,
        x: lerp(f.x, startX + i * spacing, ratio),
        y: lerp(f.y, next.furniture[0].y, ratio * 0.5),
      }));
      return next;
    },
  },
  {
    id: 'shadow-direction-mismatch',
    name: '影の向きが部屋の光源の位置と矛盾している',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const offsetDeg = computeMagnitude(180, round);
      next.lightSource = {
        ...next.lightSource,
        shadowAngleOverride: (next.lightSource.angle + offsetDeg) % 360,
      };
      return next;
    },
  },
  {
    id: 'wall-pattern-count-off',
    name: '壁の模様の反復回数が本来より1つ多い/少ない',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const probability = computeMagnitude(1, round);
      const delta = Math.random() < probability ? (round % 2 === 0 ? 1 : -1) : 0;
      next.wallPattern.count = Math.max(1, next.wallPattern.count + delta);
      return next;
    },
  },
  {
    id: 'mirrored-furniture',
    name: '家具の配置が意味もなく左右鏡写しになっている',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const ratio = computeMagnitude(1, round);
      const centerX = 400;
      next.furniture = next.furniture.map((f, i) => {
        if (i % 2 === 0) return f;
        const mirrorPartner = next.furniture[i - 1] || f;
        const mirroredX = centerX * 2 - mirrorPartner.x - mirrorPartner.w;
        return { ...f, x: lerp(f.x, mirroredX, ratio), y: lerp(f.y, mirrorPartner.y, ratio) };
      });
      return next;
    },
  },
  {
    id: 'clock-calendar-mismatch',
    name: '壁掛け時計の針の位置と、カレンダーの表示日付が矛盾している',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(1, round);
      if (strength >= 0.5) {
        next.calendarDate = `${next.calendarDate}?`;
      }
      next.clock = {
        hourHand: (next.clock.hourHand + Math.round(6 * strength)) % 12,
        minuteHand: next.clock.minuteHand,
      };
      return next;
    },
  },
  {
    id: 'window-scene-changed',
    name: '窓の外の景色だけが前回と違う',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(1, round);
      const shift = strength >= 0.5 ? 3 : 1;
      next.window = { sceneId: (next.window.sceneId + shift) % 6 };
      return next;
    },
  },
  {
    id: 'corner-shadow-asymmetry',
    name: '部屋の隅の影の濃さが左右で異なる',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(0.5, round);
      next.wallPattern.cornerShadowBias = strength;
      return next;
    },
  },
  {
    id: 'chair-leg-length-diff',
    name: '同一のはずの複数の椅子の脚の長さが微妙に違う',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(12, round);
      next.furniture = next.furniture.map((f, i) =>
        i === next.furniture.length - 1 ? { ...f, h: f.h + strength } : f
      );
      return next;
    },
  },
  {
    id: 'tile-grout-spacing-uneven',
    name: '床のタイル目地の間隔が部分的に均一すぎる/不均一すぎる',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(20, round);
      next.wallPattern.floorTileJitter = strength;
      return next;
    },
  },
  {
    id: 'perfect-right-angle-corner',
    name: '家具の角がすべて不自然に完全な直角（他は違うのに1つだけ完璧）',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(6, round);
      next.furniture = next.furniture.map((f, i) => ({
        ...f,
        cornerRadius: i === 0 ? 0 : strength,
      }));
      return next;
    },
  },
  {
    id: 'wall-color-patch',
    name: '壁の色が部分的にごくわずかに違う色調になっている',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(40, round);
      next.wallPattern.colorPatchAlpha = strength / 255;
      return next;
    },
  },
  {
    id: 'outline-thickness-anomaly',
    name: '物の輪郭線の太さが1箇所だけ違う',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(4, round);
      next.furniture = next.furniture.map((f, i) =>
        i === 0 ? { ...f, outlineWidth: 2 + strength } : f
      );
      return next;
    },
  },
  {
    id: 'diagonal-duplicate-object',
    name: '部屋の隅にあるはずの物が対角線対称の位置に複製されたように見える',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(1, round);
      const source = next.furniture[0];
      if (source) {
        next.furniture = [
          ...next.furniture,
          {
            x: 800 - source.x - source.w,
            y: 500 - source.y - source.h,
            w: source.w,
            h: source.h,
            ghostAlpha: 0.3 + 0.5 * strength,
          },
        ];
      }
      return next;
    },
  },
  {
    id: 'uniform-light-intensity',
    name: '光源から発生する光の強さが物理的にありえない均一さで部屋全体を照らしている',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(1, round);
      next.lightSource = { ...next.lightSource, uniformity: strength };
      return next;
    },
  },
  {
    id: 'shadow-length-not-proportional',
    name: '家具の影の長さが物体の高さと比例していない（本来長短あるはずが全て同じ長さ）',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(1, round);
      const fixedLen = 40;
      next.furniture = next.furniture.map((f) => ({
        ...f,
        shadowLengthOverride: lerp(f.h * 0.6, fixedLen, strength),
      }));
      return next;
    },
  },
  {
    id: 'furniture-floating',
    name: '家具が床から不自然に浮いている',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(14, round);
      next.furniture = next.furniture.map((f, i) =>
        i === next.furniture.length - 1 ? { ...f, floatOffset: strength } : f
      );
      return next;
    },
  },
  {
    id: 'duplicate-clock',
    name: '時計がもう一つ、わずかにずれた場所にも見える',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(30, round);
      next.clock = { ...next.clock, ghostOffset: strength };
      return next;
    },
  },
  {
    id: 'missing-furniture-shadow',
    name: '特定の家具だけ影がない',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(1, round);
      next.furniture = next.furniture.map((f, i) =>
        i === 0 ? { ...f, shadowOpacity: Math.max(0, 1 - strength) } : f
      );
      return next;
    },
  },
  {
    id: 'wall-pattern-color-gradient',
    name: '壁の模様の色が部分的に不自然なグラデーションになっている',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(1, round);
      next.wallPattern.gradientStrength = strength;
      return next;
    },
  },
  {
    id: 'window-light-mismatch',
    name: '窓の外の明るさと部屋の照らされ方が矛盾している',
    apply(roomState, round) {
      const next = cloneRoomState(roomState);
      const strength = computeMagnitude(1, round);
      next.window = { ...next.window, brightnessMismatch: strength };
      return next;
    },
  },
];
