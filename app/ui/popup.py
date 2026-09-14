"""消息框的统一入口：顺手把标题与正文译成当前语言。

为什么包一层而不是直接调 `QMessageBox`：

* 弹窗的文案散在几十个调用点上，靠人工记得"这里也要 tr()"迟早会漏；
* 弹窗**只有真出错时才出现**，漏翻很难被日常使用发现——本文件让"从这儿出去的
  弹窗都过一遍 `i18n.tr`"成为默认行为，漏翻的也只是原样显示中文，不会报错。

测试里替换的是 `QMessageBox` 的静态方法（`QMessageBox.warning = ...`），
这一层内部仍旧调它们，所以替身照旧生效——不要在别处绕开这一层。
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import QMessageBox

from .. import i18n


def interactive() -> bool:
    """当前环境能不能弹模态框。

    离屏（`QT_QPA_PLATFORM=offscreen`，也就是自检）下 `exec()` 会一直等一个永远不会
    出现的点击——所以那种环境里只写日志，不弹窗。真实桌面环境返回 True。
    """

    return os.environ.get("QT_QPA_PLATFORM", "") != "offscreen"


def info(parent, title: str, text: str, **kwargs) -> None:
    QMessageBox.information(parent, i18n.tr(title), i18n.tr(text), **kwargs)


def warning(parent, title: str, text: str, **kwargs) -> None:
    QMessageBox.warning(parent, i18n.tr(title), i18n.tr(text), **kwargs)


def error(parent, title: str, text: str, **kwargs) -> None:
    QMessageBox.critical(parent, i18n.tr(title), i18n.tr(text), **kwargs)


def ask(
    parent,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton | None = None,
    default: QMessageBox.StandardButton | None = None,
):
    """问一句，返回用户点的那个按钮。不传按钮就是 Qt 默认的是/否。"""

    if buttons is None:
        return QMessageBox.question(parent, i18n.tr(title), i18n.tr(text))
    if default is None:
        return QMessageBox.question(parent, i18n.tr(title), i18n.tr(text), buttons)
    return QMessageBox.question(
        parent, i18n.tr(title), i18n.tr(text), buttons, default
    )
