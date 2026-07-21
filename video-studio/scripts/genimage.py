#!/usr/bin/env python3
"""
Gemini (Nano Banana) 画像生成スクリプト

手書き落書き風の素材を、オーナーの参照画像（マルチモーダル入力）を渡しながら
Gemini の image generation モデルで生成する。

使い方:
  python3 genimage.py \
    --prompt "プロンプト文字列" \
    --ref path/to/ref1.png --ref path/to/ref2.png \
    --out path/to/output.png \
    [--model gemini-2.5-flash-image]

環境変数 GEMINI_API_KEY が必須。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash-image"


def guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    return "image/png"


def build_parts(prompt: str, ref_paths: list[str]) -> list[dict]:
    parts = []
    for ref in ref_paths:
        with open(ref, "rb") as f:
            data = f.read()
        parts.append({
            "inline_data": {
                "mime_type": guess_mime(ref),
                "data": base64.b64encode(data).decode("ascii"),
            }
        })
    parts.append({"text": prompt})
    return parts


def generate(prompt: str, ref_paths: list[str], out_path: str, model: str, api_key: str, aspect_ratio: str | None = None) -> None:
    url = f"{API_BASE}/{model}:generateContent?key={api_key}"
    generation_config = {
        "responseModalities": ["IMAGE"]
    }
    if aspect_ratio:
        generation_config["imageConfig"] = {"aspectRatio": aspect_ratio}
    body = {
        "contents": [
            {
                "role": "user",
                "parts": build_parts(prompt, ref_paths),
            }
        ],
        "generationConfig": generation_config,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"[HTTPError {e.code}] {err_body}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(raw)

    candidates = data.get("candidates", [])
    if not candidates:
        print(f"[error] no candidates returned: {json.dumps(data, ensure_ascii=False)[:2000]}", file=sys.stderr)
        sys.exit(1)

    saved = False
    for cand in candidates:
        content = cand.get("content", {})
        for part in content.get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                img_bytes = base64.b64decode(inline["data"])
                os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                saved = True
                print(f"[ok] saved -> {out_path} ({len(img_bytes)} bytes)")
            elif part.get("text"):
                print(f"[model text] {part['text']}", file=sys.stderr)

    if not saved:
        print(f"[error] no image data in response: {json.dumps(data, ensure_ascii=False)[:2000]}", file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--ref", action="append", default=[], help="参照画像パス（複数指定可）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--aspect-ratio", default=None, help='例: "9:16"（省略時はモデルのデフォルト）')
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[error] GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    generate(args.prompt, args.ref, args.out, args.model, api_key, args.aspect_ratio)


if __name__ == "__main__":
    main()
