# LaTeX Formula Cloud Generator

用 Python 生成“公式词云”：输入 LaTex 公式和/或公式图片，输出一张自动排布的公式云图片。

## 功能
- 支持输入 `latex` 字段（通过 matplotlib 渲染公式）
- 支持输入 `image` 字段（直接使用已有公式图片）
- 支持 `weight` 权重，权重越大显示越大
- 螺旋搜索排版，尽量避免重叠
- 支持随机旋转角度（横向/纵向/斜向）
- 支持每个公式重复出现（`repeat`）
- 公式显示数量与权重成反比（权重越小出现次数越多）
- 支持云形状约束（`rectangle`/`square`/`circle`/`diamond`）

## 安装依赖
```bash
pip install matplotlib pillow numpy
```

## 输入格式
使用 JSON 数组，每一项需要包含 `weight`，并在 `latex` 与 `image` 二选一。

示例：
```json
[
  {"latex": "E=mc^2", "weight": 10, "fontsize": 48, "repeat": 2},
  {"latex": "\\int_a^b f(x)dx", "weight": 8},
  {"image": "./formula1.png", "weight": 6}
]
```

字段说明：
- `latex`: LaTeX 字符串（不需要手动加 `$...$`）
- `image`: 公式图片路径（建议透明背景）
- `weight`: 大小权重（浮点或整数）
- `fontsize`: 仅对 `latex` 生效，可选
- `color`: 仅对 `latex` 生效，可选
- `repeat`: 同一公式重复次数，可选，默认 1

## 运行
```bash
python formula_cloud.py --input sample_formulas.json --output formula_cloud.png --width 1920 --height 1080 --shape circle --angles 0,45,90,135
```

## 输出
输出一张 PNG 图片（默认 `formula_cloud.png`）。


参数补充：
- `--shape`: 云形状，可选 `rectangle`、`square`、`circle`、`diamond`
- `--angles`: 允许的旋转角度（度数，逗号分隔），如 `0,90` 表示仅横竖排
