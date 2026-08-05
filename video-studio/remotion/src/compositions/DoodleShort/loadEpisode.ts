import { staticFile } from "remotion";
import type { Episode } from "./types";

/**
 * public dir (= video-studio/episodes) を通して episode.json を取得する。
 * remotion.config.ts で Config.setPublicDir が episodes ディレクトリを指しているため、
 * staticFile(`${episodeId}/episode.json`) で video-studio/episodes/<episodeId>/episode.json を指せる。
 */
export const loadEpisode = async (episodeId: string): Promise<Episode> => {
  const url = staticFile(`${episodeId}/episode.json`);
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(
      `episode.json の読み込みに失敗しました: ${url} (status: ${res.status})。` +
        `video-studio/episodes/${episodeId}/episode.json が存在するか確認してください。`,
    );
  }
  const episode = (await res.json()) as Episode;
  if (!episode.cuts || episode.cuts.length === 0) {
    throw new Error(`episode.json に cuts がありません: ${url}`);
  }
  return episode;
};

/** カットの尺(フレーム数)を計算する */
export const cutDurationInFrames = (durationSec: number, fps: number): number =>
  Math.max(1, Math.round(durationSec * fps));
