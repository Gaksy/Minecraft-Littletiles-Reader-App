"""区块选择说明：展示 docs/chunk-selection-modes.svg。

只读，固定大小。放在独立窗口而不是常驻在导出对话框里——图很大（1240×576），
常驻会把导出对话框撑得又宽又空。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

MODES_SVG = Path(__file__).resolve().parents[2] / "docs" / "chunk-selection-modes.svg"

# 按原图缩放。0.72 → 约 893×415，普通笔记本屏幕放得下。
DEFAULT_SCALE = 0.72


class IllustrationDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, scale: float = DEFAULT_SCALE) -> None:
        super().__init__(parent)
        self.setWindowTitle("区块选择说明")

        layout = QVBoxLayout(self)
        if MODES_SVG.is_file():
            view = QSvgWidget(str(MODES_SVG))
            size = view.renderer().defaultSize()
            if size.isEmpty():       # 读不到原始尺寸时按已知的 1240×576 兜底
                size.setWidth(1240)
                size.setHeight(576)
            view.setFixedSize(int(size.width() * scale), int(size.height() * scale))
            layout.addWidget(view)
        else:
            layout.addWidget(QLabel("找不到示意图：%s" % MODES_SVG))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 固定大小：不让它被拖动改形，也不留多余空白
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
