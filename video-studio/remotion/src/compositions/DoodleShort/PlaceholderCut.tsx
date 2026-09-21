import { AbsoluteFill } from "remotion";
import { paperTextureStyle } from "./paperTexture";

/**
 * まだ画像素材が無いカット用の、紙テクスチャ+テキストのプレースホルダー。
 */
export const PlaceholderCut: React.FC<{ color: string; text?: string }> = ({
  color,
  text,
}) => {
  return (
    <AbsoluteFill
      style={{
        ...paperTextureStyle(color),
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {text ? (
        <p
          style={{
            fontFamily:
              '"Hiragino Maru Gothic ProN", "ヒラギノ丸ゴ ProN W4", "Yu Gothic", sans-serif',
            fontWeight: 700,
            fontSize: 44,
            color: "rgba(0,0,0,0.55)",
            textAlign: "center",
            padding: "0 80px",
            margin: 0,
          }}
        >
          {text}
        </p>
      ) : null}
    </AbsoluteFill>
  );
};
