import { AbsoluteFill } from "remotion";

/**
 * 画面右下に小さく表示するクレジット表記（例: "VOICEVOX:波音リツ"）。
 * Caption（下部1/3・中央寄せ）とは別レイヤーで、より下の右端に配置して重ならないようにする。
 * placeholder/images が差し替わっても消えないよう、Cut側で独立して描画する。
 */
export const Credit: React.FC<{ text: string }> = ({ text }) => {
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "flex-end",
        pointerEvents: "none",
      }}
    >
      <p
        style={{
          margin: 0,
          padding: "0 20px 18px 0",
          fontFamily:
            '"Hiragino Maru Gothic ProN", "ヒラギノ丸ゴ ProN W4", "Yu Gothic", sans-serif',
          fontWeight: 700,
          fontSize: 26,
          lineHeight: 1.2,
          color: "#ffffff",
          textAlign: "right",
          WebkitTextStroke: "5px #000000",
          paintOrder: "stroke fill",
        }}
      >
        {text}
      </p>
    </AbsoluteFill>
  );
};
