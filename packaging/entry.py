"""PyInstaller 的入口脚本（不要删）。

为什么不用 `app/__main__.py` 直接当入口：那个文件是给 `python -m app` 用的，
里面全是相对导入（`from .applog import ...`）。PyInstaller 把入口当**脚本**执行，
此时 `__package__` 是空的，相对导入会直接抛
`ImportError: attempted relative import with no known parent package`——
构建能过、双击却起不来（v0.1.0 第一次打包真实踩到）。

这里用绝对导入把 `app` 当正常包导进来，`__main__.py` 里那套相对导入就走常规
的包内解析，两个入口共用同一份 `main()`。
"""

from __future__ import annotations

import sys

from app.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
