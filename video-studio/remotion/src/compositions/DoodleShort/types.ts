/**
 * episode.json のスキーマ定義。
 * 詳細な仕様説明は video-studio/docs/setup-remotion.md を参照。
 */

export type CameraEffect = "zoom-in" | "zoom-out" | "pan" | "shake" | "none";

export type EpisodeCutPlaceholder = {
  /** CSS色（背景色） */
  color: string;
  /** プレースホルダー上に表示する説明テキスト（任意） */
  text?: string;
};

export type EpisodeCut = {
  /** 1始まりのカット番号（絵コンテと対応させる） */
  index: number;
  /** このカットの表示秒数 */
  durationSec: number;
  /**
   * 画像パス（episode.json のあるディレクトリからの相対パス）。
   * 1枚: 静止表示。2枚: toggleFps の速さで交互表示（目パチ・口パク風）。
   * 未指定 or 空の場合は placeholder を使う。
   */
  images?: string[];
  /** 2枚交互表示時の切り替え速度（デフォルト 6fps）。滑らかな補間はしない。 */
  toggleFps?: number;
  /** 画像がまだ無いカット用の単色+テキストのプレースホルダー */
  placeholder?: EpisodeCutPlaceholder;
  /** 画面下部1/3に表示する字幕テキスト（省略可＝字幕なしカット） */
  caption?: string;
  /** VOICEVOX生成前でも台本行を残しておくための参考テキスト（音声には使わない） */
  narrationText?: string;
  /** ナレーションwavパス（episode.json ディレクトリからの相対パス）。未生成なら null */
  narration?: string | null;
  /** 効果音ファイルパス（同上）。未生成/無音なら null */
  se?: string | null;
  /** カメラ演出。デフォルト "none" */
  camera?: CameraEffect;
  /** 制作メモ（画面には出さない） */
  note?: string;
};

export type EpisodeAudio = {
  /** BGMファイルパス（episode.json ディレクトリからの相対パス） */
  bgm?: string | null;
  /** BGM音量 0-1（デフォルト 0.4） */
  bgmVolume?: number;
};

export type Episode = {
  id: string;
  title: string;
  /** デフォルト 30 */
  fps?: number;
  /** デフォルト 1080 */
  width?: number;
  /** デフォルト 1920 */
  height?: number;
  audio?: EpisodeAudio;
  cuts: EpisodeCut[];
};

export type DoodleShortProps = {
  /** video-studio/episodes/<episodeId>/episode.json を読み込む */
  episodeId: string;
  /** calculateMetadata がロードして詰めるので通常は渡さない */
  episode?: Episode;
};
