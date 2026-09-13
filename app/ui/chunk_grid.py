"""区块范围示意：俯视图，每格一个区块（16×16 方块）。

**这是示例图，不是选择控件**——用户不在这里点选，坐标由旁边的输入框决定，
这块只负责把"将要导出哪一片"画出来（粗框），以及三种模式的区别
（见 docs/chunk-selection-modes.svg）。M4 会再把"导出过没有"的三态着色叠上来。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..job import ChunkRange
from .theme import Colors, colors_for

CELL = 26          # 每格的像素边长
BASE_SPAN = 9      # 至少显示 9×9 格，选中范围更大时自动扩展


class ChunkGrid(QWidget):
    """只读的示意控件：显示当前选择范围，不接受点击。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._center = (0, 0)
        self._range = ChunkRange(0, 0, 1, 1)
        self.setMinimumSize(BASE_SPAN * CELL + 1, BASE_SPAN * CELL + 1)

    def set_selection(self, center: tuple[int, int], selection: ChunkRange) -> None:
        self._center = center
        self._range = selection
        self._resize_to_fit()
        self.update()

    def _span(self) -> int:
        return max(
            BASE_SPAN, max(self._range.count_x, self._range.count_z) + 2
        )

    def _resize_to_fit(self) -> None:
        side = self._span() * CELL + 1
        self.setMinimumSize(side, side)

    def _origin(self) -> tuple[int, int]:
        """网格左上角对应的区块坐标。"""
        span = self._span()
        return (
            self._center[0] - span // 2,
            self._center[1] - span // 2,
        )

    # ---- 绘制 ------------------------------------------------------------

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        # 颜色一律取自调色板：深色模式下才不会出现白底浅字
        colors: Colors = colors_for(self.palette())
        painter.fillRect(self.rect(), colors.surface)
        span = self._span()
        ox, oz = self._origin()

        # 已选中的格子
        selected = set(self._range.cells())
        for cx, cz in selected:
            rect = QRectF(
                (cx - ox) * CELL, (cz - oz) * CELL, CELL, CELL
            )
            painter.fillRect(rect, colors.accent)

        # 中心格单独加深
        if self._center in selected:
            rect = QRectF(
                (self._center[0] - ox) * CELL,
                (self._center[1] - oz) * CELL,
                CELL,
                CELL,
            )
            painter.fillRect(rect, colors.accent_strong)

        # 网格线
        painter.setPen(QPen(colors.border, 1))
        for i in range(span + 1):
            painter.drawLine(i * CELL, 0, i * CELL, span * CELL)
            painter.drawLine(0, i * CELL, span * CELL, i * CELL)

        # 选择范围的粗边框
        painter.setPen(QPen(colors.accent_strong, 2))
        painter.drawRect(
            QRectF(
                (self._range.min_x - ox) * CELL,
                (self._range.min_z - oz) * CELL,
                self._range.count_x * CELL,
                self._range.count_z * CELL,
            )
        )

        # 原点提示（0,0 在视野内时画个十字）
        if ox <= 0 < ox + span and oz <= 0 < oz + span:
            painter.setPen(QPen(colors.marker, 1))
            cx = (0 - ox) * CELL + CELL / 2
            cz = (0 - oz) * CELL + CELL / 2
            painter.drawLine(int(cx - 6), int(cz), int(cx + 6), int(cz))
            painter.drawLine(int(cx), int(cz - 6), int(cx), int(cz + 6))

    def changeEvent(self, event: QEvent) -> None:
        # 系统切换深浅色时，Qt 会发 PaletteChange；重画一次即可跟上
        if event.type() == QEvent.Type.PaletteChange:
            self.update()
        super().changeEvent(event)
