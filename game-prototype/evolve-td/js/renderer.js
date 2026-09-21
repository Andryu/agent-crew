// renderer.js
// Canvas描画（盤面・塔・個体の見た目直結・弾軌跡）。論理解像度576x384。
// DOM(Canvas 2D Context)に依存するため test.mjs では構文チェックのみ行う。

import {
  GRID,
  UPGRADE,
  LIVES_START,
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

// 配置面は格子線よりソケットを主役にし、流路との違いを形でも示す。
function drawGrid(ctx, planning, maze) {
  const blocked = new Set((maze?.rocks || []).map(cell => `${cell.col},${cell.row}`));
  ctx.save();
  ctx.strokeStyle = 'rgba(118,166,190,0.065)';
  ctx.lineWidth = 1;
  for (let col = 0; col < GRID.cols; col++) {
    for (let row = 0; row < GRID.rows; row++) {
      const { x, y } = cellToPx(col, row);
      ctx.strokeRect(col * CELL + 0.5, row * CELL + 0.5, CELL, CELL);
      if (maze ? col === 0 || col === GRID.cols - 1 || blocked.has(`${col},${row}`) : GRID.laneRows.includes(row)) continue;
      ctx.beginPath();
      ctx.arc(x, y, 15, 0, Math.PI * 2);
      ctx.fillStyle = '#0c1720';
      ctx.fill();
      ctx.strokeStyle = planning ? 'rgba(164,244,206,0.25)' : 'rgba(118,166,190,0.17)';
      ctx.stroke();
      ctx.fillStyle = 'rgba(143,183,198,0.3)';
      ctx.fillRect(x - 2, y - 0.5, 4, 1);
      ctx.fillRect(x - 0.5, y - 2, 1, 4);
      ctx.strokeStyle = 'rgba(118,166,190,0.065)';
    }
  }
  ctx.restore();
}

function drawLanes(ctx) {
  ctx.save();
  for (const [index, row] of GRID.laneRows.entries()) {
    const y = row * CELL + CELL / 2;
    const flow = ctx.createLinearGradient(0, y - 24, 0, y + 24);
    flow.addColorStop(0, '#102531');
    flow.addColorStop(0.5, '#112e39');
    flow.addColorStop(1, '#0c1e29');
    ctx.fillStyle = flow;
    ctx.fillRect(0, y - 23, CANVAS_W, 46);
    ctx.strokeStyle = 'rgba(108,212,222,0.24)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, y - 22.5); ctx.lineTo(CANVAS_W, y - 22.5);
    ctx.moveTo(0, y + 22.5); ctx.lineTo(CANVAS_W, y + 22.5);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(133,225,229,0.16)';
    ctx.setLineDash([2, 10]);
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
    ctx.setLineDash([]);
    for (let x = 42; x < CANVAS_W - 20; x += CELL * 2) {
      ctx.beginPath();
      ctx.moveTo(x - 3, y - 4); ctx.lineTo(x + 2, y); ctx.lineTo(x - 3, y + 4);
      ctx.stroke();
    }
    ctx.fillStyle = '#89bfc9';
    ctx.font = '8px monospace';
    ctx.fillText(`0${index + 1}`, 7, y - 11);
    ctx.fillStyle = '#a4f4ce';
    ctx.fillRect(0, y - 11, 2, 22);
  }
  ctx.restore();
}

// 経路探索は状態更新側で済ませ、描画では受け取った折れ線だけを使う。
const ROUTE_COLORS = ['#67dac4', '#78aeef', '#eeb67f'];

function traceRoute(ctx, path, offset = 0) {
  ctx.beginPath();
  path.forEach((cell, index) => {
    const { x, y } = cellToPx(cell.col, cell.row);
    if (index === 0) ctx.moveTo(x + offset, y + offset);
    else ctx.lineTo(x + offset, y + offset);
  });
}

function drawMazePaths(ctx, paths, preview = false, valid = true) {
  ctx.save();
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  (paths || []).forEach((path, index) => {
    if (!path?.length) return;
    const color = preview ? (valid ? '#b6ffbf' : '#ff8c87') : ROUTE_COLORS[index % ROUTE_COLORS.length];
    // 重なった経路でも各入口の色が読めるよう細線を少しずらす。
    const offset = (index - 1) * 3;
    ctx.strokeStyle = color;
    ctx.globalAlpha = preview ? 0.9 : 0.09;
    ctx.lineWidth = preview ? 2 : 22;
    ctx.setLineDash(preview ? [5, 5] : []);
    traceRoute(ctx, path, preview ? offset : 0);
    ctx.stroke();
    if (preview) return;
    ctx.globalAlpha = 0.48;
    ctx.lineWidth = 1.2;
    traceRoute(ctx, path, offset);
    ctx.stroke();
    for (let i = 1; i < path.length; i += 2) {
      const a = cellToPx(path[i - 1].col, path[i - 1].row);
      const b = cellToPx(path[i].col, path[i].row);
      const angle = Math.atan2(b.y - a.y, b.x - a.x);
      const x = (a.x + b.x) / 2 + offset;
      const y = (a.y + b.y) / 2 + offset;
      ctx.beginPath();
      ctx.moveTo(x - Math.cos(angle - 0.6) * 5, y - Math.sin(angle - 0.6) * 5);
      ctx.lineTo(x, y);
      ctx.lineTo(x - Math.cos(angle + 0.6) * 5, y - Math.sin(angle + 0.6) * 5);
      ctx.stroke();
    }
  });
  ctx.restore();
}

function drawMaze(ctx, maze, lives = LIVES_START) {
  drawMazePaths(ctx, maze.paths);
  ctx.save();
  for (const rock of maze.rocks || []) {
    const { x, y } = cellToPx(rock.col, rock.row);
    const stone = ctx.createLinearGradient(x - 20, y - 20, x + 20, y + 20);
    stone.addColorStop(0, '#28343b');
    stone.addColorStop(1, '#111d24');
    ctx.fillStyle = stone;
    ctx.fillRect(x - 22, y - 22, 44, 44);
    ctx.strokeStyle = '#3a4b52';
    ctx.lineWidth = 1;
    ctx.strokeRect(x - 21.5, y - 21.5, 43, 43);
    ctx.save();
    ctx.beginPath(); ctx.rect(x - 20, y - 20, 40, 40); ctx.clip();
    ctx.strokeStyle = 'rgba(141,163,173,0.13)';
    for (let d = -40; d <= 40; d += 9) {
      ctx.beginPath(); ctx.moveTo(x + d - 20, y + 20); ctx.lineTo(x + d + 20, y - 20); ctx.stroke();
    }
    ctx.restore();
    ctx.fillStyle = '#607079'; ctx.fillRect(x - 3, y - 3, 6, 6);
  }
  // 合流が始まるセルだけを輪で示す（共有区間全部には描かない）。
  const incoming = new Map();
  for (const path of maze.paths || []) {
    (path || []).forEach((cell, i) => {
      if (!i) return;
      const key = `${cell.col},${cell.row}`;
      if (!incoming.has(key)) incoming.set(key, { cell, sources: new Set() });
      incoming.get(key).sources.add(`${path[i - 1].col},${path[i - 1].row}`);
    });
  }
  ctx.strokeStyle = 'rgba(192,236,219,0.55)';
  for (const { cell, sources } of incoming.values()) {
    if (sources.size < 2) continue;
    const { x, y } = cellToPx(cell.col, cell.row);
    ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.stroke();
  }
  [1, 4, 7].forEach((row, index) => {
    const { x, y } = cellToPx(0, row);
    ctx.fillStyle = '#0c1c23'; ctx.fillRect(2, y - 20, 38, 40);
    ctx.fillStyle = ROUTE_COLORS[index]; ctx.fillRect(0, y - 15, 3, 30);
    ctx.font = 'bold 10px monospace'; ctx.fillText(`0${index + 1}`, 8, y - 5);
    ctx.strokeStyle = ROUTE_COLORS[index];
    ctx.beginPath(); ctx.moveTo(x - 4, y + 3); ctx.lineTo(x + 2, y + 8); ctx.lineTo(x - 4, y + 13); ctx.stroke();
  });
  const { x, y } = cellToPx(11, 4);
  const health = Math.max(0, Math.min(1, lives / LIVES_START));
  const color = health > 0.3 ? '#a4f4ce' : '#f29889';
  ctx.fillStyle = '#102a2c'; ctx.strokeStyle = color;
  ctx.beginPath(); ctx.arc(x, y, 17, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.shadowColor = color; ctx.shadowBlur = 10; ctx.fillStyle = color;
  ctx.beginPath(); ctx.moveTo(x, y - 10); ctx.lineTo(x + 7, y); ctx.lineTo(x, y + 10); ctx.lineTo(x - 7, y); ctx.closePath(); ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = '#263c41'; ctx.fillRect(x - 18, y + 22, 36, 4);
  ctx.fillStyle = color; ctx.fillRect(x - 18, y + 22, 36 * health, 4);
  ctx.font = '8px monospace'; ctx.textAlign = 'center'; ctx.fillText('CORE', x, y - 23);
  ctx.restore();
}

function drawOrgan(ctx, lives = LIVES_START) {
  ctx.save();
  // 装置は右端14pxに収め、最後列の配置中心を覆わない。
  const x = CANVAS_W - 13;
  const health = Math.max(0, Math.min(1, lives / LIVES_START));
  const color = health > 0.3 ? '#a4f4ce' : '#f29889';
  ctx.fillStyle = '#060d13';
  ctx.fillRect(x, 0, 13, CANVAS_H);
  ctx.strokeStyle = '#28434d';
  ctx.strokeRect(x + 0.5, 7.5, 12, CANVAS_H - 15);
  ctx.fillStyle = '#16312e';
  ctx.fillRect(x + 5, 17, 3, CANVAS_H - 34);
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 7;
  const h = (CANVAS_H - 34) * health;
  ctx.fillRect(x + 5, CANVAS_H - 17 - h, 3, h);
  ctx.shadowBlur = 0;
  for (const row of GRID.laneRows) {
    const y = row * CELL + CELL / 2;
    ctx.fillStyle = '#10232b'; ctx.fillRect(x, y - 9, 13, 18);
    ctx.strokeStyle = color; ctx.strokeRect(x + 3, y - 5, 6, 10);
  }
  ctx.restore();
}

function drawCellFocus(ctx, cell, selected = false, maze) {
  if (!cell || (!maze && GRID.laneRows.includes(cell.row))) return;
  const { x, y } = cellToPx(cell.col, cell.row);
  ctx.save();
  ctx.fillStyle = selected ? 'rgba(164,244,206,0.10)' : 'rgba(164,244,206,0.05)';
  ctx.fillRect(x - 23, y - 23, 46, 46);
  ctx.strokeStyle = !selected && maze?.previewValid === false ? '#f29889' : selected ? '#a4f4ce' : 'rgba(164,244,206,0.5)';
  ctx.lineWidth = selected ? 1.5 : 1;
  for (const dx of [-1, 1]) {
    for (const dy of [-1, 1]) {
      ctx.beginPath();
      ctx.moveTo(x + dx * 14, y + dy * 21);
      ctx.lineTo(x + dx * 21, y + dy * 21);
      ctx.lineTo(x + dx * 21, y + dy * 14);
      ctx.stroke();
    }
  }
  ctx.restore();
}

function drawTowerShape(ctx, cx, cy, radius, shape, color) {
  ctx.save();
  const body = ctx.createRadialGradient(cx - radius * 0.35, cy - radius * 0.45, 1, cx, cy, radius);
  body.addColorStop(0, '#f1fff7');
  body.addColorStop(0.3, color);
  body.addColorStop(1, '#233c45');
  ctx.fillStyle = body;
  ctx.shadowColor = color;
  ctx.shadowBlur = 9;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.shadowBlur = 0;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
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
  // 中央記号も属性ごとに変え、色と外周形状の二重符号を補う。
  ctx.strokeStyle = '#07131a';
  ctx.lineWidth = Math.max(1.5, radius * 0.13);
  const g = radius * 0.36;
  ctx.beginPath();
  if (shape === 'zigzag') {
    ctx.moveTo(cx + g * 0.4, cy - g); ctx.lineTo(cx - g * 0.5, cy);
    ctx.lineTo(cx + g * 0.5, cy); ctx.lineTo(cx - g * 0.4, cy + g);
  } else if (shape === 'hexring') {
    ctx.moveTo(cx, cy - g); ctx.lineTo(cx + g, cy); ctx.lineTo(cx, cy + g);
    ctx.lineTo(cx - g, cy); ctx.closePath();
  } else if (shape === 'spikes') {
    ctx.moveTo(cx, cy - g); ctx.lineTo(cx + g, cy + g * 0.7);
    ctx.lineTo(cx - g, cy + g * 0.7); ctx.closePath();
  } else {
    ctx.moveTo(cx - g, cy); ctx.lineTo(cx + g, cy);
    ctx.moveTo(cx, cy - g); ctx.lineTo(cx, cy + g);
  }
  ctx.stroke();

  ctx.restore();
}

// CP5: 塔アップグレード。中心図形をlevel数だけ同心に描く（Lv1=1重／Lv2=2重／Lv3=3重）。
// 外周形状（棘・六角枠・ジグザグ）はlevelに関わらず既存のまま変えない。
function drawTowerLevelRings(ctx, cx, cy, radius, level) {
  if (level <= 1) return;
  ctx.save();
  ctx.strokeStyle = 'rgba(255,255,255,0.6)';
  ctx.lineWidth = 1.2;
  for (let i = 1; i < level; i++) {
    const r = radius * (0.35 + 0.3 * i);
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

function drawTower(ctx, tower) {
  const def = TOWERS[tower.id];
  if (!def) return;
  const { x, y } = cellToPx(tower.col, tower.row);
  const radius = CELL * 0.32;
  drawTowerShape(ctx, x, y, radius, TOWER_SHAPES[tower.id], TOWER_COLORS[tower.id]);
  drawTowerLevelRings(ctx, x, y, radius, tower.level || 1);
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
  const membrane = ctx.createRadialGradient(cx - rx * 0.25, cy - ry * 0.3, 0, cx, cy, Math.max(rx, ry));
  membrane.addColorStop(0, '#e9e9da');
  membrane.addColorStop(0.3, color);
  membrane.addColorStop(1, '#263342');
  ctx.fillStyle = membrane;
  ctx.shadowColor = color;
  ctx.shadowBlur = 6 * scale;
  ctx.strokeStyle = color;
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
  const cx = enemy.x * CELL;
  const cy = Number.isFinite(enemy.y) ? enemy.y * CELL : laneRows[enemy.lane] * CELL + CELL / 2;
  drawGenomeShape(ctx, cx, cy, enemy.genome);
  const maxHp = enemy.maxHp ?? enemy.genome.hp;
  const hp = Number.isFinite(enemy.hp) && maxHp > 0 ? Math.max(0, Math.min(1, enemy.hp / maxHp)) : 1;
  const width = 24;
  const top = Math.max(2, cy - sizeToRadius(enemy.genome.size) - 10);
  ctx.save();
  ctx.fillStyle = '#071016'; ctx.fillRect(cx - width / 2 - 1, top - 1, width + 2, 5);
  ctx.fillStyle = '#38434b'; ctx.fillRect(cx - width / 2, top, width, 3);
  ctx.fillStyle = hp > 0.5 ? '#a4f4ce' : hp > 0.25 ? '#edc786' : '#f29889';
  ctx.fillRect(cx - width / 2, top, width * hp, 3);
  ctx.restore();
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
    ctx.strokeStyle = TOWER_COLORS[shot.towerId] || '#d5fff1';
    ctx.shadowColor = ctx.strokeStyle;
    ctx.shadowBlur = 8;
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
  ctx.fillStyle = 'rgba(164,244,206,0.035)';
  ctx.strokeStyle = 'rgba(164,244,206,0.5)';
  ctx.setLineDash([4, 4]);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(x, y, range * CELL, 0, Math.PI * 2);
  ctx.fill();
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
 *   selectedCell?: {col:number,row:number}|null,
 *   hoverCell?: {col:number,row:number}|null,
 *   planning?: boolean,
 *   maze?: {paths:Array<Array<{col:number,row:number}>>,rocks:Array<{col:number,row:number}>,previewPaths:Array<Array<{col:number,row:number}>>|null,previewValid:boolean|null},
 *   lives?: number,
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
  ctx.fillStyle = '#080f16';
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.restore();

  drawGrid(ctx, view.planning, view.maze);
  if (view.maze) drawMaze(ctx, view.maze, view.lives);
  else {
    drawLanes(ctx);
    drawOrgan(ctx, view.lives);
  }
  drawCellFocus(ctx, view.hoverCell, false, view.maze);
  drawCellFocus(ctx, view.selectedCell, true, view.maze);
  if (view.selectedCell) {
    const selected = (view.towers || []).find(tower => tower.col === view.selectedCell.col && tower.row === view.selectedCell.row);
    if (selected && TOWERS[selected.id]) {
      const range = TOWERS[selected.id].range + UPGRADE.rangeAdd * ((selected.level || 1) - 1);
      drawRangeCircle(ctx, selected.col, selected.row, range);
    }
  }

  if (!view.maze && typeof view.laneSelectAlpha === 'number') {
    for (const row of GRID.laneRows) {
      drawLaneOverlay(ctx, row, view.laneSelectAlpha);
    }
  }
  if (!view.maze && view.laneFlash) {
    drawLaneOverlay(ctx, GRID.laneRows[view.laneFlash.lane], view.laneFlash.alpha);
  }

  if (view.maze?.previewPaths) {
    drawMazePaths(ctx, view.maze.previewPaths, true, view.maze.previewValid !== false);
  } else if (view.maze?.previewValid === false) {
    drawMazePaths(ctx, view.maze.paths, true, false);
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
    if (def) drawRangeCircle(ctx, view.rangePreview.col, view.rangePreview.row, def.range + UPGRADE.rangeAdd * ((view.rangePreview.level || 1) - 1));
  }
}
