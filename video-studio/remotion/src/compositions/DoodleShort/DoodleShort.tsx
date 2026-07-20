import {
  AbsoluteFill,
  Audio,
  CalculateMetadataFunction,
  Sequence,
  staticFile,
} from "remotion";
import type { DoodleShortProps } from "./types";
import { Cut } from "./Cut";
import { cutDurationInFrames, loadEpisode } from "./loadEpisode";

const DEFAULT_FPS = 30;
const DEFAULT_WIDTH = 1080;
const DEFAULT_HEIGHT = 1920;
const DEFAULT_BGM_VOLUME = 0.4;

/**
 * episode.json を読み込み、cuts の合計尺から動画の長さ・fps・解像度を決定する。
 * Remotionは calculateMetadata の非同期処理を待ってからバンドル/レンダリングする。
 */
export const calculateDoodleShortMetadata: CalculateMetadataFunction<
  DoodleShortProps
> = async ({ props }) => {
  const episode = await loadEpisode(props.episodeId);
  const fps = episode.fps ?? DEFAULT_FPS;
  const width = episode.width ?? DEFAULT_WIDTH;
  const height = episode.height ?? DEFAULT_HEIGHT;

  const durationInFrames = episode.cuts.reduce(
    (sum, cut) => sum + cutDurationInFrames(cut.durationSec, fps),
    0,
  );

  return {
    durationInFrames: Math.max(durationInFrames, 1),
    fps,
    width,
    height,
    props: { ...props, episode },
  };
};

export const DoodleShort: React.FC<DoodleShortProps> = ({ episode }) => {
  if (!episode) {
    return null;
  }

  const fps = episode.fps ?? DEFAULT_FPS;
  let cursor = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#ffffff" }}>
      {episode.audio?.bgm ? (
        <Audio
          src={staticFile(`${episode.id}/${episode.audio.bgm}`)}
          volume={episode.audio.bgmVolume ?? DEFAULT_BGM_VOLUME}
        />
      ) : null}

      {episode.cuts.map((cut) => {
        const durationInFrames = cutDurationInFrames(cut.durationSec, fps);
        const from = cursor;
        cursor += durationInFrames;

        return (
          <Sequence key={cut.index} from={from} durationInFrames={durationInFrames}>
            <Cut cut={cut} episodeId={episode.id} durationInFrames={durationInFrames} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
