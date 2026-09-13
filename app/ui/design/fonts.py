"""像素字体（Fusion Pixel）的加载与回退。

网站用 `--font-pixel-12-mono` 这套字体栈，桌面端要一致就得把字体文件带给应用。
查找顺序（先找到先用，都没有就回退系统字体，界面仍然可用）：

1. 环境变量 `LTGEN_FONT_DIR` 指定的目录；
2. 打包/仓库内自带的 `app/resources/fonts/`；
3. 开发机上的组件库 `mcpixel-craft-ui/dist/fonts/`。

字体是 SIL OFL 1.1（见同目录 `OFL.txt`），随包分发没问题。
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from ...applog import logger

# 12px 等宽：正文与控件都用它（网站 --font-pixel-12-mono）
FONT_FILES = (
    "fusion-pixel-12px-monospaced-zh_hans.ttf",
    "fusion-pixel-12px-monospaced-latin.ttf",
)

# 系统回退栈：没有像素字体时至少不难看（各平台都列上，找不到的会被跳过）
FALLBACK_FAMILIES = (
    "PingFang SC",       # macOS 中文
    "Microsoft YaHei UI",  # Windows 中文
    "Noto Sans CJK SC",  # Linux
    "Menlo",
    "Consolas",
    "monospace",
)

_loaded_families: tuple[str, ...] = ()


def candidate_dirs() -> list[Path]:
    """按优先级列出可能放着字体文件的目录。"""

    dirs: list[Path] = []
    env = os.environ.get("LTGEN_FONT_DIR")
    if env:
        dirs.append(Path(env))
    # app/ui/design/fonts.py → 仓库根/app/resources/fonts
    dirs.append(Path(__file__).resolve().parents[2] / "resources" / "fonts")
    dirs.append(Path("/Users/external_elliott/Development/mcpixel-craft-ui/dist/fonts"))
    return dirs


def load_fonts() -> tuple[str, ...]:
    """注册像素字体并返回可用的字体族名（已注册过就返回缓存）。

    返回值可直接喂给 `QFont.setFamilies()`；为空表示没找到字体文件，
    调用方应退回系统字体栈。
    """

    global _loaded_families
    if _loaded_families:
        return _loaded_families

    families: list[str] = []
    for directory in candidate_dirs():
        if not directory.is_dir():
            continue
        missing = [name for name in FONT_FILES if not (directory / name).is_file()]
        if missing:
            continue
        for name in FONT_FILES:
            font_id = QFontDatabase.addApplicationFont(str(directory / name))
            if font_id < 0:
                logger().warning("字体注册失败：%s", directory / name)
                continue
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
        if families:
            logger().info("像素字体已加载：%s（%s）", ", ".join(families), directory)
            break

    if not families:
        logger().info("没有找到像素字体文件，回退系统字体")

    _loaded_families = tuple(dict.fromkeys(families))
    return _loaded_families


def font_families() -> tuple[str, ...]:
    """界面要用的字体族列表：像素字体在前，系统字体兜底。"""

    return tuple(load_fonts()) + FALLBACK_FAMILIES


def font_families_css() -> str:
    """给 QSS 用的 font-family 片段（带引号，逗号分隔）。"""

    return ", ".join(f'"{name}"' for name in font_families())


def has_pixel_font() -> bool:
    """是否真的用上了像素字体（测试里用来判断截图是否该按像素字体比对）。"""

    return bool(load_fonts())


def reset_cache() -> None:
    """清掉缓存（测试用：换过 LTGEN_FONT_DIR 后重新探测）。"""

    global _loaded_families
    _loaded_families = ()
