"""组件级助手：把"网站里的那种小零件"做成一行代码。

都只是给 Qt 控件打上 QSS 认得的属性/结构，不引入新组件类型——
这样界面代码保持普通 Qt，样式集中在 `qss.py`。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .tokens import METRICS


def set_variant(widget: QWidget, variant: str) -> QWidget:
    """设置按钮/控件的外观变体：primary / danger / ghost。"""

    widget.setProperty("variant", variant)
    _refresh(widget)
    return widget


def set_role(widget: QWidget, role: str) -> QWidget:
    """设置标签语义：title / subtitle / hint / dim / section / ok / warn / error。"""

    widget.setProperty("role", role)
    _refresh(widget)
    return widget


def _refresh(widget: QWidget) -> None:
    """属性改了要让 QSS 重新计算（Qt 不会自动重算）。"""

    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def primary_button(text: str, *, size: str | None = None) -> QPushButton:
    """主要动作按钮：**草绿渐变**（网站首页 CTA 用的就是这套 secondary）。

    名字叫 primary 是按"界面语义"来的（主要动作）；组件库那边这个外观叫
    secondary。想要组件库的蓝色 primary 用 `accent_button()`。
    """

    button = QPushButton(text)
    button.setProperty("variant", "secondary")
    if size:
        button.setProperty("size", size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def accent_button(text: str) -> QPushButton:
    """组件库里的 primary：蓝色渐变按钮。"""

    button = QPushButton(text)
    button.setProperty("variant", "primary")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def general_button(text: str) -> QPushButton:
    """组件库里的 general：浅灰像素按钮（默认外观）。"""

    button = QPushButton(text)
    button.setProperty("variant", "general")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def danger_button(text: str) -> QPushButton:
    """危险动作（删除、清理）：橙色渐变。"""

    button = QPushButton(text)
    button.setProperty("variant", "danger")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def ghost_button(text: str) -> QPushButton:
    """次要动作（不抢视线）。"""

    button = QPushButton(text)
    button.setProperty("variant", "ghost")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class SectionTitle(QLabel):
    """带左侧绿色竖条的分区标题（网站后台的段落标题形态）。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "section")


class StatusChip(QLabel):
    """状态标签：inventory 那种小方块标签（已导出 / 已过期 / 缺失…）。"""

    def __init__(self, text: str = "", kind: str = "muted", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("chip", kind)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_state(self, text: str, kind: str) -> None:
        self.setText(text)
        self.setProperty("chip", kind)
        _refresh(self)


def separator(horizontal: bool = True) -> QFrame:
    """一条 1px 分隔线。"""

    line = QFrame()
    line.setProperty("role", "separator")
    if horizontal:
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(METRICS.border_width)
    else:
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(METRICS.border_width)
    return line


def card(*, padding: int | None = None, spacing: int | None = None) -> tuple[QFrame, QVBoxLayout]:
    """一块卡片容器（比页面底色亮一档的面 + 2px 描边）。

    返回 `(frame, layout)`，调用方往 layout 里塞内容即可。
    """

    frame = QFrame()
    frame.setProperty("card", "true")
    layout = QVBoxLayout(frame)
    gap = METRICS.gap_md if padding is None else padding
    layout.setContentsMargins(gap, gap, gap, gap)
    layout.setSpacing(METRICS.gap_sm if spacing is None else spacing)
    return frame, layout


def row(*widgets: QWidget, spacing: int | None = None, stretch_last: bool = False) -> QWidget:
    """把若干控件横排成一行（带统一间距）。"""

    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(METRICS.gap_sm if spacing is None else spacing)
    for index, widget in enumerate(widgets):
        layout.addWidget(widget, 1 if (stretch_last and index == len(widgets) - 1) else 0)
    container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    return container


def hint(text: str) -> QLabel:
    """次要说明文字。"""

    label = QLabel(text)
    label.setProperty("role", "hint")
    label.setWordWrap(True)
    return label


def title(text: str) -> QLabel:
    """页面/对话框主标题。"""

    label = QLabel(text)
    label.setProperty("role", "title")
    return label
