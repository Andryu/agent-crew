/**
 * episode.json のスキーマ定義（v2: セリフ劇・口パク・動画埋め込み対応）。
 * 詳細な仕様説明は video-studio/docs/setup-remotion.md を参照。
 */

export type CameraEffect = "zoom-in" | "zoom-out" | "pan" | "shake" | "kenburns" | "none";

export type Speaker = "kanojo" | "kareshi" | "mob";

export type EpisodeCutPlaceholder = {
  /** CSS色（背景色。紙テクスチャのベースカラーとして使う） */
  color: string;
  /** プレースホルダー上に表示する説明テキスト（任意） */
  text?: string;
};

export type MouthLayer = {
  /** 口を閉じた状態の画像パス（episode.json ディレクトリからの相対パス） */
  mouthClosed: string;
  /** 口を開けた状態の画像パス（同上） */
  mouthOpen: string;
  /** 口パクの切り替え速度（デフォルト 8fps）。滑らかな補間はしない */
  toggleFps?: number;
};

export type DialogueLine = {
  /** 話者。字幕の縁色分け（DialogueCaption）に使う */
  speaker: Speaker;
  /** セリフwavパス（episode.json ディレクトリからの相対パス） */
  wav: string;
  /** カット先頭からの再生開始秒（複数セリフをこの値でシーケンス配置する） */
  startSec: number;
  /** wav の実測秒数（口パクウィンドウ・字幕表示ウィンドウ・尺検証に使う） */
  durationSec: number;
  /**
   * 指定時、このセリフの再生中だけ対象カットの表示画像を
   * mouthClosed/mouthOpen の2枚で toggleFps トグルする（口パク）。
   * 未指定なら通常の images 表示のまま（口開き素材が無い間の後方互換動作）。
   */
  mouthLayer?: MouthLayer;
  /**
   * このセリフの再生ウィンドウ中だけ表示するセリフ字幕（省略可）。
   * cut.caption（タイトル・演出テロップ用）とは別レイヤーで、話者ごとに縁色を変えて重ねて表示する。
   */
  text?: string;
};

export type EpisodeCut = {
  /** 1始まりのカット番号（絵コンテと対応させる） */
  index: number;
  /** このカットの表示秒数 */
  durationSec: number;
  /**
   * 全画面フルブリードで最背面に描画する背景画像1枚（episode.json ディレクトリからの相対パス、省略可）。
   * 既存の images/placeholder はこの上に今まで通り重ねて描画する。
   * 背景・前景とも白背景の線画である前提で、前景側に mix-blend-mode: multiply を適用して合成する
   * （白同士は透過的に振る舞い、線画だけが両方残る。マスク等の凝った合成はしない）。
   * idleSway は前景とは別位相で背景にも適用する。
   */
  background?: string;
  /**
   * 画像 or 動画パス（episode.json のあるディレクトリからの相対パス）。
   * - 拡張子が .mp4 / .webm の場合は OffthreadVideo で埋め込み表示（Animated Drawings 等のモーションクリップ用）。
   * - それ以外（png/jpg等）: 1枚=静止表示。2枚=toggleFpsの速さで交互表示（目パチ・口パク風）。
   * 未指定 or 空の場合は placeholder を使う。
   */
  images?: string[];
  /** 2枚交互表示時の切り替え速度（デフォルト 6fps）。滑らかな補間はしない。 */
  toggleFps?: number;
  /**
   * images が動画(.mp4/.webm)のときのループ単位秒。
   * 指定時は Loop コンポーネントでこの秒数を1周として繰り返す。未指定ならループせず1回再生。
   */
  videoLoopSec?: number;
  /** 画像がまだ無いカット用の単色+テキストのプレースホルダー（紙テクスチャ付きで描画） */
  placeholder?: EpisodeCutPlaceholder;
  /** 画面下部1/3に表示する字幕テキスト（省略可＝字幕なしカット） */
  caption?: string;
  /** VOICEVOX生成前でも台本行を残しておくための参考テキスト（音声には使わない） */
  narrationText?: string;
  /**
   * @deprecated dialogue（配列・複数話者対応）を使うこと。
   * ナレーション型の単一音声のみの場合の後方互換フィールドとして引き続き使用可。
   * ナレーションwavパス（episode.json ディレクトリからの相対パス）。未生成なら null
   */
  narration?: string | null;
  /**
   * セリフ配列（v2）。startSec でカット内にシーケンス配置し、複数話者のセリフ劇を組み立てる。
   * narration と併用可（通常はどちらか一方を使う）。
   */
  dialogue?: DialogueLine[];
  /** 効果音ファイルパス（同上）。未生成/無音なら null */
  se?: string | null;
  /** カメラ演出。デフォルト "none" */
  camera?: CameraEffect;
  /**
   * 常時ゆらゆら演出（idleSway）のON/OFF。省略時 true（デフォルトON、既存カットとの後方互換）。
   * イラスト日記モードのように動きを最小限にしたいカットでは false を指定する。
   */
  sway?: boolean;
  /**
   * 画面右下に小さく表示するクレジット表記（例: "VOICEVOX:波音リツ"）。
   * 規約上必須のクレジットなど、placeholder/images が差し替わっても消えてはいけない表示に使う。
   */
  credit?: string;
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
