"""区块状态网格：灰 = 未导出，绿 = 已导出，黄 = 可能已过期（设计文档 §6、§7.2）。

只用来"看"和"查"：**不在这里选范围**，范围仍旧由输入框决定（示例图不是控件，
免得"我点了半天怎么没选上"）。格子上悬停给出坐标与状态，点一下在旁边看详情。

`ChunkMapView` 把它包成"看地图"那种用法：范围大过视口就能滚，按住左键拖动平移
（拖动阈值 3px，所以"点一格"不会因为手抖变成拖动）。

格子太多的范围（比如半径 100）画出来只会糊成一片，所以超过 `MAX_CELLS` 就只画
中间那块，并标注"仅显示中间 N × N"。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QWidget

from ..records import STATE_FRESH, STATE_LABELS, STATE_MISSING, STATE_STALE
from . import design

CELL = 22
MAX_CELLS = 32      # 单边最多画这么多格（查询窗口用；导出对话框给更大的上限）
DRAG_SLOP = 3       # 拖动阈值：超过这么多像素才算"拖"，否则算"点"

def state_color(state: str) -> QColor:
    """三种状态的颜色取当前主题的语义色（深浅两套都看得清）。

    未导出 = 次要文字色（灰）、已导出 = 强调绿、可能过期 = 琥珀；
    早期这里是写死的三个十六进制值，深色主题下会有一格糊在背景里。
    """

    theme = design.theme()
    if state == STATE_FRESH:
        return QColor(theme.accent)
    if state == STATE_STALE:
        return QColor(theme.amber)
    return QColor(theme.text_4)


class ChunkStateGrid(QWidget):
    """一个区块范围的状态图。`cells` 是 {(x, z): (状态, 提示)}。

    格子大小与"单边最多画几格"可调：导出对话框里要放进一小块地方（12px × 16 格），
    查询窗口里可以画大一点（22px × 32 格）。
    """

    hovered = Signal(int, int, str)     # x, z, 提示（-1/-1 表示离开）
    clicked = Signal(int, int)          # 点了哪一格（-1/-1 表示点在空白处）
    panned = Signal(int, int)           # 拖动平移的像素增量（交给外层滚）

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
        self._selection: tuple[int, int, int, int] | None = None
        self._press: object | None = None
        self._dragged = False
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_area(
        self,
        min_x: int,
        min_z: int,
        count_x: int,
        count_z: int,
        cells: dict[tuple[int, int], tuple[str, str]],
        selection: tuple[int, int, int, int] | None = None,
    ) -> None:
        self._requested = (count_x, count_z)
        self._min_x = min_x
        self._min_z = min_z
        self._count_x = min(count_x, self._max_cells)
        self._count_z = min(count_z, self._max_cells)
        # 只画中间那块（而不是左上角）：看不到中心反而更容易误判
        if count_x > self._count_x:
            self._min_x += (count_x - self._count_x) // 2
        if count_z > self._count_z:
            self._min_z += (count_z - self._count_z) // 2
        self._cells = cells
        self._selection = selection
        self.setFixedSize(
            self._count_x * self._cell + 2, self._count_z * self._cell + 2
        )
        self.update()

    @property
    def count_x(self) -> int:
        """当前画出来的列数（测试与"尺寸显示"都用它）。"""

        return self._count_x

    @property
    def count_z(self) -> int:
        return self._count_z

    @property
    def min_x(self) -> int:
        return self._min_x

    @property
    def min_z(self) -> int:
        return self._min_z

    @property
    def cell(self) -> int:
        return self._cell

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
        # 像素风：不抗锯齿、直角格子（与网站一致）
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        border = QColor(design.theme().border)
        for row in range(self._count_z):
            for column in range(self._count_x):
                x = self._min_x + column
                z = self._min_z + row
                rect = self._cell_rect(x, z)
                painter.setBrush(state_color(self._state_of(x, z)))
                pen = QPen(border)
                pen.setWidth(1)
                painter.setPen(pen)
                painter.drawRect(rect)
        # 本次要导出的范围：在概览图上框出来（不然"图上的绿格"和"我要导的区块"
        # 是两件事，容易看串）
        if self._selection is not None:
            min_x, min_z, count_x, count_z = self._selection
            left = max(min_x, self._min_x)
            top = max(min_z, self._min_z)
            right = min(min_x + count_x - 1, self._min_x + self._count_x - 1)
            bottom = min(min_z + count_z - 1, self._min_z + self._count_z - 1)
            if right >= left and bottom >= top:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                pen = QPen(QColor(design.theme().hover))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawRect(
                    QRectF(
                        1 + (left - self._min_x) * self._cell,
                        1 + (top - self._min_z) * self._cell,
                        (right - left + 1) * self._cell - 2,
                        (bottom - top + 1) * self._cell - 2,
                    )
                )
        painter.end()

    def _hit(self, pos_x: float, pos_y: float) -> tuple[int, int]:
        column = int((pos_x - 1) // self._cell)
        row = int((pos_y - 1) // self._cell)
        if 0 <= column < self._count_x and 0 <= row < self._count_z:
            return self._min_x + column, self._min_z + row
        return -1, -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press is not None:
            delta = event.position() - self._press
            if abs(delta.x()) > DRAG_SLOP or abs(delta.y()) > DRAG_SLOP:
                self._dragged = True
                self.panned.emit(int(-delta.x()), int(-delta.y()))
                self._press = event.position()
                return
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

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position()
            self._dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if not self._dragged:
                x, z = self._hit(event.position().x(), event.position().y())
                self.clicked.emit(x, z)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setToolTip("")
        self.hovered.emit(-1, -1, "")
        super().leaveEvent(event)


class ChunkMapView(QScrollArea):
    """把状态网格放进可滚动视口，按住拖动就能平移（像看地图那样）。

    拖动实现在网格里（`panned`），这里只负责把增量喂给滚动条——
    鼠标事件落在网格上，装在滚动区上的实现根本收不到。
    """

    hovered = Signal(int, int, str)
    clicked = Signal(int, int)

    def __init__(
        self,
        parent: QWidget | None = None,
        cell: int = CELL,
        max_cells: int = MAX_CELLS,
    ) -> None:
        super().__init__(parent)
        self.grid = ChunkStateGrid(self, cell=cell, max_cells=max_cells)
        self.grid.hovered.connect(self.hovered)
        self.grid.clicked.connect(self.clicked)
        self.grid.panned.connect(self._pan)
        self.setWidget(self.grid)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(3 * cell + 40)

    def _pan(self, dx: int, dy: int) -> None:
        horizontal = self.horizontalScrollBar()
        vertical = self.verticalScrollBar()
        horizontal.setValue(horizontal.value() + dx)
        vertical.setValue(vertical.value() + dy)

    def set_area(
        self,
        min_x: int,
        min_z: int,
        count_x: int,
        count_z: int,
        cells: dict,
        selection: tuple[int, int, int, int] | None = None,
    ) -> None:
        self.grid.set_area(min_x, min_z, count_x, count_z, cells, selection)

    def center_on_chunk(self, x: int, z: int) -> None:
        """把某一块滚到视口中间（打开时让"有数据的地方"落在眼前）。"""

        grid = self.grid
        if grid.count_x <= 0 or grid.count_z <= 0:
            return
        target_x = (
            1 + (x - grid.min_x) * grid.cell + grid.cell / 2
            - self.viewport().width() / 2
        )
        target_y = (
            1 + (z - grid.min_z) * grid.cell + grid.cell / 2
            - self.viewport().height() / 2
        )
        self.horizontalScrollBar().setValue(int(max(0, target_x)))
        self.verticalScrollBar().setValue(int(max(0, target_y)))
