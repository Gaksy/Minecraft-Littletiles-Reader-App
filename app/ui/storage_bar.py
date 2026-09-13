"""一条按颜色分段的容量条 + 图例（像苹果「存储空间」那样，设计文档 §7.8）。

只有**一条**条：每段宽度 = 该类占比。要点都在这一处：

* 段与段之间留 2px 缝——不留缝的话相邻两类颜色糊成一块，看不出是几类；
* 占比极小的类别也留一个可见的最小宽度，否则它在条上根本点不到；
* 悬停某段或图例某行只高亮那一类，其它变淡，条上给出"名称 + 大小 + 占比"。

颜色来自 `app.storage`（语义色写在一处，别在控件里各写各的）。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..storage import human_size, percent

BAR_HEIGHT = 22
GAP = 2
MIN_WIDTH = 3          # 极小占比也要看得见、点得到


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    color: QColor
    size: int


class StorageBar(QWidget):
    """一条分段容量条。`hovered` 发的是段序号，-1 = 没有悬停。"""

    hovered = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._segments: list[Segment] = []
        self._highlight = -1
        self.setMinimumHeight(BAR_HEIGHT)
        self.setMaximumHeight(BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ---- 数据 ------------------------------------------------------------

    def set_segments(self, segments: list[Segment]) -> None:
        self._segments = list(segments)
        self._highlight = -1
        self.update()

    def set_highlight(self, index: int) -> None:
        if index != self._highlight:
            self._highlight = index
            self.update()

    @property
    def segments(self) -> list[Segment]:
        return self._segments

    # ---- 几何 ------------------------------------------------------------

    def _widths(self, total_width: float) -> list[float]:
        count = len(self._segments)
        if count == 0:
            return []
        usable = total_width - GAP * (count - 1)
        total_size = sum(segment.size for segment in self._segments)
        if usable <= 0 or total_size <= 0:
            return [0.0] * count

        widths = [usable * segment.size / total_size for segment in self._segments]
        # 把小于最小宽度的抬起来，缺口从"还很宽"的那几段按比例扣
        deficit = sum(max(0.0, MIN_WIDTH - w) for w in widths)
        if deficit > 0:
            big = [i for i, w in enumerate(widths) if w > MIN_WIDTH]
            budget = sum(widths[i] for i in big) - deficit
            if big and budget > 0:
                big_total = sum(self._segments[i].size for i in big)
                for i in big:
                    widths[i] = budget * self._segments[i].size / big_total
            for i, width in enumerate(widths):
                if width < MIN_WIDTH:
                    widths[i] = MIN_WIDTH
        scale = usable / sum(widths) if sum(widths) > usable else 1.0
        return [w * scale for w in widths]

    def _rects(self) -> list[QRectF]:
        widths = self._widths(float(self.width()))
        rects: list[QRectF] = []
        x = 0.0
        for index, width in enumerate(widths):
            rects.append(QRectF(x, 0.0, width, float(self.height())))
            x += width + GAP
        return rects

    def _hit(self, pos_x: float) -> int:
        for index, rect in enumerate(self._rects()):
            if rect.left() <= pos_x <= rect.right():
                return index
        return -1

    # ---- 绘制与交互 ------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = self.height() / 2.0
        # 底：空的部分看得见（用户能知道"条还没满"）
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().color(QPalette.ColorRole.Mid))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), radius, radius)

        for index, (rect, segment) in enumerate(zip(self._rects(), self._segments)):
            color = QColor(segment.color)
            if self._highlight >= 0 and index != self._highlight:
                color.setAlpha(70)      # 其余变淡，被指的那段自己站出来
            painter.setBrush(color)
            if index == self._highlight:
                pen = QPen(self.palette().color(QPalette.ColorRole.WindowText))
                pen.setWidth(2)
                painter.setPen(pen)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, min(radius, rect.width() / 2.0), radius)
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self._hit(event.position().x())
        self.set_highlight(index)
        self.setToolTip(self._tooltip(index))
        self.hovered.emit(index)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.set_highlight(-1)
        self.setToolTip("")
        self.hovered.emit(-1)
        super().leaveEvent(event)

    def _tooltip(self, index: int) -> str:
        if index < 0 or index >= len(self._segments):
            return ""
        total = sum(segment.size for segment in self._segments)
        segment = self._segments[index]
        return "%s　%s（%.1f%%）" % (
            segment.label,
            human_size(segment.size),
            percent(segment.size, total),
        )


class LegendRow(QWidget):
    """图例的一行：色点 + 名称 + 大小 + 占比。可悬停、可点击。"""

    hovered = Signal(int)
    clicked = Signal(int)

    def __init__(self, index: int, segment: Segment, total: int, parent=None) -> None:
        super().__init__(parent)
        self.index = index
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 1, 0, 1)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            "background:%s; border-radius:5px;" % segment.color.name()
        )
        row.addWidget(dot)
        row.addWidget(QLabel(segment.label))
        row.addStretch(1)
        row.addWidget(QLabel(human_size(segment.size)))
        share = QLabel("%.1f%%" % percent(segment.size, total))
        share.setMinimumWidth(48)
        share.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(share)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点一下看这一类的明细")

    def enterEvent(self, event) -> None:  # noqa: N802
        self.hovered.emit(self.index)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hovered.emit(-1)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mouseReleaseEvent(event)


class StorageLegend(QWidget):
    """容量条下面的图例：按大小降序，悬停联动高亮。"""

    hovered = Signal(int)
    clicked = Signal(str)      # 类别 key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._segments: list[Segment] = []

    def set_segments(self, segments: list[Segment]) -> None:
        self._segments = list(segments)
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        total = sum(segment.size for segment in segments)
        for index, segment in enumerate(segments):
            row = LegendRow(index, segment, total, self)
            row.hovered.connect(self.hovered.emit)
            row.clicked.connect(lambda _index, key=segment.key: self.clicked.emit(key))
            self._layout.addWidget(row)

    @property
    def segments(self) -> list[Segment]:
        return self._segments
