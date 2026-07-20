import { AbsoluteFill } from "remotion";

/**
 * 画面下部1/3に表示する字幕。
 * 丸ゴシック系（Hiragino Maru Gothic ProN）、白文字+黒フチでショート動画でも読める太さにする。
 */
export const Caption: React.FC<{ text: string }> = ({ text }) => {
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          width: "100%",
          minHeight: "33%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "0 56px 100px",
          boxSizing: "border-box",
        }}
      >
        <p
          style={{
            fontFamily:
              '"Hiragino Maru Gothic ProN", "ヒラギノ丸ゴ ProN W4", "Yu Gothic", sans-serif',
            fontWeight: 900,
            fontSize: 62,
            lineHeight: 1.4,
            color: "#ffffff",
            textAlign: "center",
            WebkitTextStroke: "11px #000000",
            paintOrder: "stroke fill",
            margin: 0,
            whiteSpace: "pre-wrap",
          }}
        >
          {text}
        </p>
      </div>
    </AbsoluteFill>
  );
};
