"""构建信息：打出来的这一版是**哪次提交、什么时候、哪台机器**上构建的。

为什么需要：冻结（PyInstaller）之后没有 `.git`，`git rev-parse` 只会返回"未知"，
用户报问题时最有用的一句话就丢了。所以 `tools/build_app.py` 在构建时写一个
`app/_buildinfo.py`，运行时优先读它；开发环境没有这个文件就退回读 git。

文件是可选的——缺失不影响运行（`about_text()` 会给出"开发环境"的写法）。
"""

from __future__ import annotations

import platform
from dataclasses import dataclass

from . import __version__


@dataclass(frozen=True)
class BuildInfo:
    commit: str = ""
    built_at: str = ""
    platform: str = ""
    frozen: bool = False

    @property
    def label(self) -> str:
        """一行展示：`0.1.0 · a1b2c3d · 2026-09-14 21:30 · macos-arm64`"""

        parts = [__version__]
        if self.commit:
            parts.append(self.commit)
        if self.built_at:
            parts.append(self.built_at)
        if self.platform:
            parts.append(self.platform)
        return " · ".join(parts)


def load() -> BuildInfo:
    """读构建信息：优先生成时写入的，其次运行环境（开发）。"""

    try:
        from . import _buildinfo  # 由 tools/build_app.py 生成，可能不存在

        return BuildInfo(
            commit=getattr(_buildinfo, "COMMIT", ""),
            built_at=getattr(_buildinfo, "BUILT_AT", ""),
            platform=getattr(_buildinfo, "PLATFORM", ""),
            frozen=True,
        )
    except ImportError:
        return BuildInfo(platform=platform.system().lower())


def frozen() -> bool:
    """当前是不是打包后的可执行文件（PyInstaller 会设 `sys.frozen`）。"""

    import sys

    return bool(getattr(sys, "frozen", False))
