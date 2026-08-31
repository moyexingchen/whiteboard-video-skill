#!/usr/bin/env python3
"""Step 3 — 画面 + 配音 + 字幕 → 最终成片

读取 timing.json 中的各段配音起点，用 ffmpeg adelay+amix 混音；
用 PIL 逐帧烧录白字黑边字幕；最后合并音视频输出成片。

用法:
  python mix_burn.py --video base.mp4 --vo-dir ./vo --srt master.srt --timing timing.json --output final.mp4
  python mix_burn.py --video base.mp4 --vo-dir ./vo --srt master.srt --timing timing.json --output final.mp4 --font-size 24 --margin-v 40

依赖:
  - ffmpeg（系统）
  - OpenCV（cv2）
  - Pillow（PIL）
  - ffprobe（用于时长校验）
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

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
    env_font = os.environ.get("SRT_WB_FONT")
    if env_font and os.path.exists(env_font):
        return env_font
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("no CJK font found, set SRT_WB_FONT env var")


def parse_srt(path: str) -> list[tuple[int, int, str]]:
    """解析 SRT 返回 [(start_ms, end_ms, text), ...]。"""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content.strip())
    subs = []
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


def mix_audio(vo_dir: str, timing_path: str, out_wav: str) -> str:
    """用 ffmpeg adelay+amix 混音。"""
    with open(timing_path, encoding="utf-8") as f:
        timing = json.load(f)
    lines = timing["lines"]
    n = len(lines)
    delays = [l["start_ms"] for l in lines]

    inputs = []
    for i in range(n):
        mp3 = os.path.join(vo_dir, f"line{i+1:02d}.mp3")
        if not os.path.exists(mp3):
            print(f"ERROR: {mp3} 不存在", file=sys.stderr)
            sys.exit(1)
        inputs += ["-i", mp3]

    parts = [f"[{i}:a]adelay={d}|{d}[a{i}]" for i, d in enumerate(delays)]
    mix_in = "".join(f"[a{i}]" for i in range(n))
    parts.append(f"{mix_in}amix=inputs={n}:normalize=0[aout]")
    fc = ";".join(parts)

    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + [
        "-filter_complex", fc, "-map", "[aout]",
        "-ar", "48000", "-ac", "2", out_wav
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg 混音失败:\n{r.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"混音: {out_wav}")
    return out_wav


def burn_subtitles(video_path: str, srt_path: str, out_path: str,
                   font_size: int | None = None, margin_v: int | None = None):
    """PIL 逐帧烧录白字黑边字幕。字号/边距缺省时按视频高度自适应。"""
    subs = parse_srt(srt_path)
    font_path = resolve_font()

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 60
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 自适应：1080p 高度 → 字号约 48、底部边距约 59
    if font_size is None:
        font_size = max(24, int(h * 0.045))
    if margin_v is None:
        margin_v = max(24, int(h * 0.055))
    font = ImageFont.truetype(font_path, font_size)

    # macOS 用 avc1，回退 mp4v
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"avc1"), fps, (w, h))
    if not writer.isOpened():
        writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

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
    print(f"字幕烧录: {out_path} ({total} frames)")


def combine(video_path: str, audio_path: str, out_path: str, duration: float):
    """合并音视频。"""
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", video_path, "-i", audio_path,
        "-filter_complex", "[1:a]apad[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration), out_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg 合并失败:\n{r.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"成片: {out_path}")


def main():
    p = argparse.ArgumentParser(description="画面 + 配音 + 字幕 → 最终成片")
    p.add_argument("--video", required=True, help="白板动画画面 mp4")
    p.add_argument("--vo-dir", required=True, help="配音文件目录")
    p.add_argument("--srt", required=True, help="SRT 字幕文件")
    p.add_argument("--timing", required=True, help="timing.json 文件")
    p.add_argument("--output", required=True, help="输出成片 mp4")
    p.add_argument("--font-size", type=int, default=None,
                   help="字幕字号（默认按视频高度自适应，1080p 约 48）")
    p.add_argument("--margin-v", type=int, default=None,
                   help="字幕底部边距（默认按视频高度自适应，1080p 约 59）")
    p.add_argument("--workdir", default=None, help="工作目录（临时文件存放，默认输出目录同级）")
    args = p.parse_args()

    workdir = args.workdir or os.path.join(os.path.dirname(args.output), "tmp_mix")
    os.makedirs(workdir, exist_ok=True)

    # 1) 混音
    mix_wav = os.path.join(workdir, "vo_mix.wav")
    mix_audio(args.vo_dir, args.timing, mix_wav)

    # 2) 烧录字幕
    subbed = os.path.join(workdir, "subbed.mp4")
    burn_subtitles(args.video, args.srt, subbed, args.font_size, args.margin_v)

    # 3) 合并
    with open(args.timing, encoding="utf-8") as f:
        timing = json.load(f)
    duration_sec = timing["total_ms"] / 1000
    combine(subbed, mix_wav, args.output, duration_sec)

    # 4) 校验
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", args.output],
        capture_output=True, text=True
    )
    final_dur = float(r.stdout.strip())
    print(f"成片时长: {final_dur:.2f}s（目标 {duration_sec:.2f}s）")
    print(f"输出: {args.output}")


if __name__ == "__main__":
    main()
