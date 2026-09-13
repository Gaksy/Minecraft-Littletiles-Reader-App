"""材质管理：两列列表，像 Minecraft 的资源包界面。

左 = 导入过但没启用的；右 = 本次启用的，**顺序就是叠加顺序**。
叠加顺序 = 优先级：**上面的先铺、下面的后铺，后铺的覆盖同名资源**——
这条要写在界面上，弄反了用户拿到的贴图轻重就全错了，且极难自己发现。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..library import KIND_LABELS, Library, import_source
from ..sources import ARCHIVE_SUFFIXES
from .theme import colors_for

ICON_SIZE = 32


class MaterialManagerDialog(QDialog):
    """返回时把启用顺序写回 `resources/index.json`。"""

    def __init__(self, app_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("材质管理")
        self._app_dir = app_dir
        self.library = Library.load(app_dir)
        self._build_ui()
        self._refresh()
        self.layout().setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

    # ---- 界面 ------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        muted = colors_for(self.palette()).muted.name()

        hint = QLabel(
            "右边列表的顺序就是叠加顺序：<b>越靠下优先级越高</b>，"
            "下面的会覆盖上面的同名贴图。"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s;" % muted)
        root.addWidget(hint)

        columns = QHBoxLayout()
        root.addLayout(columns)

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("可用的素材"))
        self.available = self._make_list()
        left_box.addWidget(self.available)
        import_button = QPushButton("导入 zip / rar / jar…")
        import_button.clicked.connect(self._import)
        left_box.addWidget(import_button)
        # 删除是"从素材库里移除"，属于左列的事；放右边会让人以为删的是"本次启用"
        self.btn_remove = QPushButton("从库中删除…")
        self.btn_remove.clicked.connect(self._remove_from_library)
        left_box.addWidget(self.btn_remove)
        columns.addLayout(left_box)

        middle = QVBoxLayout()
        middle.addStretch(1)
        for name, label, slot in (
            ("btn_enable", "启用 →", self._enable_selected),
            ("btn_disable", "← 停用", self._disable_selected),
            ("btn_up", "上移 ↑", lambda: self._move(-1)),
            ("btn_down", "下移 ↓", lambda: self._move(1)),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            setattr(self, name, button)
            middle.addWidget(button)
        middle.addStretch(1)
        columns.addLayout(middle)

        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("本次启用（上 → 下 = 优先级递增）"))
        self.selected = self._make_list()
        right_box.addWidget(self.selected)
        columns.addLayout(right_box)

        self.status = QLabel()
        self.status.setStyleSheet("color:%s;" % muted)
        root.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _make_list(self) -> QListWidget:
        view = QListWidget()
        view.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        view.setMinimumWidth(260)
        view.setMinimumHeight(220)
        view.itemSelectionChanged.connect(self._update_buttons)
        return view

    def _update_buttons(self) -> None:
        """按当前选择决定哪些能点——点不动的时候就该是灰的。"""
        has_left = bool(self.available.selectedItems())
        has_right = bool(self.selected.selectedItems())
        self.btn_enable.setEnabled(has_left)
        self.btn_disable.setEnabled(has_right)
        self.btn_remove.setEnabled(has_left)      # 只有左列能删

        rows = sorted(self.selected.row(item) for item in self.selected.selectedItems())
        # 原版钉在 0，所以上移的下界是 1
        base = self.library.base
        pinned = (
            base is not None
            and bool(self.library.enabled)
            and self.library.enabled[0] == base.id
        )
        self.btn_up.setEnabled(bool(rows) and min(rows) > (1 if pinned else 0))
        self.btn_down.setEnabled(bool(rows) and max(rows) < self.selected.count() - 1)

    # ---- 列表刷新 --------------------------------------------------------

    def _fill(self, view: QListWidget, sources) -> None:
        view.clear()
        for source in sources:
            item = QListWidgetItem(
                "%s\n%s" % (source.name, source.kind_label)
            )
            item.setData(Qt.ItemDataRole.UserRole, source.id)
            if source.icon and Path(source.icon).is_file():
                item.setIcon(QIcon(source.icon))
            view.addItem(item)

    def _refresh(self) -> None:
        self._fill(self.available, self.library.available())
        self._fill(self.selected, self.library.selected())
        base = self.library.base
        if not self.library.selected():
            self.status.setText("还没有启用任何素材——导出会是白模。")
        elif base is None:
            self.status.setText(
                "注意：没有启用「原版」——它是映射表的底，缺了它导不出带贴图的模型。"
            )
        else:
            self.status.setText(
                "底包：%s　启用 %d 项"
                % (base.name, len(self.library.selected()))
            )
        self._update_buttons()

    def _selected_ids(self, view: QListWidget) -> list[str]:
        return [
            item.data(Qt.ItemDataRole.UserRole) for item in view.selectedItems()
        ]

    # ---- 操作 ------------------------------------------------------------

    def _enable_selected(self) -> None:
        for source_id in self._selected_ids(self.available):
            self.library.enable(source_id)
        self._refresh()

    def _disable_selected(self) -> None:
        for source_id in self._selected_ids(self.selected):
            self.library.disable(source_id)
        self._refresh()

    def _move(self, delta: int) -> None:
        for source_id in self._selected_ids(self.selected):
            self.library.move(source_id, delta)
        self._refresh()
        # 移动后保持选中，方便连续点
        ids = set(self._selected_ids(self.selected))
        for row in range(self.selected.count()):
            item = self.selected.item(row)
            if item.data(Qt.ItemDataRole.UserRole) in ids:
                item.setSelected(True)

    def _import(self) -> None:
        patterns = " ".join("*%s" % s for s in ARCHIVE_SUFFIXES)
        chosen, _ = QFileDialog.getOpenFileName(
            self, "导入素材（zip / rar / jar）", "", "压缩包 (%s)" % patterns
        )
        if not chosen:
            return
        work = self._app_dir / "cache" / "sources"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            source = import_source(Path(chosen), self._app_dir, work)
        except Exception as error:
            QMessageBox.warning(self, "导入失败", str(error))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.library.add(source)
        # 原版直接启用（它是底，不启用没用）；其余留给用户决定顺序
        if source.kind == "vanilla" and not self.library.selected():
            self.library.enable(source.id)
        self._refresh()
        if source.kind == "unknown":
            QMessageBox.information(
                self,
                "认不出这个文件",
                "已导入但没识别出类型：\n%s" % chosen,
            )

    def _remove_from_library(self) -> None:
        # 只认左列的选择：右列是"本次启用"，不是"要删的东西"
        ids = self._selected_ids(self.available)
        if not ids:
            return
        names = ", ".join(
            self.library.by_id(i).name for i in ids if self.library.by_id(i)
        )
        if (
            QMessageBox.question(
                self,
                "从库中删除",
                "把以下素材从库中移除（解压出来的文件也会删掉）？\n\n%s" % names,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        import shutil

        for source_id in ids:
            source = self.library.by_id(source_id)
            if source is None:
                continue
            self.library.disable(source_id)
            self.library.sources = [s for s in self.library.sources if s.id != source_id]
            shutil.rmtree(source.path, ignore_errors=True)
        self._refresh()

    # ---- 结束 ------------------------------------------------------------

    def accept(self) -> None:
        self.library.save(self._app_dir)
        super().accept()
