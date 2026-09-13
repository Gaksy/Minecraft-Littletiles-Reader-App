"""语义色（兼容层）：自绘控件用它取色，颜色统一来自设计系统。

历史上这里读的是 Qt 系统调色板（深色模式跟随系统），于是界面在 Windows /
macOS 上长得不一样。现在风格与网站统一，颜色改由 `app/ui/design` 的令牌提供，
**这里的 `colors_for()` 只是为了不改动一堆自绘控件而保留的旧接口**：
参数（widget 的 palette）不再决定颜色，真正决定颜色的是全局主题。

新代码请直接用：

```python
from app.ui.design import theme
t = theme()          # t.accent / t.text_1 / t.border …
```
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette

from .design import theme as current_theme


@dataclass(frozen=True)
class Colors:
    """一组语义色（自绘控件用）。字段名沿用旧接口。"""

    surface: QColor        # 控件底色（卡片、按钮）
    surface_hover: QColor  # 悬停态
    border: QColor         # 边框/网格线
    text: QColor           # 主文字
    muted: QColor          # 次要文字
    accent: QColor         # 强调（选中范围）
    accent_strong: QColor  # 强调（中心格、选中边框）
    marker: QColor         # 原点十字这类标记


def is_dark(palette: QPalette | None = None) -> bool:
    """当前是不是深色主题（参数已废弃，保留是为了兼容旧调用）。"""

    return current_theme().is_dark


def colors_for(palette: QPalette | None = None) -> Colors:
    """按当前主题取一组语义色（参数已废弃，传什么都不影响结果）。"""

    t = current_theme()
    return Colors(
        surface=QColor(t.sidebar),
        surface_hover=QColor(t.surface_3),
        border=QColor(t.border),
        text=QColor(t.text_1),
        muted=QColor(t.text_3),
        accent=QColor(t.accent),
        accent_strong=QColor(t.accent_strong),
        # 原点标记沿用网站的亮黄 hover 色
        marker=QColor(t.hover),
    )
