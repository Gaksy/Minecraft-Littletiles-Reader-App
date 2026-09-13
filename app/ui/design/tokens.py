"""设计令牌：与网站（mcpixel-craft-ui / inception.work 后台）逐值对应。

**这里是唯一的颜色与尺寸来源**，界面代码里不要写死色值。令牌分三层：

1. `Palette`  —— 组件库调色板 `--mc-core-*` 的原样搬运；
2. `Theme`    —— 语义主题（网站后台的 `--bk-*` 那套），深色为默认、浅色一套覆盖；
3. `Metrics`  —— 尺寸约定（控件高度 32px、**直角**、2px 描边、字号档位）。

风格要点（照搬网站）：像素字体、直角、2px 实心描边、深色石头底 + 草方块绿强调 +
亮黄 hover。改动这里就等于改整个界面的风格。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Palette:
    """组件库调色板 `--mc-core-*`（mcpixel-craft-ui/src/assets/theme/…-color.css）。"""

    green_6: str = "#2a641c"
    green_5: str = "#3c8527"
    green_4: str = "#52a535"
    green_3: str = "#6cc349"
    green_2: str = "#86d562"
    green_1: str = "#a0e081"

    grey_6: str = "#262423"
    grey_5: str = "#3d3938"
    grey_4: str = "#6b6562"
    grey_3: str = "#aba09c"
    grey_2: str = "#d0c5c0"
    grey_1: str = "#ede5e2"

    off_black: str = "#171615"
    off_white: str = "#fcf5f1"
    white: str = "#ffffff"
    black: str = "#000000"

    # 语义色（组件库其它调色板里挑出来、网站后台用到的那几个）
    focus: str = "#1157be"
    caution: str = "#e2b923"
    warning: str = "#ca3636"
    warning_2: str = "#ff605e"
    orange_4: str = "#ffa41f"
    orange_6: str = "#de5b0d"
    red_4: str = "#da3a16"
    red_6: str = "#8f1f0b"
    blue_4: str = "#1e6eea"
    blue_2: str = "#6cb1d6"
    blue_6: str = "#2f6f9a"
    yellow: str = "#fffc70"


PALETTE = Palette()


@dataclass(frozen=True)
class Theme:
    """语义主题。字段名与网站后台的 `--bk-*` 一一对应。

    深色为默认（网站后台也是），浅色覆盖成另一套值。界面里只用这些字段。
    """

    name: str
    is_dark: bool

    # 底与面
    page: str
    header: str
    sidebar: str
    modal: str
    surface: str
    surface_2: str
    surface_3: str

    # 描边
    border: str
    border_soft: str

    # 文字（1 最亮 → 4 最暗）
    text_1: str
    text_2: str
    text_3: str
    text_4: str

    # 强调与状态
    accent: str
    accent_strong: str
    hover: str
    link: str
    ok: str
    ok_bg: str
    info: str
    info_bg: str
    amber: str
    amber_bg: str
    danger: str
    danger_bg: str

    # 强调底上的文字（绿底用深色字，避免对比度不足）
    on_accent: str
    # 选中/悬停时浮层的投影（网站用 2px 硬边阴影，不用模糊）
    focus_shadow: str = ""

    # ---- 组件库按钮的四种外观（mcpixel-craft-ui 的 McPixelButton 变体）----
    #
    # 网站首页的主 CTA 用的是 secondary（草绿渐变）；general 是默认的浅灰像素按钮；
    # primary 是蓝色渐变；danger 是橙色。Qt 里用 qlineargradient 还原同样的竖直渐变。
    button_general_bg: str = (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        " stop:0 #fcf5f1, stop:0.5 #ede5e2, stop:1 #d0c5c0)"
    )
    button_general_border: str = "#002fae"      # --mc-vanilla-blue-6
    button_general_text: str = "#262423"        # grey-6
    button_general_hover_bg: str = "#ede5e2"    # grey-1

    button_primary_bg: str = (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        " stop:0 #3a87f4, stop:0.5 #1e6eea, stop:1 #0855db)"
    )
    button_primary_hover_bg: str = "#5b9ffb"    # --mc-vanilla-blue-1

    button_secondary_bg: str = (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        " stop:0 #6cc349, stop:0.5 #52a535, stop:1 #3c8527)"
    )
    button_secondary_border: str = "#2a641c"    # green-6
    button_secondary_text: str = "#3d3938"      # grey-5
    button_secondary_hover_bg: str = "#86d562"  # green-2

    button_danger_bg: str = (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        " stop:0 #ffa41f, stop:0.5 #ff791a, stop:1 #de5b0d)"
    )
    button_danger_border: str = "#de5b0d"       # --mc-dungeons-orange-6
    button_danger_hover_bg: str = "#fff27a"     # --mc-dungeons-orange-1
    # 悬停时的文字色（组件库用 legends-dark-blue-6，深色字更清楚）
    button_hover_text: str = "#001236"


DARK = Theme(
    name="dark",
    is_dark=True,
    page=PALETTE.off_black,
    header="rgba(23, 22, 21, 0.92)",
    sidebar=PALETTE.grey_6,
    modal=PALETTE.grey_6,
    surface="rgba(255, 255, 255, 0.04)",
    surface_2="rgba(255, 255, 255, 0.07)",
    surface_3="rgba(255, 255, 255, 0.12)",
    border=PALETTE.grey_5,
    border_soft="rgba(255, 255, 255, 0.08)",
    text_1=PALETTE.off_white,
    text_2=PALETTE.grey_2,
    text_3=PALETTE.grey_3,
    text_4=PALETTE.grey_4,
    accent=PALETTE.green_4,
    accent_strong=PALETTE.green_5,
    hover=PALETTE.yellow,
    link=PALETTE.green_2,
    ok=PALETTE.green_2,
    ok_bg="rgba(82, 165, 53, 0.16)",
    info=PALETTE.blue_2,
    info_bg="rgba(74, 159, 212, 0.16)",
    amber="#f5c677",
    amber_bg="rgba(217, 119, 47, 0.18)",
    danger="#ff8a7a",
    danger_bg="rgba(181, 69, 58, 0.2)",
    on_accent=PALETTE.grey_6,
    focus_shadow=PALETTE.focus,
)


LIGHT = Theme(
    name="light",
    is_dark=False,
    page=PALETTE.grey_1,
    header="rgba(252, 245, 241, 0.94)",
    sidebar=PALETTE.off_white,
    modal=PALETTE.off_white,
    surface="rgba(38, 36, 35, 0.04)",
    surface_2="rgba(38, 36, 35, 0.07)",
    surface_3="rgba(38, 36, 35, 0.12)",
    border=PALETTE.grey_2,
    border_soft="rgba(38, 36, 35, 0.1)",
    text_1=PALETTE.grey_6,
    text_2=PALETTE.grey_5,
    text_3=PALETTE.grey_4,
    text_4=PALETTE.grey_3,
    accent=PALETTE.green_5,
    accent_strong=PALETTE.green_6,
    hover="#8a6d00",
    link=PALETTE.green_6,
    ok=PALETTE.green_6,
    ok_bg="rgba(60, 133, 39, 0.14)",
    info=PALETTE.blue_6,
    info_bg="rgba(47, 111, 154, 0.12)",
    amber="#96601a",
    amber_bg="rgba(217, 119, 47, 0.14)",
    danger="#a03b30",
    danger_bg="rgba(160, 59, 48, 0.12)",
    on_accent=PALETTE.off_white,
    focus_shadow=PALETTE.focus,
)


THEMES = {"dark": DARK, "light": LIGHT}


@dataclass(frozen=True)
class Metrics:
    """尺寸约定。直角 + 2px 描边是这套风格的骨架，别改。"""

    # 控件统一高度（网站后台 --bk-control-h）
    control_height: int = 32
    border_width: int = 2
    radius: int = 0

    # 间距阶梯
    gap_xs: int = 4
    gap_sm: int = 8
    gap_md: int = 12
    gap_lg: int = 16
    gap_xl: int = 24

    # 字号（网站 --mc-*-font-size）
    font_small: int = 11
    font_medium: int = 15
    font_large: int = 17
    font_body: int = 12
    font_title: int = 17

    # 按钮尺寸档（网站 --mc-*-width/height）
    button_large_width: int = 258
    button_large_height: int = 48
    button_medium_width: int = 129
    button_medium_height: int = 32
    button_small_width: int = 43
    button_small_height: int = 24

    letter_spacing: float = 0.5


METRICS = Metrics()


@dataclass
class DesignTokens:
    """打包好的令牌三件套，界面上通过 `design.tokens()` 取。"""

    palette: Palette = field(default_factory=lambda: PALETTE)
    metrics: Metrics = field(default_factory=lambda: METRICS)
    theme: Theme = field(default_factory=lambda: DARK)

    def for_theme(self, name: str) -> Theme:
        return THEMES.get(name, DARK)


TOKENS = DesignTokens()


def theme_by_name(name: str) -> Theme:
    """按 "dark" / "light" 取主题，未知名字回退到深色。"""

    return THEMES.get(name, DARK)
