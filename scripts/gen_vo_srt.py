#!/usr/bin/env python3
"""Step 1 — 口播稿 → 配音音频 + SRT 字幕 + timing.json

把一段中文口播稿按句号/感叹号/问号/换行切句，逐句用 edge-tts 生成 MP3，
用 ffprobe 测每句真实时长，按真实时长生成 SRT 时间轴和 timing.json。

用法:
  python gen_vo_srt.py --text "这是一段口播稿。" --outdir ./output
  python gen_vo_srt.py --text-file script.txt --outdir ./output
  python gen_vo_srt.py --text-file script.txt --outdir ./output --voice zh-CN-YunxiNeural

输出文件:
  <outdir>/vo/line01.mp3 ... lineNN.mp3
  <outdir>/master.srt
  <outdir>/timing.json
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_VOICE = "zh-CN-YunxiNeural"
INITIAL_SILENCE = 400   # ms, 开头静音
GAP_MS = 20            # ms, 句间间隔
TAIL_MS = 700          # ms, 末尾画面停留

SENTENCE_SPLIT = re.compile(r"[。！？!?\n]+")


def split_sentences(text: str) -> list[str]:
    """按中文标点和换行切句，过滤空句。"""
    parts = SENTENCE_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


async def gen_audio(text: str, voice: str, rate: str, pitch: str, out_path: str):
    """用 edge-tts 生成单句 MP3。"""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(out_path)


def measure_duration(mp3_path: str) -> int:
    """用 ffprobe 测 MP3 时长（ms）。"""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", mp3_path],
        capture_output=True, text=True
    )
    seconds = float(r.stdout.strip())
    return round(seconds * 1000)


def fmt_srt_time(ms: int) -> str:
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    p = argparse.ArgumentParser(description="口播稿 → 配音 + SRT + timing.json")
    p.add_argument("--text", help="口播稿文本（直接传入）")
    p.add_argument("--text-file", help="口播稿文件路径")
    p.add_argument("--outdir", required=True, help="输出目录")
    p.add_argument("--voice", default=DEFAULT_VOICE, help=f"edge-tts 音色（默认 {DEFAULT_VOICE}）")
    p.add_argument("--rate", default="+0%", help="语速（如 +10%%）")
    p.add_argument("--pitch", default="+0Hz", help="音调（如 +5Hz）")
    p.add_argument("--initial-silence", type=int, default=INITIAL_SILENCE, help=f"开头静音 ms（默认 {INITIAL_SILENCE}）")
    p.add_argument("--gap", type=int, default=GAP_MS, help=f"句间间隔 ms（默认 {GAP_MS}）")
    p.add_argument("--tail", type=int, default=TAIL_MS, help=f"末尾停留 ms（默认 {TAIL_MS}）")
    args = p.parse_args()

    # 读取口播稿
    if args.text_file:
        with open(args.text_file, encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        p.error("必须提供 --text 或 --text-file")

    sentences = split_sentences(text)
    if not sentences:
        p.error("口播稿为空或无法切句")
    print(f"切句: {len(sentences)} 条")
    for i, s in enumerate(sentences, 1):
        print(f"  {i}. {s}")

    # 创建输出目录
    outdir = Path(args.outdir)
    vo_dir = outdir / "vo"
    vo_dir.mkdir(parents=True, exist_ok=True)

    # 逐句生成配音
    durations = []
    for i, sentence in enumerate(sentences, 1):
        mp3_path = str(vo_dir / f"line{i:02d}.mp3")
        try:
            asyncio.run(gen_audio(sentence, args.voice, args.rate, args.pitch, mp3_path))
            dur = measure_duration(mp3_path)
            durations.append(dur)
            print(f"  line{i:02d}: {dur}ms  ({sentence[:20]}...)")
        except Exception as e:
            print(f"  line{i:02d} FAIL: {e}", file=sys.stderr)
            sys.exit(1)

    # 计算时间轴
    starts = []
    t = args.initial_silence
    for d in durations:
        starts.append(t)
        t += d + args.gap
    total_ms = starts[-1] + durations[-1] + args.tail

    # 生成 SRT
    srt_lines = []
    for i, (s, d, sentence) in enumerate(zip(starts, durations, sentences), 1):
        end = s + d
        srt_lines.append(f"{i}\n{fmt_srt_time(s)} --> {fmt_srt_time(end)}\n{sentence}\n")
    srt_path = outdir / "master.srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    print(f"\nSRT: {srt_path}")

    # 生成 timing.json
    timing = {
        "voice": args.voice,
        "rate": args.rate,
        "pitch": args.pitch,
        "initial_silence_ms": args.initial_silence,
        "gap_ms": args.gap,
        "tail_ms": args.tail,
        "total_ms": total_ms,
        "lines": [
            {
                "index": i,
                "text": sentence,
                "duration_ms": d,
                "start_ms": s,
                "file": f"vo/line{i:02d}.mp3",
            }
            for i, (sentence, d, s) in enumerate(zip(sentences, durations, starts), 1)
        ],
    }
    timing_path = outdir / "timing.json"
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)
    print(f"Timing: {timing_path}")
    print(f"总时长: {total_ms / 1000:.2f}s")


if __name__ == "__main__":
    main()
