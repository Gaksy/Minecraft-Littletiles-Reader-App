"""动效：只做"让人看懂刚刚发生了什么"的那几处，不做纯装饰的动画。

三处：

* `fade_in()`——窗口 / 对话框出现时淡入，避免"啪"地一下整屏换掉；
* `StorageBar` 的容量条由 0 长到实际比例，让"项目又大了"这件事看得见；
* 项目卡片在列表刷新时依次淡入（错开一点点）。

**离屏场景一律不动画**（`QT_QPA_PLATFORM=offscreen`，即自检与截图，
以及手动设 `LTR_NO_MOTION=1` 时）：那些场景要的是确定的静止画面，
动画跑一半截图会得到半透明的图。

注意：淡入用的是 `QGraphicsOpacityEffect`，它会强制整棵子树离屏绘制；
所以动画一结束就把效果摘掉，不留着影响后续绘制与截图。
"""

from __future__ import annotations

import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

DURATION_FADE = 180
DURATION_GROW = 260


def enabled() -> bool:
    """当前环境要不要放动画（离屏/自检环境返回 False）。"""

    if os.environ.get("LTR_NO_MOTION"):
        return False
    return os.environ.get("QT_QPA_PLATFORM", "") != "offscreen"


def fade_in(widget: QWidget | None, duration: int = DURATION_FADE, delay: int = 0):
    """把一个控件从透明淡到不透明；返回动画对象（不放动画时返回 None）。"""

    if widget is None or not enabled():
        return None

    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)

    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(max(0, duration))
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def finish() -> None:
        # 动画结束就摘掉效果：留着会让整个子树一直离屏合成
        QTimer.singleShot(0, lambda: widget.setGraphicsEffect(None))

    animation.finished.connect(finish)
    if delay > 0:
        QTimer.singleShot(delay, lambda: animation.start())
    else:
        animation.start()
    return animation
