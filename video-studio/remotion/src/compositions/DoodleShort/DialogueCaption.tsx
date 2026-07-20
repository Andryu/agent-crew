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
 * cut.caption（画面下部1/3・タイトルや演出テロップ用）とは別レイヤーとして、
 * その少し上（画面55%あたりから下向き）に配置し、通常は重ならないようにしている。
 */
export const DialogueCaptions: React.FC<{ lines: Array<{ text: string; speaker: Speaker }> }> = ({
  lines,
}) => {
  if (lines.length === 0) return null;
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "center",
        paddingTop: "55%",
        pointerEvents: "none",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
        {lines.map((line, i) => (
          <DialogueBubble key={i} text={line.text} speaker={line.speaker} />
        ))}
      </div>
    </AbsoluteFill>
  );
};
