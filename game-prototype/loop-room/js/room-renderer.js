// room-renderer.js
// base部屋レイアウトの生成とCanvas 2D描画を担当する。

const CANVAS_W = 800;
const CANVAS_H = 500;

// 5〜8種類のbaseレイアウト（家具配置・光源・時計・カレンダー・窓の外景・壁模様の初期値）
const BASE_LAYOUTS = [
  // 0: 応接室風、家具4つを左右非対称に配置
  {
    furniture: [
      { x: 120, y: 300, w: 70, h: 90 },
      { x: 260, y: 320, w: 60, h: 70 },
      { x: 560, y: 290, w: 80, h: 100 },
      { x: 420, y: 340, w: 50, h: 50 },
    ],
    wallPattern: { type: 'stripe', count: 8, spacing: 90 },
    lightSource: { x: 400, y: 60, angle: 100 },
    clock: { hourHand: 3, minuteHand: 15 },
    calendarDate: '3',
    window: { sceneId: 0 },
  },
  // 1: 書斎風、左右にほぼ対称の棚と机
  {
    furniture: [
      { x: 100, y: 280, w: 90, h: 120 },
      { x: 610, y: 280, w: 90, h: 120 },
      { x: 340, y: 350, w: 120, h: 60 },
    ],
    wallPattern: { type: 'brick', count: 6, spacing: 110 },
    lightSource: { x: 200, y: 50, angle: 120 },
    clock: { hourHand: 7, minuteHand: 45 },
    calendarDate: '14',
    window: { sceneId: 1 },
  },
  // 2: 食堂風、テーブルと椅子4脚
  {
    furniture: [
      { x: 330, y: 300, w: 140, h: 80 },
      { x: 300, y: 260, w: 30, h: 40 },
      { x: 470, y: 260, w: 30, h: 40 },
      { x: 300, y: 390, w: 30, h: 40 },
      { x: 470, y: 390, w: 30, h: 40 },
    ],
    wallPattern: { type: 'stripe', count: 10, spacing: 72 },
    lightSource: { x: 400, y: 40, angle: 90 },
    clock: { hourHand: 12, minuteHand: 0 },
    calendarDate: '1',
    window: { sceneId: 2 },
  },
  // 3: 寝室風、ベッドと棚
  {
    furniture: [
      { x: 150, y: 320, w: 160, h: 90 },
      { x: 600, y: 300, w: 60, h: 110 },
    ],
    wallPattern: { type: 'brick', count: 5, spacing: 130 },
    lightSource: { x: 620, y: 70, angle: 140 },
    clock: { hourHand: 9, minuteHand: 30 },
    calendarDate: '22',
    window: { sceneId: 3 },
  },
  // 4: 廊下風、等間隔の小家具が並ぶ
  {
    furniture: [
      { x: 140, y: 350, w: 40, h: 40 },
      { x: 280, y: 350, w: 40, h: 40 },
      { x: 420, y: 350, w: 40, h: 40 },
      { x: 560, y: 350, w: 40, h: 40 },
    ],
    wallPattern: { type: 'stripe', count: 12, spacing: 60 },
    lightSource: { x: 150, y: 55, angle: 80 },
    clock: { hourHand: 5, minuteHand: 5 },
    calendarDate: '9',
    window: { sceneId: 4 },
  },
  // 5: 応接室風その2、非対称な低家具
  {
    furniture: [
      { x: 180, y: 340, w: 100, h: 60 },
      { x: 500, y: 280, w: 70, h: 120 },
      { x: 380, y: 360, w: 40, h: 40 },
    ],
    wallPattern: { type: 'brick', count: 7, spacing: 95 },
    lightSource: { x: 500, y: 45, angle: 70 },
    clock: { hourHand: 2, minuteHand: 50 },
    calendarDate: '27',
    window: { sceneId: 5 },
  },
];

export function cloneRoomState(roomState) {
  return {
    furniture: roomState.furniture.map((f) => ({ ...f })),
    wallPattern: { ...roomState.wallPattern },
    lightSource: { ...roomState.lightSource },
    clock: { ...roomState.clock },
    calendarDate: roomState.calendarDate,
    window: { ...roomState.window },
  };
}

export function buildBaseRoomState(layoutIndex) {
  const layout = BASE_LAYOUTS[layoutIndex % BASE_LAYOUTS.length];
  return cloneRoomState(layout);
}

export function getLayoutCount() {
  return BASE_LAYOUTS.length;
}

// 窓の外景バリエーション（sceneIdごとに簡単な図形パターンを描き分ける）
function drawWindowScene(ctx, x, y, w, h, sceneId, brightnessMismatch) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();

  const skyColors = ['#2b2f3a', '#22262f', '#302733', '#1f2a2e', '#2a2233', '#242b2b'];
  ctx.fillStyle = skyColors[sceneId % skyColors.length];
  ctx.fillRect(x, y, w, h);

  // 窓の外の明るさと部屋の暗さが矛盾する異変（窓だけ不自然に明るい）
  if (brightnessMismatch) {
    ctx.fillStyle = `rgba(255,255,220,${brightnessMismatch * 0.5})`;
    ctx.fillRect(x, y, w, h);
  }

  // sceneIdに応じて月や木のシルエットの位置・数を変える
  ctx.fillStyle = '#3a3f4a';
  const treeCount = 2 + (sceneId % 3);
  for (let i = 0; i < treeCount; i++) {
    const tx = x + ((i + 1) * w) / (treeCount + 1);
    const th = h * (0.3 + 0.1 * ((i + sceneId) % 3));
    ctx.fillRect(tx - 4, y + h - th, 8, th);
  }

  ctx.fillStyle = '#4a4d55';
  ctx.beginPath();
  const moonX = x + w * (0.2 + 0.15 * (sceneId % 4));
  ctx.arc(moonX, y + h * 0.25, 10, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

function drawWallPattern(ctx, pattern) {
  const gradientStrength = pattern.gradientStrength || 0;
  if (pattern.type === 'stripe') {
    for (let i = 0; i < pattern.count; i++) {
      let x = 20 + i * pattern.spacing;
      if (pattern.floorTileJitter) {
        x += Math.sin(i * 1.7) * pattern.floorTileJitter * 0.3;
      }
      if (x > CANVAS_W - 20) break;
      const shade = 58 - Math.round(gradientStrength * 20 * (i / Math.max(1, pattern.count)));
      ctx.strokeStyle = `rgb(${shade},${shade},${shade})`;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x, 20);
      ctx.lineTo(x, 220);
      ctx.stroke();
    }
  } else if (pattern.type === 'brick') {
    let row = 0;
    for (let y = 20; y < 220; y += 30) {
      const offset = row % 2 === 0 ? 0 : pattern.spacing / 2;
      for (let i = 0; i < pattern.count; i++) {
        let x = 10 + offset + i * pattern.spacing;
        if (pattern.floorTileJitter) {
          x += Math.cos((i + row) * 1.3) * pattern.floorTileJitter * 0.3;
        }
        if (x > CANVAS_W - 10) break;
        const shade = 58 - Math.round(gradientStrength * 20 * (i / Math.max(1, pattern.count)));
        ctx.strokeStyle = `rgb(${shade},${shade},${shade})`;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x, y, pattern.spacing - 4, 28);
      }
      row++;
    }
  }

  // 壁の一部にごくわずかに違う色調のパッチを重ねる
  if (pattern.colorPatchAlpha) {
    ctx.fillStyle = `rgba(90,80,70,${pattern.colorPatchAlpha})`;
    ctx.fillRect(CANVAS_W * 0.4, 30, 120, 150);
  }
}

// 部屋の隅の影の濃さを左右非対称にする
function drawCornerShadowBias(ctx, bias) {
  if (!bias) return;
  ctx.fillStyle = `rgba(0,0,0,${0.15 + bias * 0.4})`;
  ctx.beginPath();
  ctx.moveTo(10, 10);
  ctx.lineTo(70, 10);
  ctx.lineTo(10, 90);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = 'rgba(0,0,0,0.08)';
  ctx.beginPath();
  ctx.moveTo(CANVAS_W - 10, 10);
  ctx.lineTo(CANVAS_W - 70, 10);
  ctx.lineTo(CANVAS_W - 10, 90);
  ctx.closePath();
  ctx.fill();
}

function drawClock(ctx, clock) {
  const cx = CANVAS_W - 90;
  const cy = 90;
  const r = 30;

  ctx.strokeStyle = '#555';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();

  const hourAngle = ((clock.hourHand % 12) / 12) * Math.PI * 2 - Math.PI / 2;
  const minAngle = ((clock.minuteHand % 60) / 60) * Math.PI * 2 - Math.PI / 2;

  ctx.strokeStyle = '#888';
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(hourAngle) * r * 0.5, cy + Math.sin(hourAngle) * r * 0.5);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(minAngle) * r * 0.8, cy + Math.sin(minAngle) * r * 0.8);
  ctx.stroke();

  // もう一つの時計がわずかにずれた場所に薄く見える異変
  if (clock.ghostOffset) {
    const gcx = cx + clock.ghostOffset;
    const gcy = cy;
    ctx.strokeStyle = 'rgba(150,150,150,0.25)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(gcx, gcy, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(gcx, gcy);
    ctx.lineTo(gcx + Math.cos(hourAngle) * r * 0.5, gcy + Math.sin(hourAngle) * r * 0.5);
    ctx.stroke();
  }
}

function drawCalendar(ctx, calendarDate) {
  const x = CANVAS_W - 160;
  const y = 60;
  ctx.strokeStyle = '#555';
  ctx.strokeRect(x, y, 40, 40);
  ctx.fillStyle = '#999';
  ctx.font = '16px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(String(calendarDate), x + 20, y + 26);
  ctx.textAlign = 'left';
}

function furnitureShadow(ctx, f, lightSource) {
  const cx = f.x + f.w / 2;
  const cy = f.y + f.h / 2;

  let nx;
  let ny;
  if (typeof lightSource.shadowAngleOverride === 'number') {
    // 光源の実位置と矛盾する向きに影を落とす異変
    const rad = (lightSource.shadowAngleOverride * Math.PI) / 180;
    nx = Math.cos(rad);
    ny = Math.sin(rad);
  } else {
    const dx = cx - lightSource.x;
    const dy = cy - lightSource.y;
    const dist = Math.max(1, Math.hypot(dx, dy));
    nx = dx / dist;
    ny = dy / dist;
  }

  const shadowLen =
    typeof f.shadowLengthOverride === 'number' ? f.shadowLengthOverride : f.h * 0.6;

  // 光源の強さが物理的にありえない均一さの場合、影を薄くする
  const uniformity = lightSource.uniformity || 0;
  const baseOpacity = typeof f.shadowOpacity === 'number' ? f.shadowOpacity : 1;
  const opacity = Math.max(0, 0.35 * baseOpacity * (1 - uniformity * 0.8));

  if (opacity <= 0.01) return;

  ctx.fillStyle = `rgba(0,0,0,${opacity})`;
  ctx.beginPath();
  ctx.ellipse(
    cx + nx * shadowLen,
    f.y + f.h + ny * shadowLen * 0.2,
    f.w * 0.6,
    f.h * 0.15,
    0,
    0,
    Math.PI * 2
  );
  ctx.fill();
}

export function render(ctx, roomState) {
  ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

  // 背景
  ctx.fillStyle = '#1a1a1a';
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

  // 床
  ctx.fillStyle = '#242424';
  ctx.fillRect(0, 220, CANVAS_W, CANVAS_H - 220);

  // 床タイル目地
  ctx.strokeStyle = '#2f2f2f';
  ctx.lineWidth = 1;
  for (let x = 0; x < CANVAS_W; x += 40) {
    ctx.beginPath();
    ctx.moveTo(x, 220);
    ctx.lineTo(x, CANVAS_H);
    ctx.stroke();
  }
  for (let y = 220; y < CANVAS_H; y += 40) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(CANVAS_W, y);
    ctx.stroke();
  }

  // 壁の輪郭
  ctx.strokeStyle = '#4a4a4a';
  ctx.lineWidth = 2;
  ctx.strokeRect(10, 10, CANVAS_W - 20, 210);

  drawWallPattern(ctx, roomState.wallPattern);
  drawCornerShadowBias(ctx, roomState.wallPattern.cornerShadowBias);

  // 窓
  drawWindowScene(
    ctx,
    60,
    60,
    100,
    100,
    roomState.window.sceneId,
    roomState.window.brightnessMismatch
  );
  ctx.strokeStyle = '#4a4a4a';
  ctx.lineWidth = 2;
  ctx.strokeRect(60, 60, 100, 100);

  drawClock(ctx, roomState.clock);
  drawCalendar(ctx, roomState.calendarDate);

  // 家具の影→本体の順で描画
  for (const f of roomState.furniture) {
    furnitureShadow(ctx, f, roomState.lightSource);
  }
  for (const f of roomState.furniture) {
    drawFurniturePiece(ctx, f);
  }

  drawVignette(ctx);
}

function drawVignette(ctx) {
  const vignette = ctx.createRadialGradient(
    CANVAS_W / 2,
    CANVAS_H / 2,
    CANVAS_H * 0.3,
    CANVAS_W / 2,
    CANVAS_H / 2,
    CANVAS_H * 0.75
  );
  vignette.addColorStop(0, 'rgba(0,0,0,0)');
  vignette.addColorStop(1, 'rgba(0,0,0,0.55)');
  ctx.fillStyle = vignette;
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
}

function drawFurniturePiece(ctx, f) {
  const floatOffset = f.floatOffset || 0;
  const y = f.y - floatOffset;
  const radius = typeof f.cornerRadius === 'number' ? f.cornerRadius : 3;
  const alpha = typeof f.ghostAlpha === 'number' ? f.ghostAlpha : 1;

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = '#2e2e2e';
  ctx.strokeStyle = '#666';
  ctx.lineWidth = typeof f.outlineWidth === 'number' ? f.outlineWidth : 2;

  ctx.beginPath();
  if (radius > 0 && typeof ctx.roundRect === 'function') {
    ctx.roundRect(f.x, y, f.w, f.h, Math.min(radius, f.w / 2, f.h / 2));
  } else {
    ctx.rect(f.x, y, f.w, f.h);
  }
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

export const CANVAS_WIDTH = CANVAS_W;
export const CANVAS_HEIGHT = CANVAS_H;
