# 标注 JSON Schema

`srt-whiteboard-animation` 的标注文件格式，`auto_annotate.py` 自动生成、也可手动编辑。

## 顶层结构

```json
{
  "sceneId": "scene-01",
  "canvas": {"width": 1216, "height": 832},
  "storyBasis": "故事/口播内容概述",
  "sceneDurationMs": 26564,
  "elements": [...]
}
```

## elements 数组

每个元素对应一句字幕/一个叙事节点：

```json
{
  "id": "el-01",
  "label": "白板与手绘笔",
  "sequence": 1,
  "narrativeRole": "场景铺垫：点明主题",
  "subtitle": "对应字幕文本",
  "type": "structure",
  "region": {
    "x": 60,
    "y": 296,
    "width": 250,
    "height": 220
  },
  "reveal": {
    "direction": "top_to_bottom",
    "startMs": 330,
    "durationMs": 3572,
    "maskPaddingPx": 18,
    "protectedRegions": []
  },
  "handPath": {
    "start": [185, 305],
    "end": [185, 500],
    "easing": "easeInOut"
  }
}
```

## 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 元素唯一标识 |
| `label` | string | 人类可读标签 |
| `sequence` | int | 揭示顺序（1 开始） |
| `narrativeRole` | string | 叙事作用描述 |
| `subtitle` | string | 对应字幕文本 |
| `type` | string | 元素类型（`structure`） |
| `region.x/y/width/height` | int | 元素在画布上的矩形区域（像素坐标） |
| `reveal.direction` | string | 揭示方向：`left_to_right` / `top_to_bottom` / `right_to_left` / `bottom_to_top` |
| `reveal.startMs` | int | 揭示开始时间（ms），通常 = 配音起点 - 70（笔先动） |
| `reveal.durationMs` | int | 揭示持续时间（ms），= 下一元素 startMs - 本元素 startMs |
| `reveal.maskPaddingPx` | int | 掩码内边距，控制揭示边缘柔和度（默认 18） |
| `reveal.protectedRegions` | array | 不被提前揭示的区域列表（默认空） |
| `handPath.start` | [x, y] | 笔尖起点坐标 |
| `handPath.end` | [x, y] | 笔尖终点坐标 |
| `handPath.easing` | string | 缓动函数（`easeInOut`） |

## 时序计算公式

```
reveal.startMs[i] = vo_start[i] - hand_lead   (hand_lead = 70ms)
reveal.durationMs[i] = reveal.startMs[i+1] - reveal.startMs[i]   (中间元素)
reveal.durationMs[last] = sceneDurationMs - reveal.startMs[last]
sceneDurationMs = vo_start[last] + vo_dur[last] + tail_ms   (tail_ms = 700)
```

## 区域坐标原则

- 坐标基于线稿原始像素尺寸
- 区域之间允许重叠（后揭示的区域会覆盖先揭示的区域）
- 但 `auto_annotate.py` 的连通域分析会尽量取互不重叠的区域
- 如果手动调整，确保每个区域 `region` 内有实际线条内容（非背景像素 > 1%）
