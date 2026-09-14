"""材质管理：两列列表，像 Minecraft 的资源包界面。

左 = 导入过但没启用的；右 = 本次启用的，**顺序就是叠加顺序**。
叠加顺序 = 优先级：**上面的先铺、下面的后铺，后铺的覆盖同名资源**——
这条要写在界面上，弄反了用户拿到的贴图轻重就全错了，且极难自己发现。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QEventLoop, QSize, QThread, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..library import KIND_LABELS, Library, import_source
from ..config import AppConfig
from ..materials import inspect_source, projects_using
from ..applog import logger
from ..sources import ARCHIVE_SUFFIXES
from . import design
from .widgets import wrap

ICON_SIZE = 32

# 阶段名 → 给用户看的中文（库发的是 parse/mesh/write）
STAGE_LABELS = {"parse": "解析", "mesh": "建网格", "write": "写出文件"}


class _Importer(QThread):
    """后台导入：解压一个客户端 jar 要十几秒，放主线程界面会冻住。

    （之前这里漏了——我给"选文件"那条旧路径加过线程，后来素材入口换成材质管理，
    管理界面里的导入是同步的，又把线程绕过去了。）
    """

    finished_with = Signal(object)   # Source，或捕到的 Exception

    def __init__(
        self,
        chosen: Path,
        app_dir: Path,
        work: Path,
        name: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._chosen = chosen
        self._app_dir = app_dir
        self._work = work
        self._name = name

    def run(self) -> None:
        try:
            self.finished_with.emit(
                import_source(
                    self._chosen, self._app_dir, self._work, name=self._name
                )
            )
        except Exception as error:
            self.finished_with.emit(error)


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

        hint = QLabel(
            "右边列表的顺序就是叠加顺序：<b>越靠下优先级越高</b>，"
            "下面的会覆盖上面的同名贴图。"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        wrap(hint)
        design.set_role(hint, "hint")
        root.addWidget(hint)

        columns = QHBoxLayout()
        root.addLayout(columns)

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("可用的素材"))
        self.available = self._make_list()
        left_box.addWidget(self.available)
        import_button = QPushButton("导入素材包")
        import_button.clicked.connect(self._import)
        left_box.addWidget(import_button)
        # 删除是"从素材库里移除"，属于左列的事；放右边会让人以为删的是"本次启用"
        self.btn_remove = QPushButton("从库中删除")
        self.btn_remove.clicked.connect(self._remove_from_library)
        left_box.addWidget(self.btn_remove)
        # 兜底：出了说不清的问题时，把库与缓存清空重来，比一点点排查快
        self.btn_clear = QPushButton("清空素材库")
        self.btn_clear.clicked.connect(self._clear_everything)
        self.btn_clear.setToolTip("删掉导入的素材与组合缓存，回到刚装好的状态")
        left_box.addWidget(self.btn_clear)
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
        wrap(self.status)
        design.set_role(self.status, "hint")
        root.addWidget(self.status)

        # 选中左边某个导入物时，这里说明它里面到底有什么（方块/模型/贴图/缺失）
        self.details = QLabel()
        wrap(self.details)
        design.set_role(self.details, "dim")
        root.addWidget(self.details)

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
        self._update_details()
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

    def _update_details(self) -> None:
        """把选中那个导入物的内容摘要显示出来（方块 / 模型 / 贴图 / 缺失）。

        看的是左列（素材库）；左列没选就看右列（本次启用），两边选的目标一样。
        """

        view = self.available if self.available.selectedItems() else self.selected
        items = view.selectedItems()
        if len(items) != 1:
            self.details.setText("")
            return
        source_id = items[0].data(Qt.ItemDataRole.UserRole)
        source = self.library.by_id(source_id)
        if source is None:
            self.details.setText("")
            return
        try:
            summary = inspect_source(Path(source.path))
        except OSError as error:
            self.details.setText("读不出内容：%s" % error)
            return
        text = "%s：%s" % (source.name, summary.render())
        # 素材库是全局的、项目只是引用它：删之前先说清哪些项目在用它
        try:
            config = AppConfig.load(self._app_dir / "config" / "app.json")
            users = projects_using(source.id, config.project_paths())
        except Exception:                     # 配置坏了也不该拖垮这里
            users = []
        if users:
            text += "\n被 %d 个项目绑定：%s" % (len(users), "、".join(users))
        self.details.setText(text)

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
        # 名字由用户定：默认取文件名，但允许改（素材库列表里显示的就是它）
        default_name = Path(chosen).stem
        name, accepted = QInputDialog.getText(
            self,
            "给这个素材起个名字",
            "这个名字会显示在素材库与项目绑定里。\n留空就用文件名：%s" % default_name,
            text=default_name,
        )
        if not accepted:
            return
        work = self._app_dir / "cache" / "sources"
        progress = QProgressDialog(
            "正在解压并识别…\n\n%s\n\n（客户端 jar 要十几秒）" % Path(chosen).name,
            "", 0, 0, self,
        )
        progress.setWindowTitle("导入素材")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()

        importer = _Importer(Path(chosen), self._app_dir, work, name=name, parent=self)
        result: dict = {}
        loop = QEventLoop()

        def finished(payload) -> None:
            result["payload"] = payload
            loop.quit()

        importer.finished_with.connect(finished)
        importer.start()
        loop.exec()          # 嵌套事件循环：界面照常重绘
        importer.wait()
        progress.close()

        payload = result.get("payload")
        if isinstance(payload, Exception):
            logger().exception("导入素材失败: %s", chosen)
            QMessageBox.warning(self, "导入失败", str(payload))
            return
        source = payload
        logger().info("导入素材: %s（识别为 %s）", chosen, source.kind)
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
        for source_id in ids:
            source = self.library.by_id(source_id)
            if source is None:
                continue
            self.library.disable(source_id)
            self.library.sources = [s for s in self.library.sources if s.id != source_id]
            shutil.rmtree(source.path, ignore_errors=True)
        self._refresh()

    def _clear_everything(self) -> None:
        """清空素材库与所有缓存。

        为什么要有这个：遇到说不清的问题时（贴图不对、类型识别错了、组合结果奇怪），
        让用户能一步回到干净状态重来，比让他去翻 resources/ 和 cache/ 目录可靠得多。
        """
        total = len(self.library.sources)
        if (
            QMessageBox.question(
                self,
                "清空重来",
                "将删除：\n"
                "  · 已导入的全部素材（%d 个）\n"
                "  · 组合缓存\n\n"
                "原始 zip / rar / jar 不会被删，之后可以重新导入。\n\n确定吗？"
                % total,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        # 清空是个大动作，必须留痕：不然"我的素材怎么没了"会变成一桩无头案
        # （用户就是这么撞上的：清空成功、日志里却一个字都没有）。
        logger().info("清空素材库：原有素材 %d 个，将删除解压结果与全部组合缓存", total)
        # 解压出来的素材、组合结果、图标缩略图、以及解压过程中的中间目录
        for target in (
            self._app_dir / "resources" / "sources",
            self._app_dir / "cache" / "packages",
            self._app_dir / "cache" / "icons",
            self._app_dir / "cache" / "sources",
        ):
            shutil.rmtree(target, ignore_errors=True)
        self.library = Library()
        self.library.save(self._app_dir)
        self._refresh()
        self.status.setText("已清空。原始压缩包还在，可以重新导入。")
        logger().info("清空完成：素材库与缓存已重置（原始压缩包未动）")

    # ---- 结束 ------------------------------------------------------------

    def accept(self) -> None:
        self.library.save(self._app_dir)
        super().accept()
