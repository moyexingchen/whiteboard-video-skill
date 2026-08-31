---
name: whiteboard-video-skill
description: "将一段口播稿自动转化为 1920×1080 高清横屏白板手绘动画成片的生产线。串联 edge-tts（配音）、线稿连通域标注、高清画布适配、浏览器预览确认、流式笔迹渲染、PIL 字幕烧录，从文本到成片一条龙。当用户说「给这段文字做个视频」「口播稿转动画」「把这个文案做成白板动画」时触发。输入一段中文口播文本，输出带配音和字幕的白板手绘动画 MP4。"
---

# Whiteboard Video Skill

## 概述

把一段口播稿自动转化为**高清横屏（1920×1080，16:9）**白板手绘动画成片。六个阶段串行：

1. **edge-tts** — 文本切句 → 逐句 TTS → 测真实时长 → 生成 SRT + timing.json
2. **线稿生成** — 出一张暖米黄底深灰线条的手绘插画，元素数 = 句数
3. **自动标注 + 高清画布适配** — 连通域分析框出元素，等比缩放到 1920×1080
4. **浏览器预览确认**（强制关卡）— 预览台直观调整区域 / 顺序 / 时序，用户确认后才渲染
5. **渲染白板动画** — 流式笔迹绘制 60fps 底版
6. **混音 + 字幕烧录 + 合成** — 最终成片

## 路径约定

本 skill 的脚本位于本仓库 `scripts/` 目录（下文以 `$SKILL` 指代本 SKILL.md 所在目录）。渲染引擎在 `$SKILL/scripts/render/`。

```bash
SKILL=<本仓库根目录>          # scripts/ 与 SKILL.md 所在目录
PY=<含依赖的 python>          # 安装了 edge-tts、opencv-python、Pillow 的解释器
```

前置依赖：`edge-tts`、`opencv-python`、`Pillow`、`numpy`（`pip install -r $SKILL/requirements.txt`）、系统 `ffmpeg` + `ffprobe`。

环境变量：`SRT_WB_FONT` 可选，手动指定 CJK 字体路径（默认自动探测）。

## 工作流

### 第 1 步：口播稿 → 配音 + SRT

```bash
$PY $SKILL/scripts/gen_vo_srt.py \
  --text "口播稿全文。" --outdir <project>/edit/pipeline
# 或 --text-file script.txt
```

输出 `vo/lineNN.mp3`、`master.srt`、`timing.json`。关键设计见 `docs/workflow.md`：开头 400ms 静音、句间 20ms、末尾 700ms；**必须 ffprobe 实测时长**。可选 `--voice`（默认 `zh-CN-YunxiNeural`）、`--rate`、`--pitch`。

### 第 2 步：生成线稿

用可用的图像生成工具出一张极简手绘插画：

- 风格：极简手绘素描、Notion 涂鸦美学；底色暖米黄 `#F5EBD7`；深灰线条，红 / 橙 / 蓝点缀
- 构图：横向流程图，元素从左到右排列，大量留白，符合 16:9 宽幅
- **元素数量 = 口播稿句数**；**绝对禁止文字、字母、数字、水印**
- 尺寸优先 `1920x1080`

生成后重命名为 `<project>/assets/scene-01.png`，查看图片确认无水印无文字。

### 第 3 步：自动标注 + 画布适配

```bash
$PY $SKILL/scripts/auto_annotate.py \
  --artwork <project>/assets/scene-01.png \
  --timing <project>/edit/pipeline/timing.json \
  --output <project>/assets/scene-01.annotation.json

$PY $SKILL/scripts/make_hd.py \
  --artwork <project>/assets/scene-01.png \
  --annotation <project>/assets/scene-01.annotation.json \
  --output-artwork <project>/assets/scene-01.hd.png \
  --output-annotation <project>/assets/scene-01.hd.annotation.json

# 静态预览验证标注
$PY $SKILL/scripts/render/render_annotation_preview.py \
  <project>/assets/scene-01.hd.png \
  <project>/assets/scene-01.hd.annotation.json \
  <project>/assets/preview.png
```

查看 preview.png 确认区域框贴合元素。**不贴合是常态**（元素笔画拆碎 / 色差低于阈值），此时手动编辑 annotation.json 的 region 坐标，格式见 `docs/annotation-schema.md`。

### 第 4 步：浏览器预览台确认（强制关卡）

```bash
$PY $SKILL/scripts/open_preview.py \
  --artwork <project>/assets/scene-01.hd.png \
  --annotation <project>/assets/scene-01.hd.annotation.json
```

**执行规则（强制）：**
- 告知用户：浏览器已自动载入线稿 + 标注，点 ▶ 查看揭示效果；拖区域四边/四角改 region；右侧面板改名称 / 方向 / 起止毫秒；拖模块列表调顺序；点「保存本场景」下载更新后的 `.annotation.json`，移动到原标注路径覆盖；确认后回到对话说「确认」
- **必须等用户明确说「确认」后才可进入渲染。** 不得把「未回复」「笼统授权」「用户没反对」视为确认
- 用户要求修改标注时，只改标注并保存后再次等待确认
- 渲染使用保存后的最新 `.annotation.json`，无需重跑 make_hd

### 第 5 步：渲染白板动画

```bash
$PY $SKILL/scripts/render/render_stream_whiteboard.py \
  <project>/assets/scene-01.hd.png \
  <project>/assets/scene-01.hd.annotation.json \
  <project>/edit/pipeline/base.mp4 \
  --cap-long-edge 1920
```

**必须加 `--cap-long-edge 1920`**，否则输出不是高清横屏。输出 1920×1080、60fps。

### 第 6 步：合成最终成片

```bash
$PY $SKILL/scripts/mix_burn.py \
  --video <project>/edit/pipeline/base.mp4 \
  --vo-dir <project>/edit/pipeline/vo \
  --srt <project>/edit/pipeline/master.srt \
  --timing <project>/edit/pipeline/timing.json \
  --output <project>/edit/pipeline/final.mp4
```

字幕字号 / 边距按视频高度自适应（1080p 约 48px / 59px），可 `--font-size 52 --margin-v 70` 覆盖。输出 final.mp4，用 `present_files`（或对应渠道）呈现给用户。

## 常见坑速查

| 问题 | 解法 |
|------|------|
| 自动标注错位 | 渲染静态预览图检查；手改 annotation.json；多元素网格布局先反推真实坐标 |
| OpenCV 写 MP4 空文件 | 脚本已自动回退 avc1 编码器 |
| ffmpeg 无 libass | 本管线用 PIL 逐帧烧录，不走 ffmpeg 字幕滤镜 |
| ImageGen 等生图带水印 | 生成后检查，修掉再进管线（用真实底色修补，不要纯色块） |
| edge-tts 限流 | 重试或换 `--voice` |
| 成品不是 1920×1080 | 渲染加 `--cap-long-edge 1920`；线稿优先 1920×1080 |
| 预览台保存后找不到文件 | 在浏览器下载目录，文件名 `<名称>.annotation.json`，移回原路径覆盖 |
| 跳过预览直接渲染 | 第 4 步是强制关卡，必须等用户明确确认 |

## 示例工程

`examples/手绘视频生产线/` 有完整示例：15 句口播稿 → 68 秒成片，含线稿、标注、timing、字幕与成片，可用来验证环境。
