import { AbsoluteFill, Audio, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { EpisodeCut } from "./types";
import { Caption } from "./Caption";
import { Credit } from "./Credit";
import { PlaceholderCut } from "./PlaceholderCut";
import { getCameraTransform } from "./cameraEffect";

const DEFAULT_TOGGLE_FPS = 6;

export const Cut: React.FC<{
  cut: EpisodeCut;
  episodeId: string;
  durationInFrames: number;
}> = ({ cut, episodeId, durationInFrames }) => {
  // Sequence配下なので frame はこのカット先頭を0とするローカル時間
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const images = cut.images ?? [];
  const toggleFps = cut.toggleFps ?? DEFAULT_TOGGLE_FPS;

  let currentImage: string | undefined;
  if (images.length === 1) {
    currentImage = images[0];
  } else if (images.length >= 2) {
    // 滑らかな補間はせず、一定フレーム数ごとにパッと切り替える（目パチ・口パク風）
    const framesPerImage = Math.max(1, Math.round(fps / toggleFps));
    const index = Math.floor(frame / framesPerImage) % images.length;
    currentImage = images[index];
  }

  const cameraTransform = getCameraTransform(cut.camera, frame, durationInFrames);

  return (
    <AbsoluteFill style={{ backgroundColor: "#ffffff", overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          transform: cameraTransform,
          transformOrigin: "center center",
        }}
      >
        {currentImage ? (
          <Img
            src={staticFile(`${episodeId}/${currentImage}`)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        ) : cut.placeholder ? (
          <PlaceholderCut color={cut.placeholder.color} text={cut.placeholder.text} />
        ) : (
          <PlaceholderCut color="#eeeeee" />
        )}
      </AbsoluteFill>

      {cut.caption ? <Caption text={cut.caption} /> : null}
      {cut.credit ? <Credit text={cut.credit} /> : null}

      {cut.narration ? (
        <Audio src={staticFile(`${episodeId}/${cut.narration}`)} volume={1} />
      ) : null}
      {cut.se ? <Audio src={staticFile(`${episodeId}/${cut.se}`)} /> : null}
    </AbsoluteFill>
  );
};
