import "./index.css";
import { Composition } from "remotion";
import { DoodleShort, calculateDoodleShortMetadata } from "./compositions/DoodleShort/DoodleShort";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="doodle-short"
        component={DoodleShort}
        calculateMetadata={calculateDoodleShortMetadata}
        // 初期値。実際の値は episode.json を読んだ calculateMetadata が上書きする。
        fps={30}
        width={1080}
        height={1920}
        durationInFrames={30}
        defaultProps={{ episodeId: "ep01" }}
      />
    </>
  );
};
