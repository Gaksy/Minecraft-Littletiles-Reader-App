"""按调色板取语义色。

控件里**不写死颜色**：系统（或用户）给什么调色板就用什么。之前把按钮底色写成
`#ffffff`、网格底面写成 `#fcfcfd`，在深色模式下就变成白底浅字、选中框糊在背景里。

需要"品牌蓝"这类强调色时，也只按明暗选深浅两档，而不是固定一个值。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette


@dataclass(frozen=True)
class Colors:
    """一组语义色，够界面用即可。"""

    surface: QColor        # 控件底色（卡片、按钮）
    surface_hover: QColor  # 悬停态
    border: QColor         # 边框/网格线
    text: QColor           # 主文字
    muted: QColor          # 次要文字
    accent: QColor         # 强调（选中范围）
    accent_strong: QColor  # 强调（中心格、选中边框）
    marker: QColor         # 原点十字这类标记


def is_dark(palette: QPalette) -> bool:
    """窗口底色偏暗即为深色模式。这是 Qt 自己的判断方式，比读系统设置可靠。"""
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def colors_for(palette: QPalette) -> Colors:
    dark = is_dark(palette)
    surface = palette.color(QPalette.ColorRole.Base)
    text = palette.color(QPalette.ColorRole.Text)
    return Colors(
        surface=surface,
        surface_hover=(
            surface.lighter(130) if dark else surface.darker(105)
        ),
        border=palette.color(QPalette.ColorRole.Mid),
        text=text,
        muted=text.darker(160) if dark else text.lighter(160),
        # 深色底上用亮一档的蓝，浅色底上用深一档，保证选中范围看得清
        accent=QColor("#3b82f6") if dark else QColor("#93c5fd"),
        accent_strong=QColor("#60a5fa") if dark else QColor("#2563eb"),
        marker=QColor("#fbbf24") if dark else QColor("#f59e0b"),
    )
