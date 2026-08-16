// renderer.js
// Canvas描画（盤面・塔・個体の見た目直結・弾軌跡）。論理解像度576x384。
// DOM(Canvas 2D Context)に依存するため test.mjs では構文チェックのみ行う。

import {
  GRID,
  TOWERS,
  TOWER_COLORS,
  TOWER_SHAPES,
  RESIST_COLORS,
  RESIST_MARKER_SHAPES,
  GENOME_RANGES,
} from './config.js';

const CELL = GRID.cellSize;
const CANVAS_W = GRID.cols * CELL;
const CANVAS_H = GRID.rows * CELL;

export const LOGICAL_WIDTH = CANVAS_W;
export const LOGICAL_HEIGHT = CANVAS_H;

function cellToPx(col, row) {
  return { x: col * CELL + CELL / 2, y: row * CELL + CELL / 2 };
}

function drawGrid(ctx) {
  ctx.save();
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  for (let c = 0; c <= GRID.cols; c++) {
    ctx.beginPath();
    ctx.moveTo(c * CELL, 0);
    ctx.lineTo(c * CELL, CANVAS_H);
    ctx.stroke();
  }
  for (let r = 0; r <= GRID.rows; r++) {
    ctx.beginPath();
    ctx.moveTo(0, r * CELL);
    ctx.lineTo(CANVAS_W, r * CELL);
    ctx.stroke();
  }
  ctx.restore();
}

function drawLanes(ctx) {
  ctx.save();
  ctx.fillStyle = 'rgba(120, 160, 220, 0.10)';
  for (const row of GRID.laneRows) {
    ctx.fillRect(0, row * CELL, CANVAS_W, CELL);
  }
  // 模様入りの帯（進行方向を示す簡易な矢羽根パターン）
  ctx.strokeStyle = 'rgba(120, 160, 220, 0.25)';
  ctx.lineWidth = 1;
  for (const row of GRID.laneRows) {
    const y = row * CELL + CELL / 2;
    for (let x = 8; x < CANVAS_W; x += 24) {
      ctx.beginPath();
      ctx.moveTo(x, y - 4);
      ctx.lineTo(x + 8, y);
      ctx.lineTo(x, y + 4);
      ctx.stroke();
    }
  }
  ctx.restore();
}

function drawOrgan(ctx) {
  ctx.save();
  const row = Math.floor(GRID.rows / 2);
  const x = CANVAS_W - CELL * 0.6;
  const y = row * CELL + CELL / 2;
  ctx.fillStyle = '#c94a6a';
  ctx.beginPath();
  ctx.ellipse(x, y, CELL * 0.7, CANVAS_H * 0.42, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawTowerShape(ctx, cx, cy, radius, shape, color) {
  ctx.save();
  ctx.fillStyle = color;
  ctx.strokeStyle = 'rgba(0,0,0,0.35)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  if (shape === 'spikes') {
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      const x1 = cx + Math.cos(a) * radius;
      const y1 = cy + Math.sin(a) * radius;
      const x2 = cx + Math.cos(a) * (radius + 6);
      const y2 = cy + Math.sin(a) * (radius + 6);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }
  } else if (shape === 'hexring') {
    ctx.beginPath();
    for (let i = 0; i <= 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      const x = cx + Math.cos(a) * (radius + 5);
      const y = cy + Math.sin(a) * (radius + 5);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  } else if (shape === 'zigzag') {
    ctx.beginPath();
    const steps = 8;
    for (let i = 0; i <= steps; i++) {
      const a = (i / steps) * Math.PI * 2;
      const r = radius + (i % 2 === 0 ? 6 : 2);
      const x = cx + Math.cos(a) * r;
      const y = cy + Math.sin(a) * r;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  }
  ctx.restore();
}

function drawTower(ctx, tower) {
  const def = TOWERS[tower.id];
  if (!def) return;
  const { x, y } = cellToPx(tower.col, tower.row);
  drawTowerShape(ctx, x, y, CELL * 0.32, TOWER_SHAPES[tower.id], TOWER_COLORS[tower.id]);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function hpToStrokeWidth(hp) {
  const [min, max] = GENOME_RANGES.hp;
  const t = Math.min(1, Math.max(0, (hp - min) / (max - min)));
  return lerp(1, 6, t); // 2026-08-17: 上限5→6px（硬さの差を見やすく）
}

function sizeToRadius(size) {
  const [min, max] = GENOME_RANGES.size;
  const t = Math.min(1, Math.max(0, (size - min) / (max - min)));
  return lerp(7, 18, t); // 2026-08-17: 8〜17→7〜18px（体格の差を見やすく）
}

function drawResistMarker(ctx, cx, cy, r, resist, fillColor) {
  const shape = RESIST_MARKER_SHAPES[resist];
  if (shape === 'none') return;
  // 塗り色の明度に応じてマーカー線色を白/黒に自動反転
  const markerColor = isLight(fillColor) ? '#222' : '#fff';
  ctx.save();
  ctx.strokeStyle = markerColor;
  ctx.lineWidth = 1.5;
  const m = r * 0.4;
  if (shape === 'triangle') {
    ctx.beginPath();
    ctx.moveTo(cx, cy - m);
    ctx.lineTo(cx - m * 0.86, cy + m * 0.5);
    ctx.lineTo(cx + m * 0.86, cy + m * 0.5);
    ctx.closePath();
    ctx.stroke();
  } else if (shape === 'diamond') {
    ctx.beginPath();
    ctx.moveTo(cx, cy - m);
    ctx.lineTo(cx + m, cy);
    ctx.lineTo(cx, cy + m);
    ctx.lineTo(cx - m, cy);
    ctx.closePath();
    ctx.stroke();
  } else if (shape === 'zigzag') {
    ctx.beginPath();
    ctx.moveTo(cx - m * 0.6, cy - m);
    ctx.lineTo(cx + m * 0.3, cy - m * 0.2);
    ctx.lineTo(cx - m * 0.3, cy + m * 0.2);
    ctx.lineTo(cx + m * 0.6, cy + m);
    ctx.stroke();
  }
  ctx.restore();
}

function isLight(hexColor) {
  const c = hexColor.replace('#', '');
  const r = parseInt(c.substring(0, 2), 16);
  const g = parseInt(c.substring(2, 4), 16);
  const b = parseInt(c.substring(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6;
}

/**
 * genome1体分の図形（速度=縦横比、体力=輪郭太さ、耐性=色+形状記号、体格=半径）を
 * 指定した中心座標に描画する。動きのない静止描画（レポート・プレビュー用）にも
 * ゲーム中のEnemy描画にも使う共通ルーチン。
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} cx
 * @param {number} cy
 * @param {object} genome
 * @param {number} [scale] 半径・線幅のスケール倍率（既定1）
 */
function drawGenomeShape(ctx, cx, cy, genome, scale = 1) {
  const radius = sizeToRadius(genome.size) * scale;
  // speed: 縦横比（速いほど進行方向に細長い）
  const [minSpeed, maxSpeed] = GENOME_RANGES.speed;
  const t = Math.min(1, Math.max(0, (genome.speed - minSpeed) / (maxSpeed - minSpeed)));
  // 2026-08-17 「変化が分からない」→ 縦横比の振れ幅を拡大（遅い=丸〜縦長、速い=矢のように横長）
  const rx = radius * lerp(0.85, 1.9, t);
  const ry = radius * lerp(1.15, 0.6, t);

  const color = RESIST_COLORS[genome.resist];
  ctx.save();
  ctx.fillStyle = color;
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = hpToStrokeWidth(genome.hp) * scale;
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();

  drawResistMarker(ctx, cx, cy, radius, genome.resist, color);
}

function drawEnemy(ctx, enemy, laneRows) {
  if (!enemy.alive || enemy.spawnAt > 0) return;
  const cx = enemy.x * CELL + CELL / 2;
  const cy = laneRows[enemy.lane] * CELL + CELL / 2;
  drawGenomeShape(ctx, cx, cy, enemy.genome);
}

/**
 * genome1体を size×size のCanvasに静止描画する（変異レポートの代表個体・
 * 次ウェーブプレビュー用）。
 * @param {CanvasRenderingContext2D} ctx
 * @param {object} genome
 * @param {number} size
 */
/**
 * 群れのサンプル（最大 cols*rows 体）を size×size のCanvasに格子状に静止描画する。
 * 変異レポートの「前の群れ／次の群れ」用（2026-08-17: 代表1体では変化が伝わりにくかったため）。
 * @param {CanvasRenderingContext2D} ctx
 * @param {Array<object>} genomes
 * @param {number} width
 * @param {number} height
 * @param {number} cols
 * @param {number} rows
 */
export function renderGenomeGroup(ctx, genomes, width, height, cols = 3, rows = 2) {
  ctx.clearRect(0, 0, width, height);
  const cellW = width / cols;
  const cellH = height / rows;
  const scale = (Math.min(cellW, cellH) / CELL) * 0.75;
  genomes.slice(0, cols * rows).forEach((g, i) => {
    const cx = (i % cols) * cellW + cellW / 2;
    const cy = Math.floor(i / cols) * cellH + cellH / 2;
    drawGenomeShape(ctx, cx, cy, g, scale);
  });
}

export function renderGenomeIcon(ctx, genome, size) {
  ctx.clearRect(0, 0, size, size);
  // 0.8の余白係数: size1.5/speed2.0の個体の楕円が40px/96pxのcanvas内に収まるよう縮小する
  const scale = (size / CELL) * 0.8;
  drawGenomeShape(ctx, size / 2, size / 2, genome, scale);
}

function drawLaneOverlay(ctx, row, alpha) {
  ctx.save();
  ctx.fillStyle = `rgba(255,255,255,${alpha})`;
  ctx.fillRect(0, row * CELL, CANVAS_W, CELL);
  ctx.restore();
}

function drawShots(ctx, shots) {
  ctx.save();
  ctx.lineWidth = 1.5;
  for (const shot of shots) {
    ctx.strokeStyle = TOWER_COLORS[shot.towerId] || 'rgba(255,255,255,0.6)';
    ctx.beginPath();
    ctx.moveTo(shot.x1 * CELL, shot.y1 * CELL);
    ctx.lineTo(shot.x2 * CELL, shot.y2 * CELL);
    ctx.stroke();
  }
  ctx.restore();
}

/**
 * 撃破ジュース: 個体の塗り色の粒子群を描画する（CP3）。
 * @param {CanvasRenderingContext2D} ctx
 * @param {Array<{x:number,y:number,color:string,ttl:number,life:number}>} particles
 */
function drawParticles(ctx, particles) {
  if (!particles || !particles.length) return;
  ctx.save();
  for (const p of particles) {
    const alpha = Math.max(0, Math.min(1, p.ttl / p.life));
    if (alpha <= 0) continue;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

/**
 * 撃破報酬の数字ポップを描画する（CP3）。
 * @param {CanvasRenderingContext2D} ctx
 * @param {Array<{x:number,y:number,text:string,ttl:number,life:number}>} goldPopups
 */
function drawGoldPopups(ctx, goldPopups) {
  if (!goldPopups || !goldPopups.length) return;
  ctx.save();
  ctx.font = 'bold 13px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const p of goldPopups) {
    const alpha = Math.max(0, Math.min(1, p.ttl / p.life));
    if (alpha <= 0) continue;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = '#f4d35e';
    ctx.fillText(p.text, p.x, p.y);
  }
  ctx.restore();
}

function drawRangeCircle(ctx, col, row, range) {
  const { x, y } = cellToPx(col, row);
  ctx.save();
  ctx.strokeStyle = 'rgba(255,255,255,0.5)';
  ctx.setLineDash([4, 4]);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(x, y, range * CELL, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

/**
 * 塔パレット用の単体アイコンを size×size のCanvasに描画する。
 * @param {CanvasRenderingContext2D} ctx
 * @param {string} towerId
 * @param {number} size
 */
export function drawTowerIcon(ctx, towerId, size) {
  ctx.clearRect(0, 0, size, size);
  drawTowerShape(ctx, size / 2, size / 2, size * 0.3, TOWER_SHAPES[towerId], TOWER_COLORS[towerId]);
}

/**
 * 盤面を描画する。
 * @param {CanvasRenderingContext2D} ctx
 * @param {{
 *   towers: Array<{id:string,col:number,row:number}>,
 *   enemies: Array<object>,
 *   shots?: Array<object>,
 *   rangePreview?: {col:number,row:number,towerId:string}|null,
 *   laneSelectAlpha?: number|null, // 発熱レーン選択モード中の3レーン点滅alpha
 *   laneFlash?: {lane:number, alpha:number}|null, // 発熱発動レーンの一瞬の白フラッシュ
 *   particles?: Array<object>, // 撃破ジュースの粒子（CP3）
 *   goldPopups?: Array<object>, // 撃破報酬の数字ポップ（CP3）
 * }} view
 */
export function render(ctx, view) {
  ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.save();
  ctx.fillStyle = '#14161c';
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.restore();

  drawGrid(ctx);
  drawLanes(ctx);
  drawOrgan(ctx);

  if (typeof view.laneSelectAlpha === 'number') {
    for (const row of GRID.laneRows) {
      drawLaneOverlay(ctx, row, view.laneSelectAlpha);
    }
  }
  if (view.laneFlash) {
    drawLaneOverlay(ctx, GRID.laneRows[view.laneFlash.lane], view.laneFlash.alpha);
  }

  for (const tower of view.towers || []) {
    drawTower(ctx, tower);
  }

  if (view.shots && view.shots.length) {
    drawShots(ctx, view.shots);
  }

  for (const enemy of view.enemies || []) {
    drawEnemy(ctx, enemy, GRID.laneRows);
  }

  drawParticles(ctx, view.particles);
  drawGoldPopups(ctx, view.goldPopups);

  if (view.rangePreview) {
    const def = TOWERS[view.rangePreview.towerId];
    if (def) drawRangeCircle(ctx, view.rangePreview.col, view.rangePreview.row, def.range);
  }
}
