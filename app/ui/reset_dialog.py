"""「清空所有数据」对话框：勾要清哪几类，写清楚各自会没掉什么。

清空是应用自己的数据（设置、素材库、产物、日志），**不碰任何项目目录**——
项目里的东西归项目所有，要删去项目卡片上删。这一点在界面里必须说清楚，
否则"清空所有数据"看起来像是要把项目也一起抹了。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from .. import appdata
from .. import i18n
from ..storage import human_size
from . import design
from .widgets import wrap


class ResetDataDialog(QDialog):
    """选要清空哪几类数据；返回 `keys()` 给调用方执行。"""

    def __init__(self, app_dir: Path | str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("清空所有数据")
        self.setMinimumWidth(560)
        app_dir = Path(app_dir)

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_md)

        title = QLabel("清掉应用自己的数据，回到刚装好的状态")
        design.set_role(title, "subtitle")
        layout.addWidget(title)

        sizes = appdata.sizes(app_dir)
        self.boxes: dict[str, QCheckBox] = {}
        for category in appdata.CATEGORIES:
            box = QCheckBox(i18n.tr(category.label))
            box.setToolTip(i18n.tr(category.hint))
            box.setChecked(True)
            box.toggled.connect(self._sync)
            self.boxes[category.key] = box
            row = QHBoxLayout()
            row.addWidget(box)
            row.addWidget(QLabel("　—　%s" % i18n.tr(category.hint)), 1)
            row.addWidget(QLabel(human_size(sizes.get(category.key, 0))))
            layout.addLayout(row)

        self.total = QLabel()
        design.set_role(self.total, "hint")
        layout.addWidget(self.total)

        hint = QLabel(
            "项目目录不会被删除（包括里面的素材副本、贴图库、导出产物与历史记录）。\n"
            "要删项目，用项目卡片上的「删除项目」。"
        )
        wrap(hint)
        design.set_role(hint, "hint")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.btn_ok.setText("清空")
        design.set_variant(self.btn_ok, "danger")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sizes = sizes
        i18n.translate(self)
        self._sync()

    def keys(self) -> list[str]:
        return [key for key, box in self.boxes.items() if box.isChecked()]

    def _sync(self) -> None:
        chosen = self.keys()
        total = sum(self._sizes.get(key, 0) for key in chosen)
        self.total.setText(
            i18n.tr("将清空 %d 类，释放约 %s。") % (len(chosen), human_size(total))
        )
        self.btn_ok.setEnabled(bool(chosen))
