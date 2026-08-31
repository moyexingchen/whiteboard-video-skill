# 工作流设计细节

本文是 [README](../README.md) 快速开始的深化版：每一步的设计取舍、时序公式、以及为什么这样做。

## 总体设计

整条管线只维护一个权威时间源：`timing.json`。配音时长、字幕起止、画笔揭示时刻全部由它派生，因此音画天然同步，不需要任何对齐步骤。

```
timing.json（唯一时间源）
  ├─ master.srt      字幕起止 = 各句配音起止
  ├─ annotation.json reveal.startMs = 配音起点 - 70ms
  ├─ 混音            adelay = 各句起点
  └─ 合成长度        total_ms
```

## 第 1 步：gen_vo_srt.py

### 为什么逐句配音而不是整段配音

1. **时长必须实测**。edge-tts 输出时长不固定，估算的时长会让字幕和配音漂移。逐句生成后用 ffprobe 测每句 MP3 的真实时长，精确到毫秒。
2. **时间轴由真实时长累加得出**，每句的 `start_ms` 是前面所有句子的实测长度之和加间隔，不是任何理论值。
3. 一句一个文件还方便重配某一句——改错一句不用整段重来。

### 时间轴常量

| 常量 | 默认值 | 作用 |
|------|--------|------|
| `initial_silence` | 400ms | 开头静音，给片头一点呼吸 |
| `gap` | 20ms | 句间间隔，几乎无缝但有微喘息 |
| `tail` | 700ms | 末尾画面停留，避免戛然而止 |

### timing.json 格式

```json
{
  "voice": "zh-CN-YunxiNeural",
  "rate": "+0%",
  "pitch": "+0Hz",
  "initial_silence_ms": 400,
  "gap_ms": 20,
  "tail_ms": 700,
  "total_ms": 25864,
  "lines": [
    {"index": 1, "text": "...", "duration_ms": 3552, "start_ms": 400, "file": "vo/line01.mp3"}
  ]
}
```

## 第 2 步：线稿的构图要求

线稿本质是「一页被切分成 N 个区域的画」，每个区域对应一句台词。构图要求都为这个服务：

- **元素数量 = 句数**：多余元素不会被揭示（观众看不到），缺元素会有台词无画可画
- **横向流程排列**：符合「按 y 分带 + 带内按 x」的默认揭示顺序，也是人眼自然阅读顺序
- **无文字**：字幕由第 6 步统一烧录，画面自带文字会和字幕穿帮
- **大量留白**：连通域分析需要元素之间有清晰间隔，元素贴在一起会被识别成一个连通域

线稿来源不限：AI 生图（注意水印）、手绘扫描（注意背景均匀度）、矢量工具导出。`auto_annotate.py` 的背景色取四角均值自适应，所以只要背景大致均匀就能工作。

## 第 3 步：auto_annotate.py 的分析逻辑与失效条件

```
背景色 = 四角 8px 均值
线条像素 = |像素 - 背景| > diff_threshold (55)
掩码 = 5×5 膨胀 1 次 → 连通域 → 过滤面积 < 300
排序 = 按画布高度 1/3 分带，带内按 x 从左到右
取前 N 个（N = 句数）
```

### 已知失效模式

1. **阈值 55 抓不到浅色元素**：色差低于 55 的线条被当背景。解法：调低 `--diff-threshold`。
2. **元素内部笔画被拆碎**：虚线、断笔风格的线稿，一个元素被拆成多个连通域，排前面的都是碎块，后面的元素分不到。解法：调低阈值让碎块连通，或直接手动写 annotation.json。
3. **元素粘连**：两个元素贴太近被识别为一块。解法：手动改 region 拆开。

多元素网格布局（如 5×3）建议流程：先跑 `render_annotation_preview.py` 出静态图检查；若错位，用图像工具读出每个图标的真实中心坐标，手写标注。

### 时序公式

```
reveal.startMs[i]   = vo_start[i] - hand_lead     (hand_lead = 70ms)
reveal.durationMs[i] = reveal.startMs[i+1] - reveal.startMs[i]
reveal.durationMs[last] = sceneDurationMs - reveal.startMs[last]
sceneDurationMs = vo_start[last] + vo_dur[last] + tail_ms
```

**笔尖提前 70ms 的原因**：人对声音的感知比视觉快，如果画和声音严格同时出现，主观感受是画面慢了半拍。让笔先落 70ms，听感上正好同步。

## 第 4 步：预览台为什么是强制关卡

渲染 60fps 全片是整条管线最耗时的一步，标错一个区域就要整个重来。预览台在渲染前用静态线稿 + 标注直接回放揭示效果，把校验成本从分钟级降到秒级。

预览 HTML 由 `open_preview.py` 生成，线稿和标注全部 base64 内联，打开即载入，无需起本地服务器。保存走浏览器下载。

## 第 5 步：渲染

`render_stream_whiteboard.py`（来自 srt-whiteboard-animation）逐帧绘制：

- 每个元素在自己的 `region` 掩码内流式落墨（先 ink 铺线，再 color 添彩）
- 笔尖沿 `handPath` 从 start 移到 end，带缓动
- `--cap-long-edge 1920` 控制输出分辨率，不加会按 1080 缩放
- 末行打印 `OUTPUT=<路径>` 便于脚本化

## 第 6 步：mix_burn.py

1. **混音**：`ffmpeg adelay+amix`，各句按 timing.json 起点延迟后混合，`normalize=0` 不自动归一化（保留原始响度关系）
2. **烧字幕**：PIL 逐帧绘制，白字黑边（`stroke_width=3`），CJK 字体自动探测（环境变量 `SRT_WB_FONT` 可手动指定），字号随视频高度自适应
3. **合并**：`ffmpeg -c:v copy -c:a aac -t total_ms`，视频比音频长时补静音（apad）

用 PIL 而不用 ffmpeg 的 `subtitles` 滤镜，是因为很多系统 ffmpeg 编译时没带 `libass`/`freetype`，PIL 方案零额外依赖且渲染效果可控。
