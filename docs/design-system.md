# 界面设计系统（与网站同一套视觉语言）

桌面应用的界面风格与 [inception.work](https://inception.work) 保持一致：**像素字体、
直角、2px 实心描边、深色石头底 + 草方块绿强调 + 亮黄 hover**。
颜色与尺寸全部来自 `app/ui/design/`，界面代码里**不写死色值**。

## 1. 架构（四层，单向依赖）

```
tokens.py      调色板 --mc-core-* + 语义主题 --bk-* + 尺寸约定
    ↓
fonts.py       像素字体（Fusion Pixel）注册与回退
    ↓
qss.py         由令牌生成全局 QSS（Qt 样式表）
    ↓
theme.py       ThemeManager：装到 QApplication、切主题、发变更信号
    ↓
components.py  组件助手（卡片 / 分区标题 / 状态标签 / 各类按钮）
```

**为什么用 QSS 而不是逐控件调色板**：Qt 的默认外观在 Windows / macOS 上不同，
用系统调色板拼出来的界面换台机器就变样；QSS 一把梭，两端一致，而且能精确复刻
网站的形态。`ThemeManager` 同时会同步一份 `QPalette`，让自绘控件与原生弹窗也跟着走。

## 2. 令牌

调色板（组件库 `mcpixel-craft-ui` 的 `--mc-core-*`，原样搬运）：

| 名称 | 值 | 名称 | 值 |
|---|---|---|---|
| green-6 | `#2a641c` | grey-6 | `#262423` |
| green-5 | `#3c8527` | grey-5 | `#3d3938` |
| green-4 | `#52a535` | grey-4 | `#6b6562` |
| green-3 | `#6cc349` | grey-3 | `#aba09c` |
| green-2 | `#86d562` | grey-2 | `#d0c5c0` |
| green-1 | `#a0e081` | grey-1 | `#ede5e2` |
| off-black | `#171615` | off-white | `#fcf5f1` |

语义主题（网站后台的 `--bk-*`）：深色是默认，浅色一套覆盖。

| 语义 | 深色 | 浅色 |
|---|---|---|
| 页面底 | `#171615` | `#ede5e2` |
| 侧栏 / 弹窗 | `#262423` | `#fcf5f1` |
| 表面（浮层） | `rgba(255,255,255,.04/.07/.12)` | `rgba(38,36,35,.04/.07/.12)` |
| 描边 | `#3d3938` | `#d0c5c0` |
| 文字 1/2/3/4 | `#fcf5f1` / `#d0c5c0` / `#aba09c` / `#6b6562` | `#262423` / `#3d3938` / `#6b6562` / `#aba09c` |
| 强调 / 强强调 | `#52a535` / `#3c8527` | `#3c8527` / `#2a641c` |
| hover | `#fffc70` | `#8a6d00` |

尺寸：控件高 32px、描边 2px、**圆角 0**、正文 12px / 控件 13px、标题 17px；
按钮档 large 258×48、medium 129×32、small 43×24。

## 3. 按钮的四种外观（照搬组件库 McPixelButton）

| variant | 外观 | 用在哪 |
|---|---|---|
| 默认（general） | 浅灰竖直渐变 + 蓝框（`#002fae`） | 普通动作（浏览…、打开目录） |
| `primary` | 蓝色竖直渐变 | 组件库的 primary |
| `secondary` | 草绿竖直渐变（`#6cc349→#52a535→#3c8527`）+ 深绿框 | **主操作**（网站首页 CTA 用的就是这个） |
| `danger` | 橙色竖直渐变 | 危险动作（删除、清理） |
| `ghost` | 透明 + 细描边 | 次要动作 |

悬停时换成亮色填充 + 深色文字（组件库的 hover 行为）。`components.primary_button()`
给的是草绿那套（界面语义上的"主要动作"）。

## 4. 字体

像素字体 **Fusion Pixel**（SIL OFL 1.1，`app/resources/fonts/` 随包分发）：
`fusion-pixel-12px-monospaced-zh_hans.ttf` + `...-latin.ttf`。

`fonts.py` 的查找顺序：`LTGEN_FONT_DIR` → `app/resources/fonts/` →
组件库的 `dist/fonts/`；都没有就退回系统字体栈（PingFang SC / 微软雅黑 / 等宽），
界面仍然可用，只是不是像素风。

## 5. 界面里怎么写

```python
from app.ui import design

design.install(app, config.ui_theme)      # 启动时一次（app/__main__.py 已接）

design.title("要做什么？")                 # 标题
design.hint("说明文字")                    # 次要说明（role="hint"）
design.primary_button("导出")              # 主操作（草绿）
design.general_button("浏览…")             # 普通操作（浅灰）
design.danger_button("删除")               # 危险操作（橙）
design.set_role(label, "ok")               # 语义色：ok / warn / error / hint / dim
design.set_variant(button, "ghost")        # 需要时手工指定变体
card, layout = design.card()               # 卡片容器（2px 描边 + 面）

t = design.theme()                         # 自绘控件取语义色
painter.setBrush(QColor(t.accent))
```

自定义绘制（区块状态格子、容量条）在 `paintEvent` 里取 `design.theme()`，
所以切主题会立刻跟着变；`ThemeManager` 切换时会重绘所有控件。

## 5.1 分组标题、动效与弹窗按钮

- **分组标题（QGroupBox）不能贴着框线**：Qt 把边框画在"内容矩形"上，
  `margin-top` 那条空白就是标题的地盘，标题的 `top` 只能在这条带子里微调——
  负值会顶出控件被裁掉一半（踩过）。现值：`margin-top: 22px`、`top: 4px`。
- **动效只做"让人看懂发生了什么"**（`app/ui/design/motion.py`）：窗口/对话框淡入、
  容量条从 0 长到实际比例、项目卡片依次淡入。离屏（自检与截图）与
  `LTR_NO_MOTION=1` 一律不动画——截图要的是确定的静止画面。
- **标准弹窗按钮说中文**：装一个应用级过滤器（`components.ButtonTextFilter`），
  不依赖发行版自带的 Qt 翻译包；文案走 `i18n.tr()`，所以英文界面下就是 OK / Cancel。

## 6. 深浅色

主题名 `"dark"`（默认）与 `"light"`，用户的选择存在 `AppConfig.ui_theme`；
菜单「视图 → 切换到浅色/深色主题」可切换，切换后立即生效并落盘。

## 7. 自检

```sh
QT_QPA_PLATFORM=offscreen python tests/render_theme_check.py <输出目录>
```

会各出一张深浅色的主界面 / 导出对话框 / 项目界面 PNG，人工核对配色与排版。
