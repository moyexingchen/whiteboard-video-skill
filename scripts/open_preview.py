#!/usr/bin/env python3
"""打开浏览器预览台 — 自动载入线稿+标注，打开即见效果、可直接播放

生成一个自带数据的预览 HTML（线稿以 base64 内联、标注 JSON 内联），
打开浏览器即刻载入，无需手动选文件夹。用户可直接播放、调整、保存。

用法:
  python open_preview.py --artwork <线稿.png> --annotation <标注.json>
  # 可选 --browser chrome|edge|default（默认 chrome，回退 default）
"""
import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

PREVIEW_HTML = Path.home() / ".workbuddy/skills/srt-whiteboard-animation/assets/preview.html"


def open_url(url: str, browser: str) -> bool:
    """尝试用指定浏览器打开 URL，成功返回 True。"""
    try:
        if sys.platform == "darwin":
            if browser == "chrome":
                subprocess.run(["open", "-a", "Google Chrome", url], check=True)
            elif browser == "edge":
                subprocess.run(["open", "-a", "Microsoft Edge", url], check=True)
            else:
                subprocess.run(["open", url], check=True)
        elif sys.platform == "win32":
            exe = {"chrome": "chrome", "edge": "msedge"}.get(browser)
            subprocess.run(["start", exe or "", url], shell=True, check=True)
        else:
            subprocess.run(["xdg-open", url], check=True)
        return True
    except Exception:
        return False


def generate_preview_html(artwork_path: Path, annotation_path: Path, output_path: Path):
    """生成自带数据的预览 HTML：线稿 base64 内联 + 标注 JSON 内联，打开即载入。"""
    html = PREVIEW_HTML.read_text(encoding="utf-8")

    # 读取线稿 → base64
    with open(artwork_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("ascii")

    # 读取标注 JSON → Python dict → 重新序列化为 JS 安全的 JSON
    with open(annotation_path, "r", encoding="utf-8") as f:
        cfg_obj = json.load(f)

    art_name = artwork_path.stem
    anno_name = annotation_path.name

    # 注入到 </body> 前的自动载入脚本
    # 使用 IIFE 在 preview.html 自身脚本之后执行，直接填充 S.scenes 并调用 loadScene(0)
    auto_load = f"""
<script>
// === 自动载入线稿+标注（无需手动选文件夹）===
(function() {{
  const imgB64 = {json.dumps(img_b64)};
  const cfg = {json.dumps(cfg_obj, ensure_ascii=False)};

  const imgUrl = "data:image/png;base64," + imgB64;
  const scene = {{
    name: {json.dumps(art_name)},
    imgName: {json.dumps(art_name + ".png")},
    cfgName: {json.dumps(anno_name)},
    cfg: cfg,
    cfgHandle: null,
    imgUrl: imgUrl,
    hasConfig: true
  }};

  S.scenes = [scene];
  S.dirty.clear();

  const sel = $('sceneSel');
  sel.innerHTML = '<option value="0">1. ' + scene.name + '</option>';
  sel.disabled = $('prevBtn').disabled = $('nextBtn').disabled = false;
  $('sceneCount').textContent = '共 1 张（1 张带标注）';
  $('hint').hidden = true;
  canvas.hidden = false;
  $('side').hidden = false;
  $('playBtn').disabled = $('timeline').disabled = false;

  loadScene(0);
}})();
</script>
"""
    html = html.replace("</body>", auto_load + "\n</body>")
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main():
    p = argparse.ArgumentParser(description="打开浏览器预览台（自动载入线稿+标注）")
    p.add_argument("--artwork", required=True,
                   help="线稿 PNG 路径（已 make_hd 适配的 HD 版）")
    p.add_argument("--annotation", required=True,
                   help="标注 JSON 路径（已 make_hd 适配的 HD 版）")
    p.add_argument("--browser", default="chrome",
                   choices=["chrome", "edge", "default"],
                   help="浏览器：chrome（默认）/ edge / default")
    args = p.parse_args()

    if not PREVIEW_HTML.exists():
        print(f"[err] 预览台模板不存在: {PREVIEW_HTML}", file=sys.stderr)
        print("  请确认 srt-whiteboard-animation skill 已安装", file=sys.stderr)
        return 1

    artwork = Path(args.artwork).resolve()
    annotation = Path(args.annotation).resolve()

    if not artwork.exists():
        print(f"[err] 线稿文件不存在: {artwork}", file=sys.stderr)
        return 1
    if not annotation.exists():
        print(f"[err] 标注文件不存在: {annotation}", file=sys.stderr)
        return 1

    # 生成自带数据的预览 HTML
    output_html = artwork.parent / f"preview-{artwork.stem}.html"
    generate_preview_html(artwork, annotation, output_html)

    # 用浏览器打开
    url = output_html.resolve().as_uri()
    if not open_url(url, args.browser):
        print(f"[warn] 无法用 {args.browser} 打开，回退默认浏览器", file=sys.stderr)
        open_url(url, "default")

    print("=" * 56)
    print("浏览器预览台已打开（已自动载入线稿+标注）")
    print("=" * 56)
    print(f"  线稿: {artwork}")
    print(f"  标注: {annotation}")
    print()
    print("可直接操作：")
    print("  - 点 ▶ 或拖时间轴查看揭示动画效果")
    print("  - 拖区域四边/四角调整 region；右侧改名称/方向/时间/字幕")
    print("  - 拖动模块列表调整 sequence 顺序")
    print("  - 点「保存本场景」下载更新后的 JSON")
    print(f"    （下载后请移动到: {annotation}）")
    print("  - 确认无误后，回到对话中说「确认」即可继续渲染")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
