import { AbsoluteFill } from "remotion";
import type { Speaker } from "./types";

// 話者ごとの識別色。白文字+この色の縁取り＋同色のドットで見分ける（吹き出しは使わずシンプルに）。
const SPEAKER_COLOR: Record<Speaker, string> = {
  kanojo: "#E6478B",
  kareshi: "#2E7FE0",
  mob: "#4C9A63",
};

const DialogueBubble: React.FC<{ text: string; speaker: Speaker }> = ({ text, speaker }) => {
  const color = SPEAKER_COLOR[speaker];
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 12,
        background: "rgba(0,0,0,0.32)",
        borderRadius: 999,
        padding: "8px 28px",
        border: `3px solid ${color}`,
        maxWidth: "88%",
      }}
    >
      <span
        style={{
          width: 12,
          height: 12,
          borderRadius: "50%",
          backgroundColor: color,
          flexShrink: 0,
        }}
      />
      <p
        style={{
          margin: 0,
          fontFamily:
            '"Hiragino Maru Gothic ProN", "ヒラギノ丸ゴ ProN W4", "Yu Gothic", sans-serif',
          fontWeight: 800,
          fontSize: 42,
          lineHeight: 1.3,
          color: "#ffffff",
          textAlign: "center",
          WebkitTextStroke: `5px ${color}`,
          paintOrder: "stroke fill",
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
      </p>
    </div>
  );
};

/**
 * 再生中のセリフ字幕（複数話者ぶんを縦に積み上げ表示できる）。
 * 顔（画面中央〜上）にかからないよう、画面下部（縦80〜85%あたり）に下揃えで固定表示する。
 * 複数行が同時に積み上がる場合も、下端を固定して上方向に伸びるため下端がフレーム外に
 * ずれることはない。
 *
 * 注意: padding-top/bottom の%指定はCSS仕様上コンテナの「幅」基準で解決される
 * （高さ基準ではない）。本コンポジションは1080x1920固定のため、
 * ここでは%を使わず1920px基準のpx値で直接位置決めする。
 *
 * cut.caption（画面最下部1/3・タイトルや演出テロップ用、Caption.tsx参照）と同じカットで
 * 同時に表示される場合は、そのゾーン（テキストは概ね縦76%以降から出現）と重ならないよう
 * hasTitleCaption=true でさらに上（縦72%あたりが下端）に押し上げる。
 */
export const DialogueCaptions: React.FC<{
  lines: Array<{ text: string; speaker: Speaker }>;
  hasTitleCaption?: boolean;
}> = ({ lines, hasTitleCaption = false }) => {
  if (lines.length === 0) return null;
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        // 縦1920px基準: 通常は下端が縦85%(288px)、タイトルテロップと同時表示時は縦72%(538px)
        paddingBottom: hasTitleCaption ? "538px" : "288px",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 14,
          width: "100%",
        }}
      >
        {lines.map((line, i) => (
          <DialogueBubble key={i} text={line.text} speaker={line.speaker} />
        ))}
      </div>
    </AbsoluteFill>
  );
};
