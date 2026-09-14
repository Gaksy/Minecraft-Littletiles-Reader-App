"""三种区块选择模式的示意图——**按当前主题现画**，不再用固定配色的 SVG。

为什么改成画：原来的 `docs/chunk-selection-modes.svg` 颜色是写死的（白底 + 深灰字），
切到深色主题就是一张刺眼的白纸。画出来的版本所有颜色取自 `design.theme()`，
深浅两套自动跟随，也和界面其余部分同一套形态（直角、2px 描边、草绿选中）。

图里只有三块内容，从左到右：单区块 / 区块范围 / 中心 + 半径。每块画一个
7 × 5 的格子示意，被选中的格子用强调绿填、中心用亮黄描一圈。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import i18n
from . import design

CELL = 26
COLS = 6
ROWS = 4
PANEL_W = 300
PANEL_H = 200
GAP = 16


class ChunkModesIllustration(QWidget):
    """三块并排的示意图（尺寸固定，颜色跟主题走）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(PANEL_W * 3 + GAP * 2, PANEL_H)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # 主题换了要重画：颜色是现取的，不重画就还是旧主题的
        design.manager().changed.connect(self.update)

    # ---- 绘制 ----

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        theme = design.theme()
        panels = (
            (i18n.tr("单区块"), "single"),
            (i18n.tr("区块范围"), "range"),
            (i18n.tr("中心 + 半径"), "center"),
        )
        for index, (title, kind) in enumerate(panels):
            left = index * (PANEL_W + GAP)
            self._draw_panel(painter, left, title, kind)
        painter.end()

    def _draw_panel(self, painter: QPainter, left: int, title: str, kind: str) -> None:
        theme = design.theme()
        panel = QRectF(left, 0, PANEL_W, PANEL_H)
        painter.setPen(self._pen(theme.border, design.METRICS.border_width))
        painter.setBrush(QColor(theme.sidebar))
        painter.drawRect(panel)

        painter.setPen(QColor(theme.text_1))
        title_font = QFont(self.font())
        title_font.setBold(True)
        title_font.setPixelSize(design.METRICS.font_medium)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(left + design.METRICS.gap_md, design.METRICS.gap_sm, PANEL_W - 24, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        grid = self._grid_rect(left)
        selected, center = self._selection(kind)
        for row in range(ROWS):
            for column in range(COLS):
                cell = QRectF(
                    grid.left() + column * CELL,
                    grid.top() + row * CELL,
                    CELL - 2,
                    CELL - 2,
                )
                if (column, row) in selected:
                    painter.setBrush(QColor(theme.accent))
                    painter.setPen(self._pen(theme.accent_strong, 2))
                else:
                    painter.setBrush(QColor(theme.surface_3))
                    painter.setPen(self._pen(theme.border, 1))
                painter.drawRect(cell)
                if center is not None and (column, row) == center:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(self._pen(theme.hover, 2))
                    painter.drawRect(cell.adjusted(-2, -2, 2, 2))

        caption_font = QFont(self.font())
        caption_font.setPixelSize(design.METRICS.font_small)
        painter.setFont(caption_font)
        painter.setPen(QColor(theme.text_3))
        painter.drawText(
            QRectF(
                left + design.METRICS.gap_md,
                grid.bottom() + design.METRICS.gap_sm,
                PANEL_W - 2 * design.METRICS.gap_md,
                PANEL_H - grid.bottom() - design.METRICS.gap_sm,
            ),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            self._caption(kind),
        )

    def _grid_rect(self, left: int) -> QRectF:
        width = COLS * CELL - 2
        height = ROWS * CELL - 2
        return QRectF(
            left + (PANEL_W - width) / 2,
            design.METRICS.gap_sm + 30,
            width,
            height,
        )

    @staticmethod
    def _pen(color: str, width: int) -> QPen:
        pen = QPen(QColor(color))
        pen.setWidth(width)
        return pen

    @staticmethod
    def _selection(kind: str) -> tuple[set, tuple[int, int] | None]:
        """画哪几格被选中（列, 行），以及中心格（没有就是 None）。"""

        if kind == "single":
            return {(2, 1)}, None
        if kind == "range":
            return {(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2)}, None
        # center + radius（r = 1）：中心 + 周围一圈 = 3 × 3
        return (
            {(column, row) for column in range(1, 4) for row in range(0, 3)},
            (2, 1),
        )

    @staticmethod
    def _caption(kind: str) -> str:
        if kind == "single":
            return i18n.tr("输入一个区块坐标 (x, z)，只导出这一块。")
        if kind == "range":
            return i18n.tr("输入起点 (x1, z1) 与终点 (x2, z2)，导出这个矩形里的所有区块。")
        return i18n.tr(
            "输入中心 (x, z) 与半径 r，导出中心周围 (2r+1)² 个区块（亮黄框是中心）。"
        )
