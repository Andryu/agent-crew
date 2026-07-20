import {
  AbsoluteFill,
  Audio,
  Img,
  Loop,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { EpisodeCut } from "./types";
import { Caption } from "./Caption";
import { Credit } from "./Credit";
import { DialogueCaptions } from "./DialogueCaption";
import { PlaceholderCut } from "./PlaceholderCut";
import { getCameraTransform } from "./cameraEffect";
import { getIdleSwayTransform } from "./idleSway";
import { paperTextureStyle } from "./paperTexture";

const DEFAULT_TOGGLE_FPS = 6;
const DEFAULT_MOUTH_TOGGLE_FPS = 8;
const VIDEO_EXTENSION_RE = /\.(mp4|webm)$/i;

const isVideoSrc = (src: string): boolean => VIDEO_EXTENSION_RE.test(src);

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
  const dialogue = cut.dialogue ?? [];

  // 再生中のセリフのうち mouthLayer を持つものを探す（口パク対象）
  const activeMouthDialogue = dialogue.find((line) => {
    if (!line.mouthLayer) return false;
    const startFrame = Math.round(line.startSec * fps);
    const endFrame = startFrame + Math.round(line.durationSec * fps);
    return frame >= startFrame && frame < endFrame;
  });

  let currentImage: string | undefined;
  if (activeMouthDialogue?.mouthLayer) {
    // 口パク優先: そのセリフの再生中だけ口閉じ/口開きをステップ切り替え（補間なし）
    const { mouthClosed, mouthOpen, toggleFps: mouthToggleFps } = activeMouthDialogue.mouthLayer;
    const mfps = mouthToggleFps ?? DEFAULT_MOUTH_TOGGLE_FPS;
    const framesPerMouth = Math.max(1, Math.round(fps / mfps));
    const localFrame = frame - Math.round(activeMouthDialogue.startSec * fps);
    const isOpen = Math.floor(localFrame / framesPerMouth) % 2 === 1;
    currentImage = isOpen ? mouthOpen : mouthClosed;
  } else if (images.length === 1) {
    currentImage = images[0];
  } else if (images.length >= 2) {
    // 滑らかな補間はせず、一定フレーム数ごとにパッと切り替える（目パチ・口パク風）
    const framesPerImage = Math.max(1, Math.round(fps / toggleFps));
    const index = Math.floor(frame / framesPerImage) % images.length;
    currentImage = images[index];
  }

  const cameraTransform = getCameraTransform(cut.camera, frame, durationInFrames);
  const swayTransform = getIdleSwayTransform(frame, fps, cut.index);
  const currentIsVideo = currentImage ? isVideoSrc(currentImage) : false;

  // 再生ウィンドウ中で text を持つセリフを全て集める（cut3のような重ね再生も複数行スタック表示できる）
  const activeDialogueCaptions = dialogue
    .filter((line) => {
      if (!line.text) return false;
      const startFrame = Math.round(line.startSec * fps);
      const endFrame = startFrame + Math.round(line.durationSec * fps);
      return frame >= startFrame && frame < endFrame;
    })
    .map((line) => ({ text: line.text as string, speaker: line.speaker }));

  // 背景と前景で位相をずらし、機械的に同調して見えないようにする
  const backgroundSwayTransform = getIdleSwayTransform(frame, fps, cut.index + 100);

  return (
    <AbsoluteFill style={{ ...paperTextureStyle("#ffffff"), overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          transform: cameraTransform,
          transformOrigin: "center center",
        }}
      >
        {cut.background ? (
          <AbsoluteFill
            style={{
              transform: backgroundSwayTransform,
              transformOrigin: "center center",
            }}
          >
            <Img
              src={staticFile(`${episodeId}/${cut.background}`)}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </AbsoluteFill>
        ) : null}

        {/* 常時ゆらゆら：手書き風の揺れ（上下±%＋微小回転）をカメラ演出とは独立に重ねがけ */}
        <AbsoluteFill
          style={{
            transform: swayTransform,
            transformOrigin: "center center",
            // 背景がある場合、前景は白背景同士がmultiplyで馴染む（白は透過的に振る舞い、線画だけ残る）
            mixBlendMode: cut.background ? "multiply" : "normal",
          }}
        >
          {currentImage ? (
            currentIsVideo ? (
              cut.videoLoopSec ? (
                <Loop durationInFrames={Math.max(1, Math.round(cut.videoLoopSec * fps))}>
                  <OffthreadVideo
                    src={staticFile(`${episodeId}/${currentImage}`)}
                    muted
                    // 動画はcoverだとモーションクリップ内の動きで画面外に見切れることがあるため
                    // containにして全身が常に収まるようにする（上下左右の余白は白背景と馴染む前提）
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                  />
                </Loop>
              ) : (
                <OffthreadVideo
                  src={staticFile(`${episodeId}/${currentImage}`)}
                  muted
                  style={{ width: "100%", height: "100%", objectFit: "contain" }}
                />
              )
            ) : (
              <Img
                src={staticFile(`${episodeId}/${currentImage}`)}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                }}
              />
            )
          ) : cut.placeholder ? (
            <PlaceholderCut color={cut.placeholder.color} text={cut.placeholder.text} />
          ) : (
            <PlaceholderCut color="#eeeeee" />
          )}
        </AbsoluteFill>
      </AbsoluteFill>

      {cut.caption ? <Caption text={cut.caption} /> : null}
      <DialogueCaptions lines={activeDialogueCaptions} />
      {cut.credit ? <Credit text={cut.credit} /> : null}

      {/* 後方互換: 単一ナレーション */}
      {cut.narration ? (
        <Audio src={staticFile(`${episodeId}/${cut.narration}`)} volume={1} />
      ) : null}

      {/* v2: 複数話者のセリフをstartSecでシーケンス配置 */}
      {dialogue.map((line, i) => {
        const from = Math.max(0, Math.round(line.startSec * fps));
        const lineDurationInFrames = Math.max(1, Math.round(line.durationSec * fps));
        return (
          <Sequence key={i} from={from} durationInFrames={lineDurationInFrames}>
            <Audio src={staticFile(`${episodeId}/${line.wav}`)} volume={1} />
          </Sequence>
        );
      })}

      {cut.se ? <Audio src={staticFile(`${episodeId}/${cut.se}`)} /> : null}
    </AbsoluteFill>
  );
};
