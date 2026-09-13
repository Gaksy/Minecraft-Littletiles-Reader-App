"""随应用带的小图标（像素风）。

目前只有复选框的勾：Qt 的 QSS 画不出"勾"，只能给 `image:` 一个位图。
图标是 12×12 的像素图（`app/resources/icons/`），颜色固定为深色——
勾只出现在绿色/蓝色填充上，深色勾在深浅两套主题里都看得清。
"""

from __future__ import annotations

from pathlib import Path

_ICON_DIR = Path(__file__).resolve().parents[2] / "resources" / "icons"


def icon_path(name: str) -> str:
    """图标的绝对路径（QSS 的 `url()` 需要绝对路径）。"""

    return str(_ICON_DIR / name)


def icon_url(name: str) -> str:
    """给 QSS 用的 `url(...)` 片段；文件不存在时返回空串（样式里就不引用）。"""

    path = _ICON_DIR / name
    if not path.is_file():
        return ""
    # Qt 的 url() 里反斜杠要转成正斜杠（Windows 路径）
    return "url(%s)" % str(path).replace("\\", "/")
