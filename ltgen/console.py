"""控制台输出的编码兜底。

这些脚本的输出里必然有中文。Python 在 Windows 上被重定向成管道时，stdout 会退回
系统 locale 编码（可能是 cp1252 之类），一打印中文就 `UnicodeEncodeError` 直接崩——
而"被脚本调用"恰恰是这类工具的常见用法。

标准解法是设 `PYTHONUTF8=1`；这里再兜一层，保证无论怎么调用都不会因为编码崩掉。
"""

from __future__ import annotations

import sys


def enable_utf8_output() -> None:
    """把 stdout/stderr 切到 UTF-8；编不出来的字符降级为替代符，不抛异常。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # 被替换过的特殊流
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
