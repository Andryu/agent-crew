#!/usr/bin/env python3
"""
スマホUI（ステータスバー・ツールバー等）が写り込んだスクリーンショットから、
落書き本体の領域だけを自動検出してクロップするワンオフスクリプト。

方針:
- 各行/列が「非白ピクセルを含むか」を判定
- 非白の行が連続する塊（run）を複数検出し、最大の塊を「絵の本体」とみなす
  （UIアイコン類は絵の本体と大きな白い余白で分離されているため、
  別の小さな塊として検出される）
- 検出したbboxにマージンを付けてクロップ
"""
import sys
from PIL import Image

WHITE_THRESHOLD = 245  # これ以上ならほぼ白とみなす
MARGIN = 40


def non_white_row_mask(im: Image.Image):
    w, h = im.size
    px = im.load()
    mask = []
    for y in range(h):
        row_has_content = False
        for x in range(0, w, 2):  # 高速化のため間引きサンプリング
            r, g, b = px[x, y][:3]
            if r < WHITE_THRESHOLD or g < WHITE_THRESHOLD or b < WHITE_THRESHOLD:
                row_has_content = True
                break
        mask.append(row_has_content)
    return mask


def find_largest_run(mask):
    runs = []
    start = None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    if not runs:
        return None
    # 最大の(長さ)runを採用
    return max(runs, key=lambda r: r[1] - r[0])


def col_bbox_in_rows(im: Image.Image, y0: int, y1: int):
    w, h = im.size
    px = im.load()
    x_min, x_max = w, 0
    for y in range(y0, y1 + 1):
        for x in range(w):
            r, g, b = px[x, y][:3]
            if r < WHITE_THRESHOLD or g < WHITE_THRESHOLD or b < WHITE_THRESHOLD:
                if x < x_min:
                    x_min = x
                if x > x_max:
                    x_max = x
    return x_min, x_max


def crop_one(path: str):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    mask = non_white_row_mask(im)
    run = find_largest_run(mask)
    if run is None:
        print(f"[skip] {path}: 非白ピクセルが見つからず")
        return
    y0, y1 = run
    x0, x1 = col_bbox_in_rows(im, y0, y1)

    y0m = max(0, y0 - MARGIN)
    y1m = min(h - 1, y1 + MARGIN)
    x0m = max(0, x0 - MARGIN)
    x1m = min(w - 1, x1 + MARGIN)

    print(f"{path}: original={w}x{h} detected_bbox=({x0},{y0})-({x1},{y1}) "
          f"cropped_bbox=({x0m},{y0m})-({x1m},{y1m}) -> size={x1m-x0m+1}x{y1m-y0m+1}")

    cropped = im.crop((x0m, y0m, x1m + 1, y1m + 1))
    return cropped


def main():
    for path in sys.argv[1:]:
        cropped = crop_one(path)
        if cropped is None:
            continue
        orig_path = path.replace(".png", "_orig.png")
        import shutil
        shutil.copy2(path, orig_path)
        cropped.save(path)
        print(f"  saved backup -> {orig_path}")
        print(f"  overwrote    -> {path}")


if __name__ == "__main__":
    main()
