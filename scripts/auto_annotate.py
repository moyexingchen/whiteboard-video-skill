#!/usr/bin/env python3
"""Step 2 — 线稿图 + SRT → 标注 JSON（自动像素分析）

对线稿做连通域分析，按从左到右、从上到下排序，取前 N 个最大区域
（N = SRT 条数），生成 srt-whiteboard-animation 所需的 annotation.json。

用法:
  python auto_annotate.py --artwork line_art.png --srt master.srt --output annotation.json
  python auto_annotate.py --artwork line_art.png --timing timing.json --output annotation.json

可选:
  --padding 18        掩码内边距 px
  --hand-lead 70      笔尖比配音提前多少 ms 落笔
  --tail 700          末尾画面停留 ms
  --diff-threshold 55 非背景像素色差阈值（越大越严格，只捕深线条）
"""
import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

PADDING = 18
HAND_LEAD_MS = 70
TAIL_MS = 700
DIFF_THRESHOLD = 55


def parse_srt_times(srt_path: str) -> list[tuple[int, int, str]]:
    """解析 SRT 返回 [(start_ms, end_ms, text), ...]。"""
    with open(srt_path, encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content.strip())
    cues = []
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
        cues.append((start, end, text))
    return cues


def parse_timing(path: str) -> list[dict]:
    """从 timing.json 读 lines。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["lines"]


def detect_bg(img: np.ndarray) -> np.ndarray:
    """取四角 8px 平均色作为背景色（BGR float32）。"""
    h, w = img.shape[:2]
    corners = np.concatenate([
        img[:8, :8].reshape(-1, 3),
        img[:8, w-8:].reshape(-1, 3),
        img[h-8:, :8].reshape(-1, 3),
        img[h-8:, w-8:].reshape(-1, 3),
    ])
    return corners.mean(axis=0)


def find_regions(img: np.ndarray, n: int, diff_threshold: int = DIFF_THRESHOLD) -> list[dict]:
    """连通域分析，返回前 n 个最大区域 [{x,y,w,h}, ...]。"""
    h, w = img.shape[:2]
    bg = detect_bg(img)
    diff = np.abs(img.astype(np.float32) - bg).mean(axis=2)
    mask = (diff > diff_threshold).astype(np.uint8)
    print(f"  深色像素占比: {mask.mean():.1%}")

    # 小膨胀连接笔画
    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(mask, kernel, iterations=1)
    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    comps = []
    min_w, min_h = 80, 60  # 最小区域尺寸，避免预览脚本标签溢出
    for i in range(1, n_labels):
        x, y, ww, hh, area = stats[i]
        if area < 300:
            continue
        # 扩展过小区域到最小尺寸（以中心点为基准向外扩）
        cx, cy = x + ww // 2, y + hh // 2
        if ww < min_w:
            ww = min_w
            x = max(0, cx - ww // 2)
            if x + ww > w:
                x = w - ww
        if hh < min_h:
            hh = min_h
            y = max(0, cy - hh // 2)
            if y + hh > h:
                y = h - hh
        comps.append({"x": int(x), "y": int(y), "w": int(ww), "h": int(hh),
                       "cx": int(x + ww // 2), "cy": int(y + hh // 2), "area": int(area)})

    # 按 从左到右、从上到下 排序（先按 y 分带，带内按 x）
    # y 分带宽度 = 画布高度的 1/3
    band_h = max(h // 3, 50)
    comps.sort(key=lambda c: (c["cy"] // band_h, c["cx"]))
    return comps[:n]


def build_annotation(
    img_path: str,
    cues: list,           # [(start_ms, end_ms, text), ...] 或 timing lines
    timing_mode: str,    # "srt" or "timing"
    output: str,
    padding: int = PADDING,
    hand_lead: int = HAND_LEAD_MS,
    tail_ms: int = TAIL_MS,
    diff_threshold: int = DIFF_THRESHOLD,
):
    img = cv2.imread(img_path)
    if img is None:
        print(f"ERROR: 无法读取图片 {img_path}", file=sys.stderr)
        sys.exit(1)
    h, w = img.shape[:2]
    print(f"画布: {w} x {h}")

    n = len(cues)
    regions = find_regions(img, n, diff_threshold)
    print(f"找到 {len(regions)} 个区域（需要 {n} 个）")

    if len(regions) < n:
        print(f"WARNING: 区域数({len(regions)}) < 字幕数({n})，可能需要手动补充标注")

    # 计算时间轴
    if timing_mode == "srt":
        starts = [c[0] for c in cues]
        durations = [c[1] - c[0] for c in cues]
        texts = [c[2] for c in cues]
    else:
        starts = [c["start_ms"] for c in cues]
        durations = [c["duration_ms"] for c in cues]
        texts = [c["text"] for c in cues]

    total_ms = starts[-1] + durations[-1] + tail_ms

    # reveal: 笔先动 hand_lead ms
    reveal_starts = [s - hand_lead for s in starts]
    reveal_durations = []
    for i in range(n):
        nxt = reveal_starts[i + 1] if i < n - 1 else total_ms
        reveal_durations.append(nxt - reveal_starts[i])

    # 构建标注
    elements = []
    for i in range(min(n, len(regions))):
        r = regions[i]
        region = {"x": r["x"], "y": r["y"], "width": r["w"], "height": r["h"]}
        # handPath: 从区域左侧到右侧
        hp_start = [r["x"] + 10, r["cy"]]
        hp_end = [r["x"] + r["w"] - 10, r["cy"]]
        elements.append({
            "id": f"el-{i+1:02d}",
            "label": f"区域{i+1}",
            "sequence": i + 1,
            "narrativeRole": texts[i][:40],
            "subtitle": texts[i],
            "type": "structure",
            "region": region,
            "reveal": {
                "direction": "left_to_right" if i > 0 else "top_to_bottom",
                "startMs": reveal_starts[i],
                "durationMs": reveal_durations[i],
                "maskPaddingPx": padding,
                "protectedRegions": [],
            },
            "handPath": {
                "start": hp_start,
                "end": hp_end,
                "easing": "easeInOut",
            },
        })

    annotation = {
        "sceneId": "scene-01",
        "canvas": {"width": w, "height": h},
        "storyBasis": texts[0] if texts else "",
        "sceneDurationMs": total_ms,
        "elements": elements,
    }

    with open(output, "w", encoding="utf-8") as f:
        json.dump(annotation, f, ensure_ascii=False, indent=2)
    print(f"标注: {output} ({len(elements)} 元素, 总时长 {total_ms / 1000:.2f}s)")

    # 打印摘要
    for el in elements:
        r = el["region"]
        print(f"  {el['sequence']}. {el['label']}: x={r['x']} y={r['y']} w={r['width']} h={r['height']}  "
              f"reveal={el['reveal']['startMs']}-{el['reveal']['startMs']+el['reveal']['durationMs']}ms")


def main():
    p = argparse.ArgumentParser(description="线稿 + SRT/timing → 标注 JSON")
    p.add_argument("--artwork", required=True, help="线稿图片路径")
    p.add_argument("--srt", help="SRT 字幕文件路径")
    p.add_argument("--timing", help="timing.json 文件路径（与 --srt 二选一）")
    p.add_argument("--output", required=True, help="输出标注 JSON 路径")
    p.add_argument("--padding", type=int, default=PADDING, help=f"掩码内边距 px（默认 {PADDING}）")
    p.add_argument("--hand-lead", type=int, default=HAND_LEAD_MS, help=f"笔尖提前 ms（默认 {HAND_LEAD_MS}）")
    p.add_argument("--tail", type=int, default=TAIL_MS, help=f"末尾停留 ms（默认 {TAIL_MS}）")
    p.add_argument("--diff-threshold", type=int, default=DIFF_THRESHOLD, help=f"色差阈值（默认 {DIFF_THRESHOLD}）")
    args = p.parse_args()

    if args.srt:
        cues = parse_srt_times(args.srt)
        build_annotation(args.artwork, cues, "srt", args.output,
                         args.padding, args.hand_lead, args.tail, args.diff_threshold)
    elif args.timing:
        cues = parse_timing(args.timing)
        build_annotation(args.artwork, cues, "timing", args.output,
                         args.padding, args.hand_lead, args.tail, args.diff_threshold)
    else:
        p.error("必须提供 --srt 或 --timing")


if __name__ == "__main__":
    main()
