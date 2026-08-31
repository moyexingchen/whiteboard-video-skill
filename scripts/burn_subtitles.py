#!/usr/bin/env python3
"""PIL 逐帧烧录字幕：白字黑边，自动探测 CJK 字体，底部居中。
macOS 下 OpenCV 用 avc1 编码器，回退 mp4v。
用法: burn_subtitles.py <input.mp4> <subs.srt> <output.mp4> [font_size] [margin_v]
"""
import sys, os, re
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]

def resolve_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("no CJK font found, set SRT_WB_FONT")

def parse_srt(path):
    subs = []
    with open(path, encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content.strip())
    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        m = re.match(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})", lines[1])
        if not m:
            continue
        g = m.groups()
        start = (int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2])) * 1000 + int(g[3])
        end = (int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6])) * 1000 + int(g[7])
        text = " ".join(lines[2:])
        subs.append((start, end, text))
    return subs

def main():
    src, srt_path, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    font_size = int(sys.argv[4]) if len(sys.argv) > 4 else 24
    margin_v = int(sys.argv[5]) if len(sys.argv) > 5 else 40

    subs = parse_srt(srt_path)
    font_path = os.environ.get("SRT_WB_FONT") or resolve_font()
    font = ImageFont.truetype(font_path, font_size)

    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 60
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"avc1"), fps, (w, h))
    if not writer.isOpened():
        writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    y_center = h - margin_v - font_size // 2
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        ms = int(idx / fps * 1000)
        text = ""
        for s, e, t in subs:
            if s <= ms < e:
                text = t
                break
        if text:
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(img)
            d = ImageDraw.Draw(pil)
            d.text((w // 2, y_center), text, font=font, fill=(255, 255, 255),
                   anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
            frame = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
        writer.write(frame)
        idx += 1
        if idx % 300 == 0:
            print(f"  burned {idx}/{total} frames", flush=True)
    cap.release()
    writer.release()
    print(f"done: {dst} ({total} frames)")

if __name__ == "__main__":
    main()
