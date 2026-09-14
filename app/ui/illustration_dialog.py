"""区块选择说明：三种模式各画一张示意图（`chunk_modes_art.py` 现画）。

为什么不再贴那张固定配色的 SVG：深色主题下白底图太扎眼。现画的颜色全部取自
`design.theme()`，深浅两套自动跟随（原 SVG 已删，见 docs/design.md）。

只读、固定大小。放在独立窗口而不是常驻在导出对话框里——图很大，
常驻会把导出对话框撑得又宽又空。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from . import design
from .chunk_modes_art import ChunkModesIllustration


class IllustrationDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("区块选择说明")

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_md)
        self.art = ChunkModesIllustration(self)
        layout.addWidget(self.art)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 固定大小：不让它被拖动改形，也不留多余空白
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        i18n.translate(self)
