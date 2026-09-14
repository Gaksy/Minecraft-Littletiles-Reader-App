"""找 LittleTilesReader（C++ 库编出来的 CLI）**在哪**。

打包版把库和客户端装在一起（形态 B：一个安装包、同一个位置、开箱即用），
所以查找顺序是：

1. 配置里手填的路径（高级用户想指到别的构建）；
2. **应用旁边**——打包版就是这里：`LittleTilesReader.app/Contents/Resources/…`
   旁边的可执行文件、或 exe 同目录的 `LittleTilesReader.exe`；
3. 库仓库的构建产物（`ltgen.paths.reader_executable()`，开发时的默认）。

第 2 条是这套打包能"装上就能用"的关键：用户不需要知道什么是 CLI、也不用配路径。
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from .applog import logger

NAMES = ("LittleTilesReader", "LittleTilesReader.exe")


def app_folder() -> Path:
    """应用"看得见"的那个文件夹（用户解压/安装后放它的地方）。"""

    if not getattr(sys, "frozen", False):
        from .config import APP_DIR

        return APP_DIR
    exe = Path(sys.executable).resolve()
    # macOS：…/LittleTilesReader.app/Contents/MacOS/LittleTilesReader → 取 .app 所在文件夹
    if sys.platform == "darwin" and exe.parent.name == "MacOS":
        return exe.parents[2].parent
    return exe.parent


def search_dirs() -> list[Path]:
    """会在哪些目录里找 CLI（顺序即优先级）。

    打包版里 CLI 有两处可能的落点，都要认：

    * **app 里面**（现在的方式）：`<app>/Contents/Frameworks/reader/`——
      这样 DMG 里只有一个 `.app`，用户拖一个就装完了；
    * **app 旁边**（老方式 / 便携版）：与 `.app` 同级。

    Windows 又多一层：应用自己在 `<包>/LittleTilesReader/`，CLI 在上一层
    `<包>/LittleTilesReader.exe`。
    """

    here = app_folder()
    dirs = [here / "reader", here]
    if getattr(sys, "frozen", False):
        bundle = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", "") else None
        if bundle:
            dirs.append(bundle / "reader")   # macOS .app：库 CLI 塞在包内
            dirs.append(Path(bundle))
        exe = Path(sys.executable).resolve()
        dirs.append(exe.parent)
        # Windows 的包结构是 <包>/LittleTilesReader/LittleTilesReader.exe（应用自己），
        # 而库的 CLI 在上一层 <包>/LittleTilesReader.exe——所以上一层必须也找。
        dirs.append(here.parent)
    # 去重且保序（同一个目录可能被上面几种写法重复命中）
    unique: list[Path] = []
    for folder in dirs:
        if folder not in unique:
            unique.append(folder)
    return unique


def bundled_reader() -> Path | None:
    """应用旁边的 CLI（没有就返回 None）。

    必须排掉"自己"：Windows 上应用的可执行文件也叫 `LittleTilesReader.exe`，
    而且就在 `app_folder()` 里，不排掉就会把**应用自己**当成库的 CLI 返回——
    后果是每跑一次导出都新开一个客户端窗口。
    """

    me = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None
    for folder in search_dirs():
        for name in NAMES:
            candidate = folder / name
            if not candidate.is_file():
                continue
            if me is not None and candidate.resolve() == me:
                logger().debug("跳过应用自己：%s", candidate)
                continue
            return candidate
    return None


def locate(configured: str | Path | None = None) -> Path:
    """按上面的顺序定位 CLI；都没找到就把库仓库那条路径返回（让上层去报错）。"""

    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return candidate
        logger().warning("配置里的 CLI 不存在，改用自动查找：%s", candidate)

    found = bundled_reader()
    if found is not None:
        return found

    from ltgen import paths

    fallback = paths.reader_executable()
    logger().info("应用旁边没有 LittleTilesReader，回退到库仓库构建产物：%s", fallback)
    return fallback


def describe() -> str:
    """给日志/界面用的一句话：现在用的是哪个 CLI、从哪儿来的。"""

    found = bundled_reader()
    if found is not None:
        return "应用自带（%s）" % found
    from ltgen import paths

    return "库仓库构建产物（%s，%s）" % (paths.reader_executable(), platform.system())
