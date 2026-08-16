// config.js
// 設計文書（docs/design/game-td-evolve-design.md）の数値を一元管理する定数群。
// このファイル以外で数値をハードコードしない。

// --- 盤面 ---
export const GRID = {
  cols: 12,
  rows: 8,
  cellSize: 48, // px（論理解像度 576x384）
  laneRows: [1, 4, 7], // 0始まり。行1/4/7が3レーン
};

export const LANE_LENGTH = 12; // 列数と同じ。x>=LANE_LENGTHで到達

// --- ライフ・経済 ---
export const LIVES_START = 20;

export const ECONOMY = {
  initialGoldDefault: 300,
  goldRange: [150, 600], // チャレンジリンクでの上書き範囲
  sellRatio: 0.7,
  waveClearBonus: 40,
};

// 撃破報酬 = 4 + floor(wave * 0.5)
export function killReward(wave) {
  return 4 + Math.floor(wave * 0.5);
}

// --- 塔 ---
// id, 表示名, 属性(none/heat/cold/bolt), 費用, 射程(セル), 攻撃間隔(s), ダメージ, 特殊
export const TOWERS = {
  basic: {
    id: 'basic',
    name: '好中球',
    attr: 'none',
    cost: 50,
    range: 2.0,
    interval: 0.5,
    damage: 6,
    special: null,
  },
  heat: {
    id: 'heat',
    name: 'マクロファージ',
    attr: 'heat',
    cost: 100,
    range: 2.0,
    interval: 1.0,
    damage: 14,
    special: 'splash',
    splashRadius: 0.8, // 着弾点半径0.8セル、対象含む全個体
  },
  cold: {
    id: 'cold',
    name: 'インターフェロン',
    attr: 'cold',
    cost: 100,
    range: 2.5,
    interval: 0.8,
    damage: 8,
    special: 'slow',
    slowDuration: 1.5, // 秒
    slowFactor: 0.6, // 実速度×0.6
  },
  bolt: {
    id: 'bolt',
    name: '抗体',
    attr: 'bolt',
    cost: 120,
    range: 3.5,
    interval: 1.4,
    damage: 30,
    special: null,
  },
};

export const TOWER_ORDER = ['basic', 'heat', 'cold', 'bolt'];

// wave到達で累積解禁。unlockedTowers(wave)が参照する
export const UNLOCK_WAVES = { basic: 1, heat: 3, cold: 5, bolt: 7 };

// --- 色・形状（色覚多様性対応の冗長符号。UX文書§6） ---
// resist index: 0=none 1=heat 2=cold 3=bolt
export const RESIST_COLORS = ['#9a9a9a', '#e05a3a', '#4aa8e0', '#e6c94a'];
export const RESIST_NAMES = ['なし', 'heat', 'cold', 'bolt'];
// 個体中心マーカー形状（輪郭のみ、半径40%）: none=なし、heat=▲、cold=◇、bolt=ジグザグ
export const RESIST_MARKER_SHAPES = ['none', 'triangle', 'diamond', 'zigzag'];

export const TOWER_COLORS = {
  basic: '#e8e8e8',
  heat: '#e05a3a',
  cold: '#4aa8e0',
  bolt: '#e6c94a',
};
// 塔外周の形状差: basic=正円、heat=棘6本、cold=六角枠、bolt=ジグザグ輪郭
export const TOWER_SHAPES = {
  basic: 'circle',
  heat: 'spikes',
  cold: 'hexring',
  bolt: 'zigzag',
};

// --- 敵の遺伝子（genome） ---
// genome: { speed, hp, resist: 0|1|2|3, lane: [w0,w1,w2], size }
export const GENOME_RANGES = {
  speed: [0.6, 2.0], // 基準1.0 = 1.0セル/秒
  hp: [0.6, 3.0], // 倍率。実HP = (20 + wave*8) * hp * size
  size: [0.7, 1.5], // 実速度 = speed / sqrt(size)。表示半径に比例
  resistCount: 4, // 0..3
};

export const GENOME_BASE = { speed: 1.0, hp: 1.0, size: 1.0 };
// 初期集団の±20%ジッター（2026-08-16 CP2知覚テストで±10%・lane均等では
// W1→W2のレポートがseedにより空になったため、初期分散を拡大。閾値は変えない）
export const INITIAL_JITTER = 0.2;
export const INITIAL_LANE_NOISE = 0.15; // 初期集団のlane: 均等(1/3)に±0.15の一様ノイズを加え再正規化

// 実HP = (20 + wave*8) * hp * size
export function hpBaseForWave(wave) {
  return 20 + wave * 8;
}

// 耐性のコスト: resist!==0 の個体は実HP×0.85（対応する塔がなければ耐性は選択で消え、
// 対応する塔があるときだけ残る。選択圧なしでの単一耐性への固着も抑える。2026-08-16 設計判断）
export const RESIST_HP_COST = 0.85;

// --- 個体群 ---
export const POPULATION = {
  initialSize: 22, // startNewGameで使用
  // 秒間隔で順次出現。2026-08-16 CP1スモークのシミュレーションで0.4秒は
  // W1で6塔完全配置でも15体抜けたため0.6秒に調整（設計文書参照）。
  spawnInterval: 0.6,
};

// 次ウェーブの個体数 = min(50, 20 + wave*2)
export function populationSizeForWave(wave) {
  return Math.min(50, 20 + wave * 2);
}

// --- 到達被害 ---
export const REACHED_DAMAGE_LARGE_SIZE_THRESHOLD = 1.2;
export const REACHED_DAMAGE_LARGE = 2;
export const REACHED_DAMAGE_SMALL = 1;

// --- ウェーブ ---
export const WAVE_COUNT = 15;

// --- 進化（CP2で本実装。数値はCP1から凍結） ---
export const EVOLUTION = {
  mutationBaseRate: 0.08, // p = 0.08 * (1 + (1 - towerDiversity))
  parentRatio: 0.3,
  // 2026-08-16 team-lead判断: 4→6（親プールのボトルネックをさらに緩め、
  // CP2理不尽化テスト⑦のresist固着を抑える）
  parentMin: 6,
  mutationSigma: 0.15, // 正規乱数σ
  laneNoise: 0.15,
  // 2026-08-16 team-lead判断: 0.1→0.15（切り上げ）。CP2理不尽化テスト⑦で
  // 選択圧のかからないresistが15世代のボトルネックで固着したため、
  // 毎世代の新鮮個体供給を増やして遺伝的浮動を抑える
  diversityInsuranceRatio: 0.15,
};

// --- diffReportの閾値（CP2で使用） ---
export const DIFF_THRESHOLDS = {
  statPercent: 0.04, // 速度・体力・体格 ±4%未満は出さない
  sharePoint: 0.08, // 割合 ±8pt未満は出さない
  shareMinAfter: 0.15, // 耐性・レーンの「増えた」行は変化後の割合が15%以上のときだけ（小集団ノイズ抑制、2026-08-16）
  softStatPercent: 0.01, // 全項目が閾値未満のとき、これ以上の最大変化を「わずかに〜」1行で見せる
  softSharePoint: 0.03,
};

// --- diffReport文面用の表示名（CP2）。resist 1..3 は対抗する塔の名前を使う ---
export const RESIST_LABELS = { 1: 'マクロファージ', 2: 'インターフェロン', 3: '抗体' };
export const LANE_LABELS = ['上', '中央', '下'];

// --- 能動スキル「発熱」（CP2） ---
export const SKILL = {
  unlockWave: 3, // wave>=3で解禁（塔heatと同時）
  cooldown: 30, // 秒
  duration: 3.0, // 減速持続秒
  slowFactor: 0.5, // 実速度×0.5
  coldResistFactor: 0.75, // cold耐性(resist=2)個体は×0.75
  laneFlashDuration: 0.3, // 発動レーンが白く光る秒数
  laneBlinkPeriod: 0.6, // レーン選択モードの点滅周期（秒）
  laneBlinkAlphaMin: 0.12,
  laneBlinkAlphaMax: 0.25,
  laneBlinkAlphaReducedMotion: 0.18,
};
