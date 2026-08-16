// rng.js
// シード付き擬似乱数生成（mulberry32）。同じseedなら同じ乱数列を返す。
// DOM非依存の純粋関数のみ。

/**
 * @param {number} seed uint32として扱われるシード値
 * @returns {(() => number) & { int: (n:number)=>number, pick: (arr:any[])=>any, normal: (mean?:number, sd?:number)=>number }}
 */
export function makeRng(seed) {
  let a = seed >>> 0;

  function rng() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  rng.int = function int(n) {
    return Math.floor(rng() * n);
  };

  rng.pick = function pick(arr) {
    return arr[rng.int(arr.length)];
  };

  // Box-Muller法による正規乱数
  rng.normal = function normal(mean = 0, sd = 1) {
    let u = 0;
    let v = 0;
    while (u === 0) u = rng();
    while (v === 0) v = rng();
    const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    return mean + z * sd;
  };

  return rng;
}
