import { AbsoluteFill } from "remotion";

/**
 * 画面下部に表示する字幕。
 * 丸ゴシック系（Hiragino Maru Gothic ProN）、白文字+黒フチでショート動画でも読める太さにする。
 *
 * 位置は固定の帯（33%等）を確保するのではなく、テキスト量に応じて自然に下端へ張り付く
 * 可変サイズにしている。イラスト日記モードのような「1枚絵+下部字幕」構成では、素材ごとに
 * 被写体（キャラクター）の脚元の高さがまちまち（画面の75〜88%あたりまで様々）なため、
 * 固定の大きな帯を確保すると被写体に字幕がかぶるケースがあった。paddingBottomを絞って
 * テキストを実際の画面下端ギリギリまで下げることで、行数が変わっても被写体との衝突を避けやすくする。
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
      <p
        style={{
          width: "100%",
          boxSizing: "border-box",
          padding: "0 56px 32px",
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
    </AbsoluteFill>
  );
};
