"""界面小零件：几行代码、到处都用，但写错了会整页变形的那种。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QSizePolicy


def wrapped_label(text: str = "") -> QLabel:
    """自动换行的说明文字。

    **中文没有空格**，Qt 的 QLabel 一旦自动换行，`minimumSizeHint()` 会主张"整句话
    那么宽"（它按最长单词算，而一整句中文就是一个词）。放进布局后整页被撑宽，
    横向滚动条就出来了——看起来像排版坏了。把横向策略设成 `Ignored`，
    它才会真的按可用宽度折行。
    """
    label = QLabel(text)
    return wrap(label)


def wrap(label: QLabel) -> QLabel:
    """让已经建好的 QLabel 按可用宽度折行（理由见 `wrapped_label`）。

    顺带给一个很小的最小宽度：布局算"最小高度"时会按**最小宽度**去调
    `heightForWidth`，宽度给 0 的意思就是"每个字占一行"，那一行会被撑到几百像素高。
    """
    label.setWordWrap(True)
    label.setMinimumWidth(80)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


class ClickableLabel(QLabel):
    """能点的标签（比如封面）。

    用子类而不是给实例赋 `mouseReleaseEvent = lambda ...`：那样子类化的虚函数
    派发不一定会走实例属性，行为在 PySide 上不稳。
    """

    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
