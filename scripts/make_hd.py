#!/usr/bin/env python3
"""HD 横屏适配 — 线稿 + 标注 → 1920×1080 画布

把任意尺寸线稿等比缩放、居中贴到目标尺寸（默认 1920×1080）的米黄画布上，
标注 JSON 中所有画布坐标同步线性变换（缩放 + 平移）。

适配后的线稿 + 标注交给 render_stream_whiteboard.py 渲染（需 --cap-long-edge 1920），
即可输出标准 16:9 高清横屏白板动画。

用法:
  python make_hd.py --artwork scene-01.png --annotation scene-01.annotation.json \
      --output-artwork scene-01.hd.png --output-annotation scene-01.hd.annotation.json
  # 可选 --width 1920 --height 1080 --bg "#F5EBD7"（默认取四角中值自适应）

依赖: OpenCV（cv2）
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def detect_bg(img_bgr: np.ndarray) -> tuple[int, int, int]:
    """取四角 margin 区域的中值颜色作为背景色。"""
    h, w = img_bgr.shape[:2]
    margin = max(3, min(h, w) // 50)
    samples = [img_bgr[:margin, :margin], img_bgr[:margin, -margin:],
               img_bgr[-margin:, :margin], img_bgr[-margin:, -margin:]]
    return tuple(int(v) for v in np.median(
        np.concatenate([s.reshape(-1, 3) for s in samples]), axis=0))


def scale_rect(rect: dict, sx: float, sy: float, dx: int, dy: int) -> dict:
    return {
        "x": int(round(rect["x"] * sx + dx)),
        "y": int(round(rect["y"] * sy + dy)),
        "width": int(round(rect["width"] * sx)),
        "height": int(round(rect["height"] * sy)),
    }


def scale_pt(pt: list, sx: float, sy: float, dx: int, dy: int) -> list:
    return [int(round(pt[0] * sx + dx)), int(round(pt[1] * sy + dy))]


def main():
    p = argparse.ArgumentParser(description="线稿+标注 → 高清横屏画布适配")
    p.add_argument("--artwork", required=True, help="原线稿 PNG")
    p.add_argument("--annotation", required=True, help="原标注 JSON")
    p.add_argument("--output-artwork", required=True, help="输出适配后线稿 PNG")
    p.add_argument("--output-annotation", required=True, help="输出适配后标注 JSON")
    p.add_argument("--width", type=int, default=1920, help="目标宽（默认 1920）")
    p.add_argument("--height", type=int, default=1080, help="目标高（默认 1080）")
    p.add_argument("--bg", default=None, help='背景色 hex，如 "#F5EBD7"（默认四角自适应）')
    args = p.parse_args()

    img = cv2.imread(args.artwork, cv2.IMREAD_COLOR)
    if img is None:
        print(f"[err] 无法读取线稿: {args.artwork}", file=sys.stderr)
        return 1
    ann = json.loads(Path(args.annotation).read_text(encoding="utf-8"))

    tw, th = args.width, args.height
    h0, w0 = img.shape[:2]

    # 等比缩放，完整放入目标画布（不裁切）
    scale = min(tw / w0, th / h0)
    nw, nh = int(round(w0 * scale)), int(round(h0 * scale))
    # 偶数对齐（编码要求）
    nw -= nw % 2
    nh -= nh % 2
    dx, dy = (tw - nw) // 2, (th - nh) // 2

    if args.bg:
        hexs = args.bg.lstrip("#")
        bg = tuple(int(hexs[i:i + 2], 16) for i in (4, 2, 0))  # hex RGB → BGR
    else:
        bg = detect_bg(img)

    canvas = np.empty((th, tw, 3), dtype=np.uint8)
    canvas[:] = bg
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    canvas[dy:dy + nh, dx:dx + nw] = resized

    out = Path(args.output_artwork)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas)

    # 标注坐标变换：canvas 尺寸、region、protectedRegions、handPath
    sx, sy = scale, scale
    cw, ch = ann["canvas"]["width"], ann["canvas"]["height"]
    # 若标注画布与线稿像素一致则 scale 即可；不一致时按画布比例换算
    sx = nw / cw if cw != w0 else scale
    sy = nh / ch if ch != h0 else scale

    ann["canvas"]["width"] = tw
    ann["canvas"]["height"] = th
    for el in ann.get("elements", []):
        if "region" in el:
            el["region"] = scale_rect(el["region"], sx, sy, dx, dy)
        reveal = el.get("reveal", {})
        if "protectedRegions" in reveal:
            reveal["protectedRegions"] = [
                scale_rect(r, sx, sy, dx, dy) for r in reveal["protectedRegions"]]
        hp = el.get("handPath")
        if hp:
            if "start" in hp:
                hp["start"] = scale_pt(hp["start"], sx, sy, dx, dy)
            if "end" in hp:
                hp["end"] = scale_pt(hp["end"], sx, sy, dx, dy)

    Path(args.output_annotation).write_text(
        json.dumps(ann, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"HD 适配: {w0}x{h0} -> {tw}x{th} (scale {scale:.4f}, offset {dx},{dy}, bg BGR {bg})")
    print(f"  线稿: {out}")
    print(f"  标注: {args.output_annotation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
