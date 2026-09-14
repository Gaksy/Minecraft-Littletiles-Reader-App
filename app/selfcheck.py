"""冻结版自检：`LittleTilesReader --self-check`。

为什么需要它：打包后最容易坏的不是界面，而是**运行时才 import 的东西**。
`app/generators.py` 是按文件路径加载 `tools/*.py` 的，那些脚本又 import
`ltgen.console` / `ltgen.manifest` 之类；PyInstaller 的静态分析看不见这一层，
漏掉一个模块照样"构建成功"、点下去才炸——v0.1.0 的「重新组合素材」就是这么坏的
（`No module named ltgen.console`）。这个自检把整条链路真跑一遍。

用法（打包后，从终端跑才有输出）：

```sh
<包>/LittleTilesReader.app/Contents/MacOS/LittleTilesReader --self-check
```

返回码 0 = 能发；1 = 别发（哪一条挂了都打出来了）。
"""

from __future__ import annotations

import sys

from .config import bundle_root


def _force_utf8() -> None:
    """自检的输出里有中文；被重定向成管道时 Windows 会退回 locale 编码（cp1252）直接崩。

    打包机上的"清空环境变量跑自检"就是这么炸的（`UnicodeEncodeError`），
    而不是自检内容有问题。这里兜一层，编不出来的字符降级成替代符。
    """

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

#: 运行时必须能 import 的 ltgen 子模块（tools/*.py 里用到的都在这里）。
LIBRARY_MODULES = (
    "ltgen",
    "ltgen.console",
    "ltgen.contract",
    "ltgen.lint",
    "ltgen.manifest",
    "ltgen.paths",
    "ltgen.tint",
)

#: 必须随包的只读数据（相对 bundle_root）。
BUNDLED_DATA = (
    "app/data/block_ids.tsv",
    "app/resources/fonts",
    "tools/build_assets_from_pack.py",
    "tools/add_mod_textures.py",
    "tools/resolve_block_textures.py",
)


def _ltgen_modules() -> str:
    import importlib

    for name in LIBRARY_MODULES:
        importlib.import_module(name)
    return "%d 个模块" % len(LIBRARY_MODULES)


def _tool_scripts() -> str:
    from .generators import TOOL_NAMES, load_tool

    for name in TOOL_NAMES:
        load_tool(name)
    return "、".join(TOOL_NAMES)


def _bundled_data() -> str:
    missing = [name for name in BUNDLED_DATA if not (bundle_root() / name).exists()]
    if missing:
        raise FileNotFoundError("缺：%s" % "、".join(missing))
    return "%d 项" % len(BUNDLED_DATA)


def _language_tables() -> str:
    """每种界面语言的表都真加载一遍（动态 import，PyInstaller 看不见这条边）。

    漏收集时的症状很隐蔽：日志写着"界面语言: ja"，界面却还是中文 —— 只自检
    "能不能 import" 是查不出来的，得把每张表都装进内存看它非空。
    """

    from . import i18n

    codes = [code for code in i18n.codes() if code != i18n.SOURCE]
    empty = []
    for code in codes:
        i18n.set_language(code)
        if not i18n.table():
            empty.append(code)
    i18n.set_language(i18n.SOURCE)
    if empty:
        raise RuntimeError("这些语言的表是空的：%s" % "、".join(empty))
    return "%d 种语言" % len(codes)


def _reader() -> str:
    """CLI 在不在。形态 A（瘦客户端）本来就没有，所以不算失败。"""

    from .reader import locate

    path = locate()
    return "%s（存在=%s）" % (path, path.is_file())


def _gui() -> str:
    """Qt 能不能起来（离屏即可，不需要显示器）。"""

    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import PySide6
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    return "PySide6 %s" % PySide6.__version__


CHECKS = (
    ("ltgen 模块", _ltgen_modules),
    ("工具脚本（按路径加载）", _tool_scripts),
    ("界面语言表", _language_tables),
    ("随包只读数据", _bundled_data),
    ("库 CLI", _reader),
    ("Qt", _gui),
)


def run() -> int:
    """跑完所有检查，逐条打印；全过返回 0。"""

    _force_utf8()
    print("LittleTiles Reader 自检（frozen=%s）" % getattr(sys, "frozen", False))
    print("解包目录：%s" % bundle_root())
    failed = 0
    for title, check in CHECKS:
        try:
            detail = check()
        except Exception as error:  # 自检本身不该因为某项失败而中断
            failed += 1
            print("  [失败] %-22s %s: %s" % (title, type(error).__name__, error))
            continue
        print("  [通过] %-22s %s" % (title, detail))
    print("结果：%s" % ("全部通过，可以发" if not failed else "%d 项失败，别发" % failed))
    return 1 if failed else 0
