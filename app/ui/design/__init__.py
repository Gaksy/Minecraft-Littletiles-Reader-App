"""设计系统：与网站（inception.work / mcpixel-craft-ui）同一套视觉语言。

用法：

```python
from app.ui.design import install, theme, primary_button, SectionTitle

install(app, config.ui_theme)     # 启动时一次
button = primary_button("导出")
color = theme().accent            # 任何地方取语义色
```

改风格只改 `tokens.py`（颜色/尺寸）与 `qss.py`（形态）。
"""

from __future__ import annotations

from . import components, fonts, qss, theme, tokens
from .components import (
    SectionTitle,
    StatusChip,
    accent_button,
    card,
    danger_button,
    general_button,
    ghost_button,
    hint,
    primary_button,
    row,
    separator,
    set_role,
    set_variant,
    title,
)
from .theme import install, is_dark_theme, manager, set_theme, theme, toggle_theme
from .tokens import DARK, LIGHT, METRICS, PALETTE, THEMES, Theme, theme_by_name

__all__ = [
    "DARK",
    "LIGHT",
    "METRICS",
    "PALETTE",
    "THEMES",
    "SectionTitle",
    "StatusChip",
    "Theme",
    "accent_button",
    "card",
    "components",
    "danger_button",
    "fonts",
    "ghost_button",
    "general_button",
    "hint",
    "install",
    "is_dark_theme",
    "manager",
    "primary_button",
    "qss",
    "row",
    "separator",
    "set_role",
    "set_theme",
    "set_variant",
    "theme",
    "theme_by_name",
    "title",
    "toggle_theme",
    "tokens",
]
