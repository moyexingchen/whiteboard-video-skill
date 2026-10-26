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
import webbrowser
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets"
PREVIEW_HTML = ASSETS / "preview.html"


def script_json(value):
    """JSON safe inside an HTML script element (including filenames/subtitles)."""
    return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


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
        else:
            # Python handles platform browser discovery without cmd.exe/shell quoting.
            if browser == "default":
                return webbrowser.open(url)
            return webbrowser.get({"chrome": "google-chrome", "edge": "microsoft-edge"}[browser]).open(url)
        return True
    except Exception:
        return False


def generate_preview_html(artwork_path: Path, annotation_path: Path, output_path: Path):
    """生成自带数据的预览 HTML：线稿 base64 内联 + 标注 JSON 内联，打开即载入。"""
    html = PREVIEW_HTML.read_text(encoding="utf-8")

    # Embed the hand too: output can live anywhere and works offline.
    hand_b64 = base64.b64encode((ASSETS / "drawing-hand.png").read_bytes()).decode("ascii")
    html = html.replace("./drawing-hand.png", "data:image/png;base64," + hand_b64)

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
  const imgB64 = {script_json(img_b64)};
  const cfg = {script_json(cfg_obj)};

  const imgUrl = "data:image/png;base64," + imgB64;
  const scene = {{
    name: {script_json(art_name)},
    imgName: {script_json(art_name + ".png")},
    cfgName: {script_json(anno_name)},
    cfg: cfg,
    cfgHandle: null,
    imgUrl: imgUrl,
    hasConfig: true
  }};

  S.scenes = [scene];
  S.dirty.clear();

  const sel = $('sceneSel');
  sel.replaceChildren(new Option('1. ' + scene.name, '0'));
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
    if "</body>" not in html:
        raise ValueError("预览模板缺少 </body>")
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
    p.add_argument("--no-open", action="store_true", help="只生成 HTML，不启动浏览器")
    args = p.parse_args()

    for resource in (PREVIEW_HTML, ASSETS / "drawing-hand.png"):
        if not resource.is_file():
            print(f"[err] 预览资源不存在: {resource}", file=sys.stderr)
            print("  请重新克隆完整仓库，确保 assets/ 中包含模板和手部图片", file=sys.stderr)
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
    try:
        generate_preview_html(artwork, annotation, output_html)
    except (OSError, ValueError) as exc:
        print(f"[err] 生成预览失败: {exc}", file=sys.stderr)
        return 1

    # 用浏览器打开
    url = output_html.resolve().as_uri()
    opened = False
    if not args.no_open:
        opened = open_url(url, args.browser)
        if not opened and args.browser != "default":
            print(f"[warn] 无法用 {args.browser} 打开，回退默认浏览器", file=sys.stderr)
            opened = open_url(url, "default")
        if not opened:
            print(f"[warn] 浏览器未打开，请手动打开: {url}", file=sys.stderr)

    print("=" * 56)
    print("浏览器预览台已打开" if opened else "预览 HTML 已生成（待手动打开）")
    print(f"  预览: {url}")
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
