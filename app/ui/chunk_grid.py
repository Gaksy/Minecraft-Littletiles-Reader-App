"""区块状态网格：灰 = 未导出，绿 = 已导出，黄 = 可能已过期（设计文档 §6、§7.2）。

只用来"看"，不在这里选范围——范围仍由输入框决定（和导出对话框里那张示意图
是同一条原则：示例图不是控件）。格子上悬停能看到状态与导出时间。

格子太多的范围（比如半径 100）画出来只会糊成一片，所以超过上限就只画前
`MAX_CELLS` 个并标注"仅显示前 N 个"。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..records import STATE_FRESH, STATE_MISSING, STATE_STALE, STATE_LABELS

CELL = 22
MAX_CELLS = 32      # 单边最多画这么多格

STATE_COLORS = {
    STATE_MISSING: "#9aa0a6",   # 灰
    STATE_FRESH: "#59a14f",     # 绿
    STATE_STALE: "#edc948",     # 黄
}


class ChunkStateGrid(QWidget):
    """一个区块范围的状态图。`cells` 是 {(x, z): (状态, 提示)}。

    格子大小与"单边最多画几格"可调：导出对话框里要放进一小块地方（12px × 16 格），
    查询窗口里可以画大一点（22px × 32 格）。
    """

    hovered = Signal(int, int, str)     # x, z, 提示（-1/-1 表示离开）

    def __init__(
        self,
        parent: QWidget | None = None,
        cell: int = CELL,
        max_cells: int = MAX_CELLS,
    ) -> None:
        super().__init__(parent)
        self._cell = cell
        self._max_cells = max_cells
        self._min_x = 0
        self._min_z = 0
        self._count_x = 0
        self._count_z = 0
        self._requested = (0, 0)
        self._cells: dict[tuple[int, int], tuple[str, str]] = {}
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_area(
        self,
        min_x: int,
        min_z: int,
        count_x: int,
        count_z: int,
        cells: dict[tuple[int, int], tuple[str, str]],
    ) -> None:
        self._requested = (count_x, count_z)
        self._min_x = min_x
        self._min_z = min_z
        self._count_x = min(count_x, self._max_cells)
        self._count_z = min(count_z, self._max_cells)
        self._cells = cells
        self.setFixedSize(
            self._count_x * self._cell + 2, self._count_z * self._cell + 2
        )
        self.update()

    @property
    def truncated(self) -> bool:
        return self._requested != (self._count_x, self._count_z)

    @property
    def cells(self) -> dict:
        """画出来的那些格子的状态（测试与将来的"点了哪一格"都用它）。"""
        return dict(self._cells)

    def _cell_rect(self, x: int, z: int) -> QRectF:
        column = x - self._min_x
        row = z - self._min_z
        return QRectF(
            1 + column * self._cell,
            1 + row * self._cell,
            self._cell - 2,
            self._cell - 2,
        )

    def _state_of(self, x: int, z: int) -> str:
        found = self._cells.get((x, z))
        return found[0] if found else STATE_MISSING

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._count_x <= 0 or self._count_z <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        border = self.palette().color(QPalette.ColorRole.Mid)
        for row in range(self._count_z):
            for column in range(self._count_x):
                x = self._min_x + column
                z = self._min_z + row
                rect = self._cell_rect(x, z)
                painter.setBrush(QColor(STATE_COLORS[self._state_of(x, z)]))
                pen = QPen(border)
                pen.setWidth(1)
                painter.setPen(pen)
                painter.drawRect(rect)
        painter.end()

    def _hit(self, pos_x: float, pos_y: float) -> tuple[int, int]:
        column = int((pos_x - 1) // self._cell)
        row = int((pos_y - 1) // self._cell)
        if 0 <= column < self._count_x and 0 <= row < self._count_z:
            return self._min_x + column, self._min_z + row
        return -1, -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        x, z = self._hit(event.position().x(), event.position().y())
        if x < 0:
            self.setToolTip("")
            self.hovered.emit(-1, -1, "")
        else:
            state, detail = self._cells.get((x, z), (STATE_MISSING, ""))
            text = "区块 (%d, %d)：%s%s" % (
                x, z, STATE_LABELS.get(state, state),
                ("　" + detail) if detail else "",
            )
            self.setToolTip(text)
            self.hovered.emit(x, z, text)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setToolTip("")
        self.hovered.emit(-1, -1, "")
        super().leaveEvent(event)
