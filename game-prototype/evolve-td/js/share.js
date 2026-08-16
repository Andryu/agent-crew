// share.js
// チャレンジリンクの符号化・復号（純粋関数・DOM非依存）。
// main.jsが `location.hash = "#c=" + encodeChallenge({seed, gold})` の形で使う。

import { ECONOMY } from './config.js';

const VERSION = 1;
const SEED_MAX = 0xffffffff; // uint32

function toBase64Url(str) {
  const b64 = typeof btoa === 'function' ? btoa(str) : Buffer.from(str, 'binary').toString('base64');
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64Url(str) {
  const b64 = str.replace(/-/g, '+').replace(/_/g, '/');
  const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
  return typeof atob === 'function' ? atob(padded) : Buffer.from(padded, 'base64').toString('binary');
}

/**
 * {seed, gold} をbase64urlに符号化する。"#c=" を除いた部分の文字列を返す。
 * 呼び出し側で `"#c=" + encodeChallenge(...)` として location.hash に設定する。
 * @param {{seed:number, gold:number}} payload
 * @returns {string}
 */
export function encodeChallenge({ seed, gold }) {
  const json = JSON.stringify({ v: VERSION, seed, gold });
  return toBase64Url(json);
}

/**
 * "#c=..." で始まる文字列、または"#c="を除いたペイロード部分のどちらを渡してもよい。
 * v!==1、seedが非整数・範囲外(0〜uint32最大)、goldがECONOMY.goldRange範囲外、
 * base64/JSONとしてパースできない場合はnullを返す。
 * @param {string} hashOrPayload
 * @returns {{seed:number, gold:number}|null}
 */
export function decodeChallenge(hashOrPayload) {
  if (typeof hashOrPayload !== 'string' || hashOrPayload.length === 0) return null;
  const match = hashOrPayload.match(/c=(.+)$/);
  const payload = match ? match[1] : hashOrPayload;
  if (!payload) return null;

  let json;
  try {
    json = fromBase64Url(payload);
  } catch {
    return null;
  }

  let obj;
  try {
    obj = JSON.parse(json);
  } catch {
    return null;
  }
  if (!obj || typeof obj !== 'object') return null;
  if (obj.v !== VERSION) return null;
  if (!Number.isInteger(obj.seed) || obj.seed < 0 || obj.seed > SEED_MAX) return null;

  const [min, max] = ECONOMY.goldRange;
  if (!Number.isInteger(obj.gold) || obj.gold < min || obj.gold > max) return null;

  return { seed: obj.seed, gold: obj.gold };
}
