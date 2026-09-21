/**
 * Note: When using the Node.JS APIs, the config file
 * doesn't apply. Instead, pass options directly to the APIs.
 *
 * All configuration options: https://remotion.dev/docs/config
 */

import path from "node:path";
import { Config } from "@remotion/cli/config";

// remotion.config.ts はCJSとしてバンドルされるため import.meta は使えない。
// Remotion CLI は video-studio/remotion をカレントディレクトリとして実行される前提（scripts/render.sh もそう呼ぶ）。
// episode.json・画像・音声は video-studio/episodes/<episodeId>/ 配下に置く運用。
// public dir をそこに向けることで staticFile(`${episodeId}/...`) で参照できる。
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setPublicDir(path.join(process.cwd(), "..", "episodes"));
