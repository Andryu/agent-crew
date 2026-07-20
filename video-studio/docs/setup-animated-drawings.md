# Meta AnimatedDrawings セットアップ手順

手書き落書き風ショート動画パイプラインの「④ 動き付け」工程を担う [facebookresearch/AnimatedDrawings](https://github.com/facebookresearch/AnimatedDrawings)（OSS）のローカル環境構築記録。

検証環境: macOS 26.5.2 (Darwin 25.5.0) / Apple Silicon (arm64)

## 結論（TL;DR）

- Python 3.8.13 + condaで**ネイティブarm64のまま**インストール成功。`CONDA_SUBDIR=osx-64`のRosetta回避策は不要だった（後述）。
- サンプルのMP4書き出し（`export_mp4_example.yaml`相当）はヘッドレスシェルから `USE_MESA` の指定なしで問題なく成功した。500x500 / h264 / 約26秒のMP4が生成された。
- TorchServeによるキャラ自動アノテーション（Docker版）は**ビルド・起動・疎通確認・実キャラ画像でのアノテーション〜MP4化まで一通り成功**した（詳細は「Docker / TorchServe自動アノテーション」章）。Colima上でネイティブarm64ビルドとして進行し、ビルド自体は約10分程度で完了した。
- `video-studio/scripts/animate.sh` を作成し、アノテーション済みディレクトリ＋モーション名からMP4を書き出せることを確認済み。EP01の実キャラ画像（`kareshi_body.png`）でも動作確認済み。

## 1. リポジトリの配置

作業リポジトリ（このagent-crewワークツリー）にはcloneせず、専用の作業ディレクトリを用意する。

```bash
mkdir -p ~/Workspace/video-tools
cd ~/Workspace/video-tools
git clone https://github.com/facebookresearch/AnimatedDrawings.git
```

`~/Workspace/video-tools/AnimatedDrawings` が本体リポジトリのルートになる。

## 2. Python環境の構築（conda）

### 2-1. condaの導入

このマシンには当初condaが入っていなかったため、Homebrewでminiforge（conda-forgeベースのMiniconda相当）を導入した。

```bash
brew install --cask miniforge
```

インストール先: `/opt/homebrew/Caskroom/miniforge/base`。`conda`コマンドが `/opt/homebrew/bin/conda` にリンクされる。

### 2-2. 環境作成

READMEの推奨コマンドをそのまま実行した。

```bash
conda create --name animated_drawings python=3.8.13 -y
```

**注意点（Apple Silicon）**: READMEには「M1/M2でアーキテクチャエラーが出たら `~/.condarc` に `osx-64` が混入していないか確認せよ、`osx-arm64` と `noarch` だけにせよ」という注意書きがある。今回の環境では `~/.condarc` 自体が存在せず（条件クリア）、`conda create` はconda-forgeのosx-arm64ビルドを解決してネイティブarm64のPython 3.8.13環境を作成できた。

```bash
python -c "import platform; print(platform.machine())"
# => arm64
```

もし将来的にosx-arm64ビルドが解決できない状況に当たった場合は、以下でRosetta経由のx86_64環境にフォールバックできる（今回は不要だった）。

```bash
CONDA_SUBDIR=osx-64 conda create --name animated_drawings python=3.8.13 -y
conda activate animated_drawings
conda config --env --set subdir osx-64
```

### 2-3. パッケージインストール

```bash
conda activate animated_drawings
cd ~/Workspace/video-tools/AnimatedDrawings
pip install -e .
```

`setup.py` に列挙された numpy / scipy / scikit-image / opencv-python / glfw / PyOpenGL / torchserve 等がすべてarm64向けwheelで解決され、コンパイルなしで完了した（所要時間: 数分）。

`DEPRECATION: Legacy editable install ... setup.py develop is deprecated` という警告が出るが、pipのバージョン差によるもので動作に影響はない。

## 3. サンプルMP4の書き出し検証

READMEの「Export MP4 video」手順どおり、Pythonインタプリタから実行した。

```bash
conda activate animated_drawings
cd ~/Workspace/video-tools/AnimatedDrawings
python -c "
from animated_drawings import render
render.start('./examples/config/mvc/export_mp4_example.yaml')
"
```

**結果**: `video.mp4` がリポジトリルートに生成された。

```
ISO Media, MP4 Base Media v1
codec: h264, 500x500, duration: 25.97s, size: 313323 bytes
```

### ヘッドレス実行について

READMEには「リモートサーバー等でヘッドレス実行する場合は `view.USE_MESA: True` を設定せよ」と書かれているが、**今回の検証環境（対話シェル無しのbashサブプロセス経由）では `USE_MESA` を指定せずとも問題なく動作した**。macOSのGLFWがオフスクリーン/隠しウィンドウのコンテキストを問題なく作れたためと考えられる。

もし別環境（SSH経由のヘッドレスLinuxサーバー等）で `glfw` の初期化エラーやOpenGLコンテキストエラーが出た場合は、mvc configの `view` セクションに以下を追加する回避策がある。

```yaml
view:
  USE_MESA: True
```

`video-studio/scripts/animate.sh` では `USE_MESA=1` 環境変数を指定するとこのフラグを自動付与できるようにしてある（デフォルトはOFF）。

## 4. Docker / TorchServe自動アノテーション

キャラ画像から関節アノテーション（`char_cfg.yaml` 等）を自動生成するには、TorchServeで学習済み検出・姿勢推定モデルを立ち上げる必要がある。README記載の2オプションのうち、今回はOption 1（Docker）を検証した。

### Dockerの前提状況

このマシンのDocker CLIはDocker Desktopではなく[Colima](https://github.com/abiko/colima)（軽量Docker/Lima VM）をバックエンドとしていた。`docker info` はデーモン未起動でエラーになったため、Colimaを起動する必要があった。

```bash
colima start
```

デフォルトのColimaプロファイルはCPU 2 / メモリ2GiBで、mmcv-fullのソースビルドを含む本Dockerfileには不足すると判断し、リソースを増強して起動し直した。

```bash
colima stop
colima start --cpu 4 --memory 8 --disk 60
```

### ビルド

```bash
cd ~/Workspace/video-tools/AnimatedDrawings/torchserve
docker build -t docker_torchserve .
```

**所要時間の目安**: READMEは「MacBook Pro 2021で約5-7分」としているが、これはDocker Desktop使用時の実測と思われる。Colima環境ではベースイメージ `continuumio/miniconda3` がマルチアーキ対応のため、Apple Silicon上で**エミュレーションなしのネイティブarm64ビルド**として進行した。実測では合計10分程度で完了。ネックになるのは `RUN mim install mmcv-full==1.7.0`（ソースからのCコンパイルを含む）のステップで、単体で6分前後かかった。ビルド後のイメージサイズは約6.78GB。

起動後の疎通確認（**実施済み・成功**）:

```bash
docker run -d --name docker_torchserve -p 8080:8080 -p 8081:8081 docker_torchserve
sleep 10
curl http://localhost:8080/ping
# => {"status": "Healthy"}

curl http://localhost:8081/models
# => drawn_humanoid_detector, drawn_humanoid_pose_estimator の2モデルがロード済み
```

疎通できたら、画像からアノテーション＋アニメーション一括生成が可能になる。

```bash
cd ~/Workspace/video-tools/AnimatedDrawings/examples
python image_to_animation.py drawings/garlic.png garlic_out
```

### 実キャラ画像での検証結果（EP01 `kareshi_body.png`）

EP01用に用意された実際のキャラ画像（`video-studio/episodes/ep01/assets/kareshi_body.png`）で自動アノテーション単体を実行し、動作を確認した。

```bash
cd ~/Workspace/video-tools/AnimatedDrawings/examples
python image_to_annotations.py \
  video-studio/episodes/ep01/assets/kareshi_body.png \
  <出力先ディレクトリ>
```

- `char_cfg.yaml`（16関節の骨格）・`mask.png`・`texture.png`・`joint_overlay.png`が生成され、関節位置は頭から足先まで妥当な位置に配置されていた。
- 標準出力に `WARNING:root:point [...] not inside or on edge of any triangle in mesh. Skipping it` という警告が複数出た。これは眉・目などマスクのシルエット外にある細部の点がテクスチャメッシュの三角形に含まれずスキップされる、というもので、**レンダリング自体は問題なく完走する**（後述のMP4化で確認済み）。手描きの線がキャラのマスク輪郭からはみ出している場合に出やすい。
- 生成したアノテーションを `animate.sh` に渡し、waveモーションでMP4化まで成功した（839フレーム、約12秒処理）。
- ただし出力されたMP4では、キャラが**画面の左下に小さく表示**された。これは `export_mp4_example.yaml` 由来のデフォルトカメラ設定（`CAMERA_POS: [2.0, 0.7, 8.0]` / `CAMERA_FWD: [0.0, 0.5, 8.0]`）が同梱サンプルキャラ（char1、height=602px）向けにチューニングされたものであり、EP01キャラ（height=312px、体格やアスペクト比が異なる）ではフレーミングが合わないため。**本番投入時はキャラごとに `CAMERA_POS`/`CAMERA_FWD` を調整するか、`char_cfg.yaml` の `height` に応じて自動計算するロジックを追加する必要がある。**

### ビルドに失敗する/時間がかかりすぎる場合の代替手段

Docker/TorchServeのセットアップが重い、あるいはCPUアーキテクチャの問題でビルドが通らない場合、以下の代替手段がある。

1. **macOSローカル実行（Dockerなし）**: リポジトリ同梱の `torchserve/setup_macos.sh` を使う。Javaランタイムのインストール、`torch==1.13.0` 系のpip installを行い、Dockerを介さずホストマシン上で直接TorchServeを起動できる。
   ```bash
   cd ~/Workspace/video-tools/AnimatedDrawings/torchserve
   ./setup_macos.sh
   torchserve --start --ts-config config.local.properties --foreground
   ```
   ただし `animated_drawings` conda環境（Python 3.8.13）とは別に、`torch==1.13.0` 等の依存関係が入る点に注意（衝突を避けるなら別envで実行するのが安全）。

2. **手動アノテーション（Web demo）**: [sketch.metademolab.com](https://sketch.metademolab.com/) のブラウザデモで画像をアップロードし、自動検出→必要なら関節位置を手動修正→結果をダウンロードする。コード不要で最も手早い。

3. **手動アノテーション（fix_annotations.py のWeb UI）**: 一度何らかの方法（Docker/ローカルTorchServe/Web demo）でアノテーションを生成した後、関節位置がずれている場合はローカルのFlask製Web UIで修正できる。
   ```bash
   cd ~/Workspace/video-tools/AnimatedDrawings/examples
   python fix_annotations.py garlic_out/
   # http://127.0.0.1:5050 をブラウザで開き、関節をドラッグして再Submit
   ```

4. **同梱サンプルキャラをそのまま使う**: `examples/characters/char1`〜`char6` は既にアノテーション済みなので、動き付けパイプライン単体（`animate.sh`）の検証・撮影テンプレートの試作にはこれで十分。新しい絵を自動アノテーションする本番フローだけDocker/TorchServeが必要になる。

## 5. animate.sh の使い方

`video-studio/scripts/animate.sh` はconda環境のactivateとrender呼び出しをラップしたスクリプト。

```bash
video-studio/scripts/animate.sh <char_anno_dir> <motion_name> <output_mp4_path> [retarget_cfg]
```

- `char_anno_dir`: `char_cfg.yaml` を含むアノテーション済みディレクトリ（例: `~/Workspace/video-tools/AnimatedDrawings/examples/characters/char1`）
- `motion_name`: 組み込みプリセット名（`dab` / `jesse_dance` / `jumping_jacks` / `jumping` / `wave_hello` / `zombie`）、またはmotion configへの直接パス。利便のため `jump` → `jumping`、`wave` → `wave_hello` のエイリアスを用意している。
- `output_mp4_path`: 出力先MP4パス
- `retarget_cfg`: 省略時は `examples/config/retarget/fair1_spf.yaml`（同梱の全サンプルキャラ char1〜char6 と同じ骨格に対応）

### 動作確認済みの実行例

```bash
video-studio/scripts/animate.sh \
  ~/Workspace/video-tools/AnimatedDrawings/examples/characters/char1 \
  wave \
  ./out/char1_wave.mp4
# => char1が手を振るMP4（839フレーム、約17秒処理）が生成された

video-studio/scripts/animate.sh \
  ~/Workspace/video-tools/AnimatedDrawings/examples/characters/char2 \
  jump \
  ./out/char2_jump.mp4
# => char2がジャンプするMP4（504フレーム、約6秒処理）が生成された
```

**組み込みモーションに「walk」は同梱されていない**点に注意。台本で歩行モーションが必要な場合は、以下のいずれかで対応する。

- `zombie` モーション（ゾンビ歩き、雰囲気next-bestとして代用可）
- 自前のBVHファイルを用意し、`examples/config/motion/` を参考に新しいmotion configを作成して `animate.sh` の第2引数にそのパスを渡す（[Using BVH Files with Different Skeletons](https://github.com/facebookresearch/AnimatedDrawings#using-bvh-files-with-different-skeletons) 参照）
- Rokoko等でスマホ動画から歩行BVHを自作する（README「Creating Your Own BVH Files」参照）

## 6. 既知の注意点・トラブルシューティングまとめ

| 事象 | 原因 | 対処 |
|---|---|---|
| `conda: command not found` | condaが未導入 | `brew install --cask miniforge` |
| `conda create` が `osx-64` パッケージを解決しようとする | `~/.condarc` に `osx-64` が残っている | condarcから `osx-64` を除去し `osx-arm64`/`noarch` のみにする（今回は該当なし） |
| Apple Siliconでどうしてもarm64ビルドが解決できない | conda-forgeにその組み合わせのarm64ビルドが無い | `CONDA_SUBDIR=osx-64` でRosetta越しのx86_64環境として作成 |
| ヘッドレス実行でウィンドウ生成エラー | リモートLinux等でディスプレイが無い | mvc configに `view.USE_MESA: True` を追加（`animate.sh` は `USE_MESA=1` で対応） |
| `docker info` がデーモン未起動エラー | Docker CLIのバックエンドがColimaで未起動 | `colima start` |
| TorchServe Dockerビルドが遅い/メモリ不足で落ちる | Colimaのデフォルトリソース（CPU2/メモリ2GB）が不足 | `colima stop && colima start --cpu 4 --memory 8 --disk 60` |
| 組み込みモーションに「walk」が無い | サンプルセットの都合 | `zombie` で代用、または自前BVHを用意 |
| 自前キャラで自動アノテーション実行時に `point [...] not inside or on edge of any triangle in mesh` 警告が出る | 手描きの線（眉・アクセサリ等）がマスク輪郭からはみ出している | レンダリングへの影響は軽微（該当点がスキップされるのみ）。気になる場合は `fix_annotations.py` でマスクや関節を手動修正 |
| 自前キャラのMP4でキャラが画面の隅に小さく表示される | `export_mp4_example.yaml` 由来のデフォルトカメラ（`CAMERA_POS`/`CAMERA_FWD`）は同梱サンプル（char1, height=602px）向けの値 | キャラの `char_cfg.yaml` の `height`・体格に応じて `view.CAMERA_POS`/`CAMERA_FWD` を個別調整する |

## 7. 参考リンク

- 本体リポジトリ: https://github.com/facebookresearch/AnimatedDrawings
- ブラウザデモ（手動アノテーション代替手段）: https://sketch.metademolab.com/
- config仕様: `examples/config/README.md`（clone後のリポジトリ内）
