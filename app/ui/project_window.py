"""项目工作界面：这个项目的一切都在这一页（设计文档 §5）。

结构（从上到下）：

    封面 / 名称 / 描述 / 目录        组合状态 + 重新组合
    [导出 OBJ 模型]  [导出 SNBT]      ← 上方大部分区域，最常按的两个
    存档：默认存档地址 + [备份存档]
    素材：绑定的材质包与模组（有序，越靠下越优先）
    历史记录：每次导出的时间、区块、产物；可打开、可删、可查区块状态
    存储：一条按颜色分段的容量条 + 图例（§7.8）
    进度与日志（和主界面同一块面板）

两条纪律：

* **项目模式下不再问"用什么材质"**——项目就一套素材组合（§0 第 6 条），
  每次导出都弹一遍是纯打扰。要换就去改项目里的素材绑定。
* 导出产物按时间戳新建目录（`next_output_dir`），只往里写，不覆盖旧的。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ltgen import paths

from .. import i18n
from ..applog import logger
from ..compose import ComposeError
from ..config import APP_DIR, AppConfig
from ..job import (
    CHUNK_MODE_LABELS,
    CHUNK_MODES,
    DIMENSION_LABELS,
    DIMENSIONS,
    build_snbt_job,
    default_options,
    expand_chunks,
)
from ..library import KIND_MOD, KIND_VANILLA, KIND_LABELS, Library
from ..project import Project
from ..project_assets import bound_library, ensure_package, missing_bindings
from ..records import (
    STATE_LABELS,
    ExportRecord,
    RecordStore,
    is_inside,
    stamps_for,
)
from ..retention import plan as retention_plan, policy_active
from ..storage import categories, human_size, percent
from ..storage import CATEGORY_PATHS
from ..texture_library import absorb, library_path, orphans, prune
from .background import run_in_background
from .chunk_grid import NO_CELL, ChunkMapView, ChunkStateGrid
from .export_dialog import ExportRegionDialog
from .export_panel import ExportPanel
from .storage_bar import Segment, StorageBar, StorageLegend
from . import design
from . import popup
from .snbt_source import choose_snbt_source, save_pasted_snbt
from .widgets import ClickableLabel, wrap

# 封面"清除"的哨兵值：和"没改过（空串）"、"选了新文件（路径）"区分开
_COVER_CLEAR = "__clear__"

# 导出概览：以"导过的区块"为中心向外几格；单边最多画多少格（再大靠拖动看）
OVERVIEW_RADIUS = 5
OVERVIEW_MAX = 96


class _BindingPicker(QDialog):
    """从素材库里挑要绑进项目的素材（可多选）。"""

    def __init__(self, sources, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("添加素材到项目"))
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "从素材库里选（导入新素材请用「素材 → 材质管理」）：\n"
                "绑定会把素材**复制一份**进项目目录，之后项目搬到哪都能用。"
            )
        )
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setMinimumSize(420, 260)
        for source in sources:
            item = QListWidgetItem(
                "%s（%s）" % (source.name, i18n.tr(source.kind_label))
            )
            item.setData(Qt.ItemDataRole.UserRole, source.id)
            if source.icon and Path(source.icon).is_file():
                item.setIcon(QIcon(source.icon))
            self.list.addItem(item)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.translate(self)

    def chosen_ids(self) -> list[str]:
        return [
            item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()
        ]


class _BackupsDialog(QDialog):
    """存档备份的副本管理：看清单、打开、删（§7.7：删之前先把释放多少说清楚）。"""

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("存档备份"))
        self._project = project
        layout = QVBoxLayout(self)
        hint = QLabel(
            "每次备份都是**整个存档**打成的 zip，放在 <项目>/inputs/saves/。\n"
            "删除只影响这份备份，原始存档不受影响。"
        )
        wrap(hint)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["时间", "名字", "大小"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumSize(520, 240)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.btn_open = QPushButton("打开所在目录")
        self.btn_open.clicked.connect(self._open_folder)
        self.btn_delete = QPushButton("删除选中")
        self.btn_delete.clicked.connect(self._delete)
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_delete)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.translate(self)
        self._refresh()

    def _refresh(self) -> None:
        backups = self._project.backups()
        self.table.setRowCount(len(backups))
        for row, item in enumerate(backups):
            size = item.stat().st_size if item.is_file() else 0
            for column, text in enumerate(
                (item.name.split("_")[0], item.name, human_size(size))
            ):
                cell = QTableWidgetItem(text)
                cell.setData(Qt.ItemDataRole.UserRole, str(item))
                self.table.setItem(row, column, cell)
        self.table.resizeColumnsToContents()
        has = bool(backups)
        self.btn_open.setEnabled(has)
        self.btn_delete.setEnabled(has)

    def _selected(self) -> list[Path]:
        result = []
        for index in self.table.selectionModel().selectedRows():
            cell = self.table.item(index.row(), 0)
            if cell is not None:
                result.append(Path(cell.data(Qt.ItemDataRole.UserRole)))
        return result

    def _open_folder(self) -> None:
        from .export_panel import default_open_directory

        folder = self._project.path / "inputs" / "saves"
        if folder.is_dir():
            default_open_directory(folder)

    def _delete(self) -> None:
        targets = [item for item in self._selected() if item.is_file()]
        if not targets:
            return
        freed = sum(item.stat().st_size for item in targets)
        if (
            popup.ask(
                self,
                "删除备份",
                "删掉这 %d 份备份？\n\n将释放约 %s。存档本身不受影响。"
                % (len(targets), human_size(freed)),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        for item in targets:
            item.unlink(missing_ok=True)
        logger().info("删除存档备份：%d 份，释放 %d 字节", len(targets), freed)
        self._refresh()


class _ProjectConfigDialog(QDialog):
    """项目配置：名称、简介、封面、项目目录、默认存档位置。

    工作界面上这些内容只做展示——看得到、按不坏，要改就进这个弹窗
    （用户的诉求：项目名/简介/目录默认直接显示，点「项目配置」才能改）。

    「移动项目」是搬整个目录的重活，仍旧走外面那套流程（登记表、记录索引
    都要跟着更新），这里只负责把路径显示跟着刷新。
    """

    def __init__(self, project: Project, on_move, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("项目配置"))
        self.setMinimumWidth(560)
        self.project = project
        self._on_move = on_move
        self._cover = ""                 # 选了新封面先记着，点确定才落地
        self._save_root = project.save_root

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_md)

        form = QFormLayout()
        self.name_edit = QLineEdit(project.name)
        self.name_edit.setPlaceholderText("项目名")
        form.addRow("名称", self.name_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("简介"))
        self.description_edit = QPlainTextEdit(project.description)
        self.description_edit.setPlaceholderText("这个项目是做什么的")
        self.description_edit.setFixedHeight(72)
        layout.addWidget(self.description_edit)

        cover_row = QHBoxLayout()
        self.cover_preview = QLabel()
        self.cover_preview.setFixedSize(64, 64)
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_row.addWidget(self.cover_preview)
        self.btn_cover = QPushButton("选择封面图片")
        self.btn_cover.clicked.connect(self._pick_cover)
        self.btn_cover_clear = QPushButton("清除封面")
        self.btn_cover_clear.clicked.connect(self._clear_cover)
        cover_row.addWidget(self.btn_cover)
        cover_row.addWidget(self.btn_cover_clear)
        cover_row.addStretch(1)
        layout.addLayout(cover_row)

        self.directory_label = QLabel()
        wrap(self.directory_label)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.directory_label, 1)
        self.btn_move = QPushButton("移动项目")
        self.btn_move.setToolTip("把整个项目目录搬到别处，素材副本、记录、产物一起走")
        self.btn_move.clicked.connect(self._move)
        dir_row.addWidget(self.btn_move)
        layout.addLayout(dir_row)

        self.save_label = QLabel()
        wrap(self.save_label)
        save_row = QHBoxLayout()
        save_row.addWidget(self.save_label, 1)
        self.btn_pick_save = QPushButton("选择文件夹")
        self.btn_pick_save.setToolTip("选含 level.dat 的那个存档文件夹")
        self.btn_pick_save.clicked.connect(self._pick_save)
        self.btn_clear_save = QPushButton("清除")
        self.btn_clear_save.clicked.connect(self._clear_save)
        save_row.addWidget(self.btn_pick_save)
        save_row.addWidget(self.btn_clear_save)
        layout.addLayout(save_row)

        hint = QLabel("存档位置只影响这个项目的默认值，导出时仍旧可以改。")
        wrap(hint)
        design.set_role(hint, "hint")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.translate(self)
        self._refresh()

    # ---- 显示 ----

    def _refresh(self) -> None:
        self.directory_label.setText(i18n.tr("项目目录：%s") % self.project.path)
        self.save_label.setText(
            i18n.tr("默认存档：%s") % (self._save_root or i18n.tr("（未设置）"))
        )
        self.btn_clear_save.setEnabled(bool(self._save_root))
        self._refresh_cover()

    def _refresh_cover(self) -> None:
        theme = design.theme()
        dashed = (
            "border:%dpx dashed %s; color:%s;"
            % (design.METRICS.border_width, theme.border, theme.text_3)
        )
        if self._cover == _COVER_CLEAR:
            self.cover_preview.setPixmap(QPixmap())
            self.cover_preview.setText(i18n.tr("无封面"))
            self.cover_preview.setStyleSheet(dashed)
            self.btn_cover_clear.setEnabled(False)
            return
        if self._cover:
            # 选了新图但还没确定：直接用文件里的像素预览
            self.cover_preview.setPixmap(
                QPixmap(self._cover).scaled(
                    64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.cover_preview.setStyleSheet(
                "border:%dpx solid %s;" % (design.METRICS.border_width, theme.border)
            )
            self.btn_cover_clear.setEnabled(True)
            return
        cover = self.project.cover_png()
        if cover is None:
            self.cover_preview.setPixmap(QPixmap())
            self.cover_preview.setText(i18n.tr("无封面"))
            self.cover_preview.setStyleSheet(dashed)
            self.btn_cover_clear.setEnabled(False)
            return
        self.cover_preview.setPixmap(
            QPixmap(str(cover)).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.cover_preview.setText("")
        self.cover_preview.setStyleSheet(
            "border:%dpx solid %s;" % (design.METRICS.border_width, theme.border)
        )
        self.btn_cover_clear.setEnabled(True)

    # ---- 交互 ----

    def _pick_cover(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", "图片 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)"
        )
        if not chosen:
            return
        self._cover = chosen
        self._refresh_cover()

    def _clear_cover(self) -> None:
        self._cover = _COVER_CLEAR       # 哨兵：确定时把封面删掉
        self._refresh_cover()

    def _move(self) -> None:
        self._on_move()
        self._refresh()

    def _pick_save(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择存档根目录")
        if not chosen:
            return
        self._save_root = chosen
        self._refresh()

    def _clear_save(self) -> None:
        self._save_root = ""
        self._refresh()

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "description": self.description_edit.toPlainText(),
            "save_root": self._save_root,
            "cover": self._cover,
        }


class _RetentionDialog(QDialog):
    """保留策略：只保留最近 N 次 / 超过 X 天 / 总大小上限。默认一条都不开。"""

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("保留策略"))
        layout = QVBoxLayout(self)
        hint = QLabel(
            "默认什么都不自动删。下面几条按需打开——命中的旧导出会连产物目录一起清理，\n"
            "记录索引与 SNBT 输入副本永远保留。"
        )
        wrap(hint)
        layout.addWidget(hint)

        form = QFormLayout()
        self.keep = QSpinBox()
        self.keep.setRange(0, 9999)
        self.keep.setSpecialValueText("不限")
        self.keep.setSuffix(" 次")
        self.keep.setValue(int(project.keep_exports or 0))
        form.addRow("只保留最近", self.keep)

        self.days = QSpinBox()
        self.days.setRange(0, 3650)
        self.days.setSpecialValueText("不限")
        self.days.setSuffix(" 天")
        self.days.setValue(int(project.keep_days or 0))
        form.addRow("只保留最近", self.days)

        self.size = QSpinBox()
        self.size.setRange(0, 1024 * 1024)
        self.size.setSpecialValueText("不限")
        self.size.setSuffix(" MB")
        self.size.setValue(int(project.keep_size_mb or 0))
        form.addRow("总大小不超过", self.size)
        layout.addLayout(form)

        self.auto = QCheckBox("打开项目时自动按策略清理（会先问一次）")
        self.auto.setChecked(bool(project.auto_clean))
        layout.addWidget(self.auto)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        i18n.translate(self)

    def values(self) -> dict:
        return {
            "keep_exports": self.keep.value(),
            "keep_days": self.days.value(),
            "keep_size_mb": self.size.value(),
            "auto_clean": self.auto.isChecked(),
        }


class _ChunkSearchDialog(QDialog):
    """按区块坐标搜记录：这个 (x, z) 导过吗、哪几次、产物在哪。

    以前这里是"画一个范围的网格"，导出概览接管那件事之后就没意义了；
    真正还缺的是"我手上有块坐标，想找到当时那条记录"。所以按坐标直接搜，
    结果是一张表，选中一条能直接打开产物目录。
    """

    def __init__(
        self,
        project: Project,
        store: RecordStore,
        parent=None,
        initial: tuple[int, int, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("搜索区块记录"))
        self._project = project
        self._store = store

        root = QVBoxLayout(self)
        root.setSpacing(design.METRICS.gap_sm)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        row.addWidget(QLabel(i18n.tr("区块坐标")))
        self.x = self._spin()
        self.z = self._spin()
        row.addWidget(self.x)
        row.addWidget(self.z)
        row.addWidget(QLabel(i18n.tr("维度")))
        self.dimension = QComboBox()
        self.dimension.addItem(i18n.tr("全部维度"), "")
        for value in DIMENSIONS:
            self.dimension.addItem(i18n.tr(DIMENSION_LABELS[value]), value)
        row.addWidget(self.dimension)
        search = QPushButton(i18n.tr("搜索"))
        search.clicked.connect(self._search)
        row.addWidget(search)
        row.addStretch(1)
        root.addLayout(row)

        self.result = QLabel()
        wrap(self.result)
        design.set_role(self.result, "hint")
        root.addWidget(self.result)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            i18n.tr_all(["时间", "类型", "维度", "名称", "面数", "贴图", "大小"])
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        for column, width in ((0, 152), (1, 64), (2, 90), (4, 76), (5, 84), (6, 88)):
            self.table.setColumnWidth(column, width)
        self.table.setMinimumSize(760, 260)
        self.table.itemSelectionChanged.connect(self._sync)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.btn_open = QPushButton(i18n.tr("打开产物目录"))
        self.btn_open.clicked.connect(self._open_output)
        buttons.addWidget(self.btn_open)
        buttons.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        root.addLayout(buttons)

        if initial is not None:
            self.x.setValue(int(initial[0]))
            self.z.setValue(int(initial[1]))
            index = self.dimension.findData(initial[2]) if len(initial) > 2 else -1
            if index >= 0:
                self.dimension.setCurrentIndex(index)
        self._sync()
        i18n.translate(self)
        self.resize(920, 520)
        self._search()

    @staticmethod
    def _spin() -> QSpinBox:
        box = QSpinBox()
        box.setRange(-100000, 100000)
        return box

    def _search(self) -> None:
        x, z = self.x.value(), self.z.value()
        dimension = self.dimension.currentData()
        found = [
            record
            for record in self._store.records
            if record.kind == "region"
            and (x, z) in {(int(cx), int(cz)) for cx, cz in record.chunks}
            and (not dimension or record.dimension == dimension)
        ]
        self.table.setRowCount(len(found))
        for row, record in enumerate(found):
            values = [
                record.created_at,
                i18n.tr(record.kind_label),
                DIMENSION_LABELS.get(record.dimension, record.dimension),
                record.name,
                str(record.faces or "—"),
                self._textures(record),
                human_size(record.size_bytes(self._project.path)),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(i18n.tr(text) if column in (1, 2) else text)
                if column in (4, 5, 6):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, record.id)
        if found:
            self.result.setText(
                i18n.tr("找到 %d 条记录：区块 (%d, %d)") % (len(found), x, z)
            )
        else:
            self.result.setText(
                i18n.tr("没有找到记录：区块 (%d, %d) 还没有导出过。") % (x, z)
            )
        self.table.clearSelection()
        self._sync()

    def _textures(self, record) -> str:
        if not record.textures:
            return "—"
        missing = [
            digest
            for digest in record.textures
            if not library_path(self._project.path, digest).is_file()
        ]
        if missing:
            return i18n.tr("%d 张（缺 %d）") % (len(record.textures), len(missing))
        return i18n.tr("%d 张") % len(record.textures)

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return None
        return self._store.by_id(item.data(Qt.ItemDataRole.UserRole))

    def _sync(self) -> None:
        self.btn_open.setEnabled(self._selected() is not None)

    def _open_output(self) -> None:
        record = self._selected()
        if record is None:
            return
        from .export_panel import default_open_directory

        target = self._project.path / record.output_dir
        if target.is_dir():
            default_open_directory(target)
        else:
            popup.info(
                self,
                i18n.tr("没有产物"),
                i18n.tr("这条记录的产物目录不在了：\n%s") % target,
            )


class ProjectWindow(QMainWindow):
    """一个项目的工作界面。关掉时发 `closed`，让启动界面刷新项目列表。"""

    closed = Signal()

    def __init__(
        self,
        project: Project,
        config: AppConfig,
        app_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.config = config
        self.app_dir = Path(app_dir or APP_DIR)
        self.store = RecordStore(project.path)
        self._pending: ExportRecord | None = None
        self._rebuild_record: ExportRecord | None = None
        self._force_recompose = False
        self._faded_in = False

        self.setWindowTitle("项目 · %s" % project.name)
        self.resize(1000, 760)
        self._build_ui()
        self._refresh_all()
        # 保留策略要在窗口显示之后再问（构造期间弹模态框，父窗口还没出来）
        QTimer.singleShot(0, self._auto_clean_if_needed)
        logger().info("打开项目：%s（%s）", project.name, project.path)

    # ---- 界面 ------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """第一次显示时淡入一次。"""

        super().showEvent(event)
        if not self._faded_in:
            self._faded_in = True
            design.motion.fade_in(self.centralWidget())

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)

        layout.addWidget(self._build_header())

        # 上方大部分区域 = 两个导出入口
        exports = QHBoxLayout()
        self.btn_export_region = QPushButton("导出 OBJ 模型\n（从存档选区块）")
        self.btn_export_snbt = QPushButton("导出 SNBT\n（结构文件 / 粘贴文本）")
        for button in (self.btn_export_region, self.btn_export_snbt):
            exports.addWidget(button, 1)
        layout.addLayout(exports)
        self.btn_export_region.clicked.connect(self._export_region)
        self.btn_export_snbt.clicked.connect(self._export_snbt)

        layout.addWidget(self._build_save_box())
        layout.addWidget(self._build_material_box())
        layout.addWidget(self._build_history_box())
        layout.addWidget(self._build_overview_box())
        layout.addWidget(self._build_storage_box())
        layout.addStretch(1)

        # 进度与日志放底部：常驻可见，但不跟配置抢地方
        self.panel = ExportPanel(self.config, self.app_dir, self)
        self.panel.finished_ok.connect(self._on_export_finished)
        self.panel.log_view.setMaximumHeight(150)
        outer.addWidget(self.panel, 0)

        self.setCentralWidget(central)
        self._build_menu()
        self._apply_button_style()
        i18n.translate(self)

    def _build_header(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(design.METRICS.gap_md)

        self.cover = ClickableLabel()
        self.cover.setFixedSize(96, 96)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover.setToolTip("点一下换封面")
        self.cover.clicked.connect(self._change_cover)
        row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)

        fields = QVBoxLayout()
        fields.setSpacing(design.METRICS.gap_sm)

        # 名称 / 简介 / 目录都是只读展示：改内容统一走「项目配置」弹窗
        self.name_label = QLabel()
        wrap(self.name_label)
        design.set_role(self.name_label, "title")
        fields.addWidget(self.name_label)

        self.description_label = QLabel()
        wrap(self.description_label)
        design.set_role(self.description_label, "hint")
        self.description_label.setMinimumHeight(34)
        fields.addWidget(self.description_label)

        path_row = QHBoxLayout()
        path_row.setSpacing(design.METRICS.gap_sm)
        self.directory_label = QLabel()
        wrap(self.directory_label)      # 路径很长，不折行会把整页撑宽
        self.directory_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        design.set_role(self.directory_label, "dim")
        open_button = QPushButton("打开目录")
        open_button.clicked.connect(lambda: self._open_path(self.project.path))
        self.btn_project_config = QPushButton("项目配置")
        self.btn_project_config.setToolTip("改名称、简介、封面、项目目录与默认存档位置")
        self.btn_project_config.clicked.connect(self._edit_project_config)
        path_row.addWidget(self.directory_label, 1)
        path_row.addWidget(open_button)
        path_row.addWidget(self.btn_project_config)
        fields.addLayout(path_row)
        row.addLayout(fields, 1)
        return box

    def _build_save_box(self) -> QGroupBox:
        box = QGroupBox("存档")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        row.addWidget(QLabel("默认存档位置"))
        # 只显示位置：改位置在「项目配置」里
        self.save_label = QLabel()
        wrap(self.save_label)
        self.save_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        design.set_role(self.save_label, "dim")
        row.addWidget(self.save_label, 1)
        layout.addLayout(row)

        backup_row = QHBoxLayout()
        backup_row.setSpacing(design.METRICS.gap_sm)
        self.btn_backup = QPushButton("备份存档")
        self.btn_backup.setToolTip("把整个存档打成一个 zip 存进项目目录（inputs/saves/）")
        self.btn_backup.clicked.connect(self._backup_save)
        self.btn_backups = QPushButton("管理备份")
        self.btn_backups.setToolTip("看已有的备份、打开、删掉不想留的")
        self.btn_backups.clicked.connect(self._manage_backups)
        self.backup_label = QLabel()
        wrap(self.backup_label)
        design.set_role(self.backup_label, "hint")
        backup_row.addWidget(self.btn_backup)
        backup_row.addWidget(self.btn_backups)
        backup_row.addWidget(self.backup_label, 1)
        layout.addLayout(backup_row)
        return box

    def _build_material_box(self) -> QGroupBox:
        box = QGroupBox("素材（本项目绑定：材质包 / 模组，越靠下优先级越高）")
        layout = QVBoxLayout(box)

        self.bindings = QListWidget()
        self.bindings.setMinimumHeight(96)
        self.bindings.setMaximumHeight(150)     # 列表默认爱吃满剩余空间，把整页撑得很长
        layout.addWidget(self.bindings)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        for name, label, slot in (
            ("btn_add_material", "添加素材", self._add_materials),
            ("btn_remove_material", "从项目移除", self._remove_material),
            ("btn_material_up", "上移 ↑", lambda: self._move_material(-1)),
            ("btn_material_down", "下移 ↓", lambda: self._move_material(1)),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            setattr(self, name, button)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

        # 组合状态与「重新组合素材」跟着素材放（用户：组合本来就该和素材在一栏）
        layout.addWidget(design.separator())
        status_row = QHBoxLayout()
        status_row.setSpacing(design.METRICS.gap_sm)
        self.package_status = QLabel()
        wrap(self.package_status)
        # 别被挤成竖条：这行文字在窄列里会一个字一行（中文没有空格），
        # 给个下限宽度、并让它吃右侧剩余空间（原先固定 0 拉伸）。
        self.package_status.setMinimumWidth(220)
        status_row.addWidget(self.package_status, 1)
        self.btn_recompose = QPushButton("重新组合素材")
        self.btn_recompose.clicked.connect(lambda: self._compose(force=True, report=True))
        status_row.addWidget(self.btn_recompose)
        layout.addLayout(status_row)
        return box

    def _build_history_box(self) -> QGroupBox:
        box = QGroupBox("历史记录")
        layout = QVBoxLayout(box)

        self.history = QTableWidget(0, 7)
        self.history.setHorizontalHeaderLabels(
            i18n.tr_all(["时间", "类型", "名称", "区块", "面数", "贴图", "大小"])
        )
        self.history.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setMinimumHeight(140)
        self.history.setMaximumHeight(200)      # 同上：表格的 sizeHint 也是 256 起步
        self.history.verticalHeader().setVisible(False)
        # 列宽按内容类型分：时间/类型/数字是固定宽度的短内容，名称与区块会很长、
        # 让它们吃剩余空间。以前是"内容撑 + 最后一列拉伸"，结果数字列被挤得站不住、
        # "大小"却吃掉半张表。
        header = self.history.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(56)
        for column, mode in (
            (0, QHeaderView.ResizeMode.Fixed),        # 时间：YYYY-MM-DD HH:MM:SS
            (1, QHeaderView.ResizeMode.Fixed),        # 类型：存档 / 结构
            (2, QHeaderView.ResizeMode.Stretch),      # 名称：最长的那个
            (3, QHeaderView.ResizeMode.Stretch),      # 区块：c12_-3_r1 这类
            (4, QHeaderView.ResizeMode.Fixed),        # 面数
            (5, QHeaderView.ResizeMode.Fixed),        # 贴图
            (6, QHeaderView.ResizeMode.Fixed),        # 大小
        ):
            header.setSectionResizeMode(column, mode)
        for column, width in ((0, 152), (1, 64), (4, 76), (5, 84), (6, 88)):
            self.history.setColumnWidth(column, width)
        # 选中才有对象的动作要跟着选中状态亮/灭
        self.history.itemSelectionChanged.connect(self._update_history_buttons)
        layout.addWidget(self.history)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        for name, label, slot in (
            ("btn_open_output", "打开产物目录", self._open_selected_output),
            ("btn_open_job", "打开 job.json", self._open_selected_job),
            ("btn_pack", "打包成 zip", self._pack_selected),
            # 「重建贴图」实际是拿 job.json 回库重跑一遍，叫「重新导出模型」才如实
            ("btn_rebuild", "重新导出模型", self._rebuild_selected),
            ("btn_query", "搜索区块记录", self._search_chunks),
            ("btn_delete", "删除记录", self._delete_selected),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            setattr(self, name, button)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        return box

    def _build_overview_box(self) -> QGroupBox:
        """导出概览：这个项目**导过哪些区块**，一张能拖的图（§6、§7.2）。

        与导出对话框里那块不一样：那块画的是"这次要导的范围"，这里画的是
        **已经导过的记录**——以数据的中心向外 5 格，悬停看坐标，点一格看这一块的
        详情（什么时候导的、多少面、产物在哪）。图大了能拖着看。
        """

        box = QGroupBox("导出概览")
        layout = QVBoxLayout(box)
        layout.setSpacing(design.METRICS.gap_sm)

        head = QHBoxLayout()
        head.setSpacing(design.METRICS.gap_sm)
        head.addWidget(QLabel("维度"))
        self.overview_dimension = QComboBox()
        self.overview_dimension.currentIndexChanged.connect(
            lambda _index: self._refresh_overview()
        )
        head.addWidget(self.overview_dimension)
        self.overview_size = QLabel()
        design.set_role(self.overview_size, "subtitle")
        head.addWidget(self.overview_size)
        legend = QLabel(
            "灰 = 没导过　绿 = 已导出且存档未变　黄 = 已导出但之后存档变过"
        )
        wrap(legend)
        design.set_role(legend, "hint")
        head.addWidget(legend, 1)
        layout.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        self.overview_map = ChunkMapView(cell=18, max_cells=OVERVIEW_MAX)
        self.overview_map.setMinimumHeight(200)
        self.overview_map.setMaximumHeight(260)
        self.overview_map.hovered.connect(self._on_overview_hover)
        self.overview_map.clicked.connect(self._on_overview_clicked)
        row.addWidget(self.overview_map, 1)

        detail_card, detail_layout = design.card(padding=design.METRICS.gap_sm)
        detail_card.setFixedWidth(260)
        self.overview_detail = QLabel()
        self.overview_detail.setWordWrap(True)
        self.overview_detail.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.overview_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.overview_detail)
        # 点到有记录的区块 → 一键去搜这个坐标的记录（两处信息对得上）
        self.btn_overview_search = QPushButton(i18n.tr("查看这个区块的记录"))
        self.btn_overview_search.setEnabled(False)
        self.btn_overview_search.clicked.connect(self._search_picked_chunk)
        detail_layout.addWidget(self.btn_overview_search)
        detail_layout.addStretch(1)
        row.addWidget(detail_card, 0)
        layout.addLayout(row, 1)

        self.overview_hover = QLabel()
        wrap(self.overview_hover)
        design.set_role(self.overview_hover, "hint")
        layout.addWidget(self.overview_hover)
        return box

    def _build_storage_box(self) -> QGroupBox:
        box = QGroupBox("存储")
        layout = QVBoxLayout(box)
        self.storage_total = QLabel()
        wrap(self.storage_total)
        layout.addWidget(self.storage_total)
        self.storage_bar = StorageBar()
        layout.addWidget(self.storage_bar)
        self.storage_legend = StorageLegend()
        self.storage_legend.hovered.connect(self.storage_bar.set_highlight)
        self.storage_bar.hovered.connect(self.storage_legend_hover)
        self.storage_legend.clicked.connect(self._open_category)
        layout.addWidget(self.storage_legend)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        self.btn_prune = QPushButton("清理未引用贴图")
        self.btn_prune.setToolTip(
            "删掉贴图库里没有任何导出记录引用的图（不会删产物与记录）"
        )
        self.btn_prune.clicked.connect(self._prune_textures)
        self.btn_clean_outputs = QPushButton("清理旧产物")
        self.btn_clean_outputs.clicked.connect(self._clean_outputs)
        self.btn_retention = QPushButton("保留策略")
        self.btn_retention.setToolTip(
            "只保留最近 N 次 / 超过 X 天 / 总大小上限；默认什么都不自动删"
        )
        self.btn_retention.clicked.connect(self._edit_retention)
        row.addWidget(self.btn_prune)
        row.addWidget(self.btn_clean_outputs)
        row.addWidget(self.btn_retention)
        row.addStretch(1)
        layout.addLayout(row)

        self.retention_label = QLabel()
        wrap(self.retention_label)
        design.set_role(self.retention_label, "hint")
        layout.addWidget(self.retention_label)
        return box

    def storage_legend_hover(self, index: int) -> None:
        """条上悬停 → 图例那一行也淡出/高亮，两边指向同一个类别。"""
        # 注意：storage_legend 是控件（StorageLegend），不是布局——
        # 早先这里对它调 itemAt()，每次悬停都抛 AttributeError。
        for row_index, row in enumerate(self.storage_legend.rows()):
            row.set_dimmed(index >= 0 and index != row_index)

    # ---- 导出概览（这个项目导过哪些区块） --------------------------------

    def _refresh_overview(self) -> None:
        """画出"导过哪些区块"：以数据为中心向外 5 格，越界不画。"""

        records = [r for r in self.store.records if r.kind == "region" and r.chunks]
        dimensions: list[str] = []
        for record in records:              # records 已是新的在前
            if record.dimension not in dimensions:
                dimensions.append(record.dimension)

        # 维度下拉：只列真正有记录的维度，尽量保持当前选择
        current = self.overview_dimension.currentData()
        self.overview_dimension.blockSignals(True)
        self.overview_dimension.clear()
        for dimension in dimensions:
            self.overview_dimension.addItem(
                i18n.tr(DIMENSION_LABELS.get(dimension, dimension)), dimension
            )
        if dimensions:
            index = dimensions.index(current) if current in dimensions else 0
            self.overview_dimension.setCurrentIndex(index)
        self.overview_dimension.setEnabled(bool(dimensions))
        self.overview_dimension.blockSignals(False)

        if not dimensions:
            self.overview_map.setVisible(False)
            self.overview_size.setText(i18n.tr("还没有导出记录"))
            self.overview_hover.setText("")
            self.overview_detail.setText(
                i18n.tr("这个项目还没有导出记录。导出一次之后，这里会画出导过哪些区块。")
            )
            return

        dimension = self.overview_dimension.currentData()
        mine = [r for r in records if r.dimension == dimension]
        cells, self._overview_records = self._overview_cells(dimension, mine)
        self._overview_cells = cells
        self.overview_map.setVisible(True)

        keys = list(cells.keys())
        min_x = min(x for x, _ in keys) - OVERVIEW_RADIUS
        max_x = max(x for x, _ in keys) + OVERVIEW_RADIUS
        min_z = min(z for _, z in keys) - OVERVIEW_RADIUS
        max_z = max(z for _, z in keys) + OVERVIEW_RADIUS
        count_x = min(max_x - min_x + 1, OVERVIEW_MAX)
        count_z = min(max_z - min_z + 1, OVERVIEW_MAX)
        self.overview_map.set_area(min_x, min_z, count_x, count_z, cells)
        self.overview_size.setText(
            i18n.tr("共 %d 个区块　范围 %d × %d%s")
            % (
                len(cells),
                max_x - min_x + 1,
                max_z - min_z + 1,
                "" if (count_x, count_z) == (max_x - min_x + 1, max_z - min_z + 1)
                else "（太大，只画中间 %d × %d）" % (count_x, count_z),
            )
        )
        # 让"导过的那些块"落在眼前
        center_x = (min(x for x, _ in keys) + max(x for x, _ in keys)) // 2
        center_z = (min(z for _, z in keys) + max(z for _, z in keys)) // 2
        self.overview_map.center_on_chunk(center_x, center_z)
        self.overview_hover.setText(i18n.tr("把鼠标停在格子上看这一块的坐标与状态。"))
        self.overview_detail.setText(
            i18n.tr("在左边的概览图上点一个区块，这里显示它的详情。")
        )

    def _overview_cells(self, dimension: str, records: list) -> tuple[dict, dict]:
        """`{(x, z): (状态, 提示)}`：把本项目的记录摊到网格上。

        同一个项目可能对应好几个存档（换过存档根目录），所以按"记录里的世界"
        分组各算一次三态——都对着当前项目自己的存档比，别拿别的存档的时间戳比。
        """

        cells: dict = {}
        latest: dict = {}
        by_world: dict = {}
        for record in records:              # 新的在前：先写进去的就是最近那条
            by_world.setdefault(str(record.world), []).append(record)
        for world, group in by_world.items():
            states = self.store.chunk_states(
                world, dimension, [tuple(chunk) for record in group for chunk in record.chunks]
            )
            for (x, z), (state, record) in states.items():
                if record is None or (x, z) in cells:
                    continue
                detail = "导出于 %s" % record.created_at
                if state != "fresh":
                    detail += "，存档此后已修改"
                if record.faces:
                    detail += "　%d 面" % record.faces
                cells[(x, z)] = (state, detail)
                latest[(x, z)] = record
        return cells, latest

    def _on_overview_hover(self, x: int, z: int, text: str) -> None:
        if x == NO_CELL:
            return
        self.overview_hover.setText(
            i18n.tr("区块 (%d, %d)：%s") % (x, z, text.split("：", 1)[-1])
        )

    def _on_overview_clicked(self, x: int, z: int) -> None:
        """点一格 → 在图的旁边给这一块的详情（哪次导出、多少面、产物在哪）。"""

        if x == NO_CELL:
            return
        self._overview_picked = (x, z)
        state, _detail = getattr(self, "_overview_cells", {}).get((x, z), ("missing", ""))
        found = getattr(self, "_overview_records", {}).get((x, z))
        self.btn_overview_search.setEnabled(found is not None)
        if found is None:
            self.overview_detail.setText(
                i18n.tr("区块 (%d, %d)\n状态：没导过\n\n这个项目没有这一块的记录。")
                % (x, z)
            )
            return
        lines = [
            i18n.tr("区块 (%d, %d)") % (x, z),
            i18n.tr("状态：%s") % i18n.tr(STATE_LABELS.get(state, state)),
            i18n.tr("导出于 %s") % found.created_at,
            i18n.tr("维度：%s")
            % i18n.tr(DIMENSION_LABELS.get(found.dimension, found.dimension)),
        ]
        if found.faces:
            lines.append(i18n.tr("面数：%d") % found.faces)
        lines.append(i18n.tr("产物：%s") % found.output_dir)
        lines.append(i18n.tr("记录：%s") % found.id)
        self.overview_detail.setText("\n".join(lines))

    def _search_picked_chunk(self) -> None:
        """概览里选中的那一块 → 直接搜它的记录。"""

        picked = getattr(self, "_overview_picked", None)
        if picked is None:
            return
        self._search_chunks(picked[0], picked[1], self.overview_dimension.currentData())

    def _build_menu(self) -> None:
        bar = self.menuBar()

        materials = bar.addMenu("素材(&M)")
        materials.addAction("材质管理", self._open_material_manager)
        materials.addAction(i18n.tr("添加素材到本项目"), self._add_materials)

        project_menu = bar.addMenu(i18n.tr("项目(&P)"))
        project_menu.addAction("项目配置", self._edit_project_config)
        project_menu.addAction(
            i18n.tr("打开项目目录"), lambda: self._open_path(self.project.path)
        )
        project_menu.addAction(i18n.tr("导出项目配置包"), self._export_config)
        project_menu.addAction(i18n.tr("从配置包导入到本项目"), self._import_config_into)
        project_menu.addSeparator()
        project_menu.addAction("删除项目", self._delete_this_project)
        project_menu.addSeparator()
        project_menu.addAction(i18n.tr("关闭项目界面"), self.close)

        help_menu = bar.addMenu("帮助(&H)")
        help_menu.addAction("关于", self._show_about)

    def _apply_button_style(self) -> None:
        """两个导出按钮按"大号主按钮"着色（与主界面同级入口同款）。

        样式本身来自全局 QSS：这里只打属性，不再各自拼样式表——
        否则切换主题时这些按钮会停在旧颜色上。
        """

        for button in (self.btn_export_region, self.btn_export_snbt):
            # 与网站首页的主 CTA 同一外观（草绿渐变）
            design.set_variant(button, "secondary")
            button.setProperty("size", "large")
            button.setMinimumHeight(design.METRICS.button_large_height)

    # ---- 刷新 ------------------------------------------------------------

    def _refresh_all(self) -> None:
        self._refresh_basic()
        self._refresh_cover()
        self._refresh_bindings()
        self._refresh_package_status()
        self._refresh_history()
        self._refresh_overview()
        self._refresh_storage()
        backups = self.project.backups()
        self.backup_label.setText(
            i18n.tr("已备份 %d 次　最近：%s") % (len(backups), backups[0].name)
            if backups
            else i18n.tr("还没有备份过")
        )

    def _refresh_basic(self) -> None:
        """名称 / 简介 / 目录 / 存档位置：界面上只读，改要走「项目配置」。"""

        name = self.project.name or i18n.tr("未命名项目")
        self.name_label.setText(name)
        self.description_label.setText(
            self.project.description or i18n.tr("（还没有简介）")
        )
        self.directory_label.setText(i18n.tr("目录：%s") % self.project.path)
        self.save_label.setText(self.project.save_root or i18n.tr("（未设置）"))
        self.btn_backup.setEnabled(bool(self.project.save_root))
        self.setWindowTitle("项目 · %s" % name)

    def _refresh_cover(self) -> None:
        cover = self.project.cover_png()
        theme = design.theme()
        if cover is None:
            self.cover.setPixmap(QPixmap())
            self.cover.setText(i18n.tr("封面\n（点击选择）"))
            self.cover.setStyleSheet(
                "border:%dpx dashed %s; color:%s;"
                % (design.METRICS.border_width, theme.border, theme.text_3)
            )
            return
        pixmap = QPixmap(str(cover)).scaled(
            96, 96, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.cover.setPixmap(pixmap)
        self.cover.setText("")
        self.cover.setStyleSheet(
            "border:%dpx solid %s;" % (design.METRICS.border_width, theme.border)
        )

    def _refresh_bindings(self) -> None:
        library = Library.load(self.app_dir)
        missing = set(missing_bindings(self.project, library))
        self.bindings.clear()
        for source_id in self.project.materials:
            source = library.by_id(source_id)
            name = source.name if source else source_id
            kind = (
                i18n.tr(KIND_LABELS.get(source.kind, source.kind))
                if source
                else i18n.tr("缺失")
            )
            text = "%s　（%s）" % (name, kind)
            if source_id in missing:
                text += "　— 素材库里找不到了，请重新绑定"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, source_id)
            if source and source.icon and Path(source.icon).is_file():
                item.setIcon(QIcon(source.icon))
            self.bindings.addItem(item)
        self.bindings.setCurrentRow(
            0 if self.bindings.count() else -1
        )
        has_rows = self.bindings.count() > 0
        self.btn_remove_material.setEnabled(has_rows)
        self.btn_material_up.setEnabled(self.bindings.count() > 1)
        self.btn_material_down.setEnabled(self.bindings.count() > 1)

    def _refresh_package_status(self) -> None:
        library = Library.load(self.app_dir)
        bound = bound_library(self.project, library)
        ready = (self.project.package_dir / "block_textures.tsv").is_file()
        if not bound.enabled:
            text = i18n.tr("还没有绑定素材：导出会是白模（几何完整，没有贴图）。")
            self.btn_recompose.setEnabled(False)
        elif ready:
            text = i18n.tr("素材包：已就绪（%d 项）") % len(bound.enabled)
            self.btn_recompose.setEnabled(True)
        else:
            text = i18n.tr("素材包：需要重新组合（导出前会自动做一次）")
            self.btn_recompose.setEnabled(True)
        self.package_status.setText(text)
        design.set_role(self.package_status, "hint")

    def _refresh_history(self) -> None:
        records = self.store.records
        self.history.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.created_at,
                i18n.tr(record.kind_label),
                record.name,
                record.chunk_text(),
                str(record.faces or "—"),
                self._texture_summary(record),
                human_size(record.size_bytes(self.project.path)),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                # 数字右对齐：面数/贴图/大小按位对齐才好扫
                if column in (4, 5, 6):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.history.setItem(row, column, item)
            self.history.item(row, 0).setData(Qt.ItemDataRole.UserRole, record.id)
        self.history.clearSelection()
        self._update_history_buttons()

    def _update_history_buttons(self) -> None:
        """只对"选中的那条记录"生效的按钮：没选就禁掉。

        以前它们跟着"有没有记录"亮灭，结果一条没选也能按下去——按了没反应，
        或者更糟：按到别的动作上。（查询区块跟选中无关，永远是亮的。）
        """

        has_selection = bool(self.history.selectionModel().selectedRows())
        for name in ("btn_open_output", "btn_open_job", "btn_pack",
                     "btn_rebuild", "btn_delete"):
            getattr(self, name).setEnabled(has_selection)

    def _texture_summary(self, record: ExportRecord) -> str:
        """这条记录的贴图还在不在——不在就要靠「重新导出模型」补回来。"""
        if not record.textures:
            return "—"
        missing = [
            digest
            for digest in record.textures
            if not library_path(self.project.path, digest).is_file()
        ]
        if missing:
            return "%d 张（缺 %d）" % (len(record.textures), len(missing))
        return "%d 张" % len(record.textures)

    def _refresh_storage(self) -> None:
        items = categories(self.project.path)
        segments = [
            Segment(
                category.key,
                i18n.tr(category.label),
                _color(category.color),
                category.size,
            )
            for category in items
        ]
        self.storage_bar.set_segments(segments)
        self.storage_legend.set_segments(segments)
        total = sum(category.size for category in items)
        if segments:
            biggest = segments[0]
            self.storage_total.setText(
                i18n.tr("共 %s　最大一类：%s %s（%.1f%%）")
                % (
                    human_size(total),
                    biggest.label,
                    human_size(biggest.size),
                    percent(biggest.size, total),
                )
            )
        else:
            self.storage_total.setText(i18n.tr("这个项目还什么都没有。"))
        self._refresh_retention()

    # ---- 基本配置 --------------------------------------------------------

    def _edit_project_config(self) -> None:
        """项目配置弹窗：名称 / 简介 / 封面 / 项目目录 / 默认存档位置。

        界面上这些都只读展示——要改就到这里来（一次改完、一次落盘）。
        """

        dialog = _ProjectConfigDialog(self.project, self._move_project, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_project_config(dialog.values())

    def _delete_this_project(self) -> None:
        """删除这个项目：问清楚"只移除登记"还是"连目录一起删"，然后关掉本窗口。

        入口放在项目里（不在启动界面的卡片上）：卡片是"打开项目"的地方，
        删除按错了代价太大，不该在启动页一眼就能点到。
        """

        from .delete_project import delete_project

        mode = delete_project(self, self.project.path, self.project, self.config)
        if mode is None:
            return
        self.panel.log_line(
            "项目目录已删除：%s" % self.project.path
            if mode == "purge"
            else "已从项目列表移除：%s" % self.project.path
        )
        self.close()

    def _apply_project_config(self, values: dict) -> None:
        changed = False
        name = values["name"].strip()
        if name and name != self.project.name:
            self.project.name = name
            changed = True
        if values["description"] != self.project.description:
            self.project.description = values["description"]
            changed = True
        if values["save_root"] != self.project.save_root:
            self.project.save_root = values["save_root"]
            changed = True
        if changed:
            self.project.save()
            self.config.save()
        cover = values.get("cover") or ""
        if cover == _COVER_CLEAR:
            self.project.clear_cover()
        elif cover:
            self.project.set_cover(cover)
        logger().info("项目配置已更新：%s（%s）", self.project.name, self.project.path)
        self._refresh_all()

    def _change_cover(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", "图片 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)"
        )
        if not chosen:
            return
        self.project.set_cover(chosen)
        self._refresh_cover()
        logger().info("项目封面已更新：%s", self.project.cover)

    def _move_project(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "把项目搬到哪个目录（选空目录）")
        if not chosen:
            return
        target = Path(chosen)
        if target == self.project.path:
            return
        if (
            popup.ask(
                self,
                "移动项目",
                "把整个项目目录搬到：\n%s\n\n"
                "项目里的素材副本、历史记录、产物都跟着走。确定吗？" % target,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        old = self.project.path
        try:
            self.project.move_to(target)
        except Exception as error:
            logger().exception("移动项目失败：%s", old)
            popup.warning(self, "移动失败", str(error))
            return
        self.config.unregister_project(old)
        self.config.register_project(self.project.path)
        self.config.save()
        self.store = RecordStore(self.project.path)
        logger().info("项目已移动：%s → %s", old, self.project.path)
        self._refresh_all()

    # ---- 素材 ------------------------------------------------------------

    def _open_material_manager(self) -> None:
        """打开素材库管理（导入 / 启用 / 排序）。项目里的绑定是另一件事。"""
        from .material_manager import MaterialManagerDialog

        if self.panel.runner.is_running:
            popup.info(
                self, "导出进行中", "导出任务还没结束，现在不能更改素材库。"
            )
            return
        before = list(Library.load(self.app_dir).enabled)
        dialog = MaterialManagerDialog(self.app_dir, self)
        if dialog.exec() != MaterialManagerDialog.DialogCode.Accepted:
            return
        after = list(dialog.library.enabled)
        if before != after:
            # 素材库的启用列表变了：本项目绑定的东西可能跟着变，组合要重做
            self._force_recompose = True
        self.panel.log_line(
            "素材库已更新：%s" % (" → ".join(after) if after else "（没有启用任何素材）")
        )
        self._refresh_bindings()
        self._refresh_package_status()
        self._refresh_storage()

    def _add_materials(self) -> None:
        library = Library.load(self.app_dir)
        if not library.sources:
            popup.info(
                self,
                "素材库是空的",
                "先在「素材 → 材质管理」里导入原版客户端 jar / 资源包 / 模组，"
                "再回来绑定到项目。",
            )
            return
        picker = _BindingPicker(library.sources, self)
        if picker.exec() != _BindingPicker.DialogCode.Accepted:
            return
        chosen = picker.chosen_ids()
        if not chosen:
            return
        for source_id in chosen:
            source = library.by_id(source_id)
            if source is None or source.id in self.project.materials:
                continue
            # 原版是底：恒定排最前（和素材库里的规则一致），并且**不复制**——
            # 它是用户自己游戏里的客户端 jar，解压出来两百多 MB，没必要每个项目存一份；
            # 真正需要自给自足的是组合结果，那个会存进 <项目>/package。
            if source.kind == KIND_VANILLA:
                self.project.materials.insert(0, source.id)
                continue
            kind_dir = "mods" if source.kind == KIND_MOD else "packs"
            try:
                run_in_background(
                    self,
                    "绑定素材",
                    "正在把「%s」复制进项目…" % source.name,
                    lambda source=source, kind_dir=kind_dir: self.project.bind_material(
                        source, kind_dir
                    ),
                )
            except Exception as error:
                logger().exception("绑定素材失败：%s", source.name)
                popup.warning(self, "绑定失败", str(error))
        self.project.save()
        self._force_recompose = True
        self._refresh_bindings()
        self._refresh_package_status()
        self._refresh_storage()

    def _remove_material(self) -> None:
        item = self.bindings.currentItem()
        if item is None:
            return
        source_id = item.data(Qt.ItemDataRole.UserRole)
        library = Library.load(self.app_dir)
        source = library.by_id(source_id)
        if (
            popup.ask(
                self,
                "从项目移除",
                "把「%s」从本项目移除？\n\n项目里的副本会被删掉，素材库里的原件不动。"
                % (source.name if source else source_id),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if source is not None:
            self.project.unbind(source.name, "mods" if source.kind == KIND_MOD else "packs")
        self.project.materials = [i for i in self.project.materials if i != source_id]
        self.project.save()
        self._force_recompose = True
        self._refresh_bindings()
        self._refresh_package_status()
        self._refresh_storage()

    def _move_material(self, delta: int) -> None:
        row = self.bindings.currentRow()
        materials = self.project.materials
        target = row + delta
        if row < 0 or not (0 <= target < len(materials)):
            return
        # 原版钉在最前：它自己不许下移，别的也不许越过它（否则原版会去覆盖模组）
        library = Library.load(self.app_dir)
        vanilla = next(
            (s.id for s in library.sources if s.kind == KIND_VANILLA), None
        )
        if vanilla is not None and (
            materials[row] == vanilla or materials[target] == vanilla
        ):
            return
        materials[row], materials[target] = materials[target], materials[row]
        self.project.save()
        self._force_recompose = True
        self._refresh_bindings()
        self.bindings.setCurrentRow(target)
        self._refresh_package_status()

    def _compose(self, force: bool = False, report: bool = False) -> Path | None:
        """组合本项目素材包；返回 None 表示"这次没有素材包"（白模或用户取消）。"""
        library = Library.load(self.app_dir)
        try:
            package = run_in_background(
                self,
                "素材组合",
                "正在按项目顺序组合素材…\n\n（首次要几秒，之后改动才会重做）",
                lambda: ensure_package(self.app_dir, self.project, library, force=force),
            )
        except ComposeError as error:
            self._force_recompose = False
            if report:
                popup.info(self, "没有素材", str(error))
            return None
        except Exception as error:
            logger().exception("组合项目素材失败")
            popup.warning(self, "组合失败", str(error))
            return None
        self._force_recompose = False
        if report or not package.reused:
            self.panel.log_line("素材包：%s（%s）" % (package.package_dir.name, package.note))
        if package.stale:
            popup.info(
                self,
                "素材包是旧的",
                "项目里这份素材包是以前组合的，绑定的素材已经不在素材库里了。\n"
                "先用它导出没问题，但要重新组合就得把素材重新导入素材库。",
            )
        self._refresh_package_status()
        self._refresh_storage()
        return package.package_dir

    # ---- 导出 ------------------------------------------------------------

    def _chunk_states_for_dialog(self, world: str, dimension: str, cells: list) -> dict:
        """给导出对话框的概览图用：一次算一批区块的状态与说明。

        一次问一批（而不是一格一回）：概览图一开就是上百格，逐格查要走上百次
        "读记录 + 比 .mca 的 大小/mtime"，打开对话框会明显卡一下。
        """

        states = self.store.chunk_states(world, dimension, cells)
        result: dict = {}
        for (x, z), (state, record) in states.items():
            if record is None:
                result[(x, z)] = (state, "")
                continue
            detail = "导出于 %s" % record.created_at
            if state != "fresh":
                detail += "，存档此后已修改"
            if record.faces:
                detail += "　%d 面" % record.faces
            result[(x, z)] = (state, detail)
        return result

    def _exported_chunks_for_dialog(self, world: str, dimension: str) -> list:
        """这个存档里导过哪些区块——概览图靠它决定"以哪儿为中心"。"""

        return list(self.store.exported_chunks(world, dimension).keys())

    def _export_region(self) -> None:
        if self.panel.runner.is_running:
            return
        dialog = ExportRegionDialog(
            self.config,
            self,
            initial=self.project.options or self.config.last_export,
            initial_save=self.project.save_root,
            state_provider=self._chunk_states_for_dialog,
            # 存档位置在项目配置里定好了，这里不给改（改的地方就那一处）
            save_locked=bool(self.project.save_root),
        )
        if dialog.exec() != ExportRegionDialog.DialogCode.Accepted:
            return
        save_root = dialog.save_edit.text().strip()
        if not save_root:
            popup.warning(self, "缺少存档", "请先选择存档根目录。")
            return

        package = self._assets_for_export()
        if package is None:
            return
        self.project.save_root = save_root
        self.config.remember_save(save_root)

        selection = dialog.selection()
        name = dialog.output_name()
        out_dir = self.project.next_output_dir(name)
        job = dialog.result_job(assets_package=package, output_dir=str(out_dir))
        self.project.options = dict(job.get("options") or {})
        self.project.save()
        self._refresh_basic()        # 存档位置可能刚被改过，界面上要跟着变
        self.config.last_export = dict(self.project.options)
        self.config.save()

        self._pending = ExportRecord(
            id=out_dir.name,
            kind="region",
            name=name,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            output_dir=_relative(out_dir, self.project.path),
            world=save_root,
            dimension=str(job["input"]["world"]["dimension"]),
            chunks=[[int(x), int(z)] for x, z in selection.cells()],
            options=dict(self.project.options),
            mca_stamps=stamps_for(
                save_root,
                str(job["input"]["world"]["dimension"]),
                selection.cells(),
            ),
        )
        self.panel.log_line(
            "项目导出：%s，%d 个区块（%s）"
            % (name, selection.total, "带材质" if package else "白模")
        )
        if not self.panel.run(job, _cli_path(self.config), out_dir):
            self._pending = None

    def _export_snbt(self) -> None:
        if self.panel.runner.is_running:
            return
        picked = choose_snbt_source(self)
        if picked is None:
            return
        kind, payload = picked
        if kind == "paste":
            self._run_snbt_paste(payload)
            return
        self._run_snbt(Path(payload))

    def _run_snbt_paste(self, text: str) -> None:
        if not text.strip():
            return
        target = save_pasted_snbt(text, self.project.path / "inputs" / "snbt")
        self.panel.log_line("粘贴的 SNBT 已存为：%s" % target)
        self._run_snbt(target)

    def _run_snbt(self, path: Path, output_name: str = "") -> None:
        package = self._assets_for_export()
        if package is None:
            return
        # 输入副本始终留（很小，是追溯与重建的依据）
        copy_dir = self.project.path / "inputs" / "snbt"
        copy_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        copy = copy_dir / ("%s_%s" % (stamp, path.name))
        if path.resolve() != copy.resolve():
            shutil.copyfile(path, copy)

        name = output_name or path.stem
        out_dir = self.project.next_output_dir(name)
        job = build_snbt_job(
            snbt_path=str(path),
            assets_package=package,
            output_dir=str(out_dir),
            output_name=name,
            options=self.project.options
            or default_options(center=True, normalize_scale=False),
        )
        self._pending = ExportRecord(
            id=out_dir.name,
            kind="snbt",
            name=name,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            output_dir=_relative(out_dir, self.project.path),
            world=str(path),
            options=dict(job.get("options") or {}),
        )
        self.panel.log_line("项目导出：%s（SNBT）" % name)
        if not self.panel.run(job, _cli_path(self.config), out_dir):
            self._pending = None

    def _assets_for_export(self) -> str | None:
        """导出前备好素材包。返回 `""` = 白模；`None` = 用户取消。"""
        library = Library.load(self.app_dir)
        bound = bound_library(self.project, library)
        if not bound.enabled:
            answer = popup.ask(
                self,
                "没有绑定素材",
                "这个项目还没有绑定材质包 / 模组。\n\n"
                "要以白模导出吗？（几何完整，没有贴图与 MTL）",
            )
            return "" if answer == QMessageBox.StandardButton.Yes else None
        package = self._compose(force=self._force_recompose)
        if package is None:
            return None
        return str(package)

    def _on_export_finished(self, ok: bool, result: dict) -> None:
        if self._rebuild_record is not None:
            self._finish_rebuild(ok, result)
            return
        pending = self._pending
        self._pending = None
        if pending is None:
            return
        if not ok:
            self.panel.log_line("这次导出没有成功，不写记录。")
            self._refresh_all()
            return
        obj = result.get("obj")
        if obj:
            obj_path = Path(str(obj))
            pending.obj = _relative(obj_path, self.project.path)
            pending.job = _relative(obj_path.parent / "job.json", self.project.path)
            try:
                # 贴图收进项目贴图库：同一个项目里换个区块再导不会把同一张图存两遍
                pending.textures = run_in_background(
                    self,
                    "收录贴图",
                    "正在把贴图按内容哈希收进项目贴图库…",
                    lambda: absorb(self.project.path, obj_path),
                )
            except Exception as error:
                logger().exception("收录贴图失败：%s", obj_path)
                self.panel.log_line("警告：贴图没能收进项目贴图库（%s）" % error)
        pending.faces = int(result.get("faces") or 0)
        pending.seconds = float(result.get("seconds") or 0.0)
        self.store.add(pending)
        self.panel.log_line("已记入历史：%s" % pending.id)
        self.panel.log_line(
            "要拷到别处用（发人或换机器）：选中这条记录 → 「打包成 zip」，"
            "会把模型、MTL 与用到的贴图收成一个 zip。"
        )
        self._refresh_history()
        self._refresh_storage()

    # ---- 重新导出模型（补回贴图） -----------------------------------------
    #
    # 清理是有底线的：删掉的只能是"算力能买回来的东西"（§7.6）。所以每次导出都把
    # 当时的 job.json 留在产物目录里，贴图没了就照着它重跑一遍，把图补回库里。

    def _rebuild_selected(self) -> None:
        records = self._selected_records()
        if not records:
            return
        record = records[0]
        job_path = self.project.path / (
            record.job or (record.output_dir + "/job.json")
        )
        if not job_path.is_file():
            popup.info(
                self,
                "无法重新导出",
                "这条记录没有留下 job.json（只有项目模式下导出才会留），\n"
                "没法按当时那套输入重跑一遍。",
            )
            return
        package = self.project.package_dir
        if not (package / "block_textures.tsv").is_file():
            popup.info(
                self,
                "无法重新导出",
                "项目里还没有素材包（%s）。\n\n先在「素材」里绑定素材并组合一次，"
                "重新导出要靠它。" % package,
            )
            return
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            popup.warning(self, "无法重新导出", "job.json 读不出来：%s" % error)
            return

        missing = [
            digest
            for digest in record.textures
            if not library_path(self.project.path, digest).is_file()
        ]
        if record.textures and not missing and (
            popup.ask(
                self, "贴图都还在", "这条记录用到的贴图在库里都还在，还要重跑一遍吗？"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        # 输出到项目里的临时目录：重跑只为补贴图，不该覆盖原来的产物
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        temp_dir = self.project.path / "tmp" / ("rebuild_%s" % stamp)
        output = dict(job.get("output") or {})
        output["dir"] = str(temp_dir)
        job["output"] = output
        job["assets"] = {"package": str(package)}
        self._rebuild_record = record
        self.panel.log_line(
            "重新导出模型：%s（记录 %d 张贴图，缺 %d 张）"
            % (record.id, len(record.textures), len(missing))
        )
        if not self.panel.run(job, _cli_path(self.config)):
            self._rebuild_record = None

    def _finish_rebuild(self, ok: bool, result: dict) -> None:
        record = self._rebuild_record
        self._rebuild_record = None
        if record is None:
            return
        obj = result.get("obj") if ok else None
        if not obj:
            self.panel.log_line("重新导出失败：没有产出，记录保持不变。")
            return
        obj_path = Path(str(obj))
        try:
            absorbed = run_in_background(
                self,
                "重新导出模型",
                "正在把重新烘焙出来的贴图收进项目贴图库…",
                lambda: absorb(self.project.path, obj_path),
            )
        except Exception as error:
            logger().exception("重新导出模型失败：%s", record.id)
            popup.warning(self, "重新导出失败", str(error))
            return
        before = len(record.textures)
        record.textures = sorted(set(record.textures) | set(absorbed))
        self.store.add(record)
        # 重跑出来的临时产物没有价值：贴图已经进库了
        if is_inside(obj_path.parent, self.project.path):
            shutil.rmtree(obj_path.parent, ignore_errors=True)
        self.panel.log_line(
            "重新导出完成：记录里现在有 %d 张贴图（原有 %d 张，这次补回 %d 张）"
            % (len(record.textures), before, len(record.textures) - before)
        )
        self._refresh_history()
        self._refresh_storage()

    # ---- 历史记录操作 ----------------------------------------------------

    def _selected_records(self) -> list[ExportRecord]:
        ids = []
        for index in self.history.selectionModel().selectedRows():
            item = self.history.item(index.row(), 0)
            if item is not None:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return [r for r in (self.store.by_id(i) for i in ids) if r is not None]

    def _open_selected_output(self) -> None:
        records = self._selected_records()
        if not records:
            return
        self._open_path(self.project.path / records[0].output_dir)

    def _open_selected_job(self) -> None:
        records = self._selected_records()
        if not records:
            return
        job = self.project.path / (records[0].job or (records[0].output_dir + "/job.json"))
        if job.is_file():
            self._open_path(job)
        else:
            popup.info(self, "没有 job.json", "这次的记录里没有 job.json。")

    def _pack_selected(self) -> None:
        """把选中的那条记录打成 zip：模型 + MTL + 贴图，方便拷到别处。"""

        records = self._selected_records()
        if not records:
            return
        record = records[0]
        obj = self.project.path / (record.obj or (record.output_dir + "/model.obj"))
        if not obj.is_file():
            popup.info(
                self,
                "找不到模型",
                "这条记录的模型文件不在了：\n%s\n\n"
                "产物目录被清理过的话，用「重新导出模型」重跑一遍再来打包。" % obj,
            )
            return
        self.panel.pack_obj(obj)

    def _delete_selected(self) -> None:
        """删记录：只删记录 / 连产物一起删，合成一个按钮 + 一个弹窗说清楚。

        以前是两个按钮（「只删记录」「连产物一起删…」），容易看错眼按错；
        现在按下去先问，怎么删由用户在那个弹窗里选。
        """

        records = self._selected_records()
        if not records:
            return
        total = sum(r.size_bytes(self.project.path) for r in records)

        box = QMessageBox(self)
        box.setWindowTitle("删除记录")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("要删掉选中的 %d 条记录吗？" % len(records))
        box.setInformativeText(
            "仅删除记录：产物目录留在磁盘上（约 %s），之后可以手动清理。\n"
            "记录与产物一起删除：同时删掉产物目录，释放约 %s。\n\n"
            "项目贴图库里被其它记录引用的贴图不会动，SNBT 输入副本与存档备份不受影响。"
            % (human_size(total), human_size(total))
        )
        only_record = box.addButton("仅删除记录", QMessageBox.ButtonRole.AcceptRole)
        with_output = box.addButton(
            "记录与产物一起删除", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(only_record)
        box.exec()
        clicked = box.clickedButton()
        if clicked is only_record:
            self.store.remove([r.id for r in records])
            self.panel.log_line("删除记录：%d 条（产物保留）" % len(records))
        elif clicked is with_output:
            self.store.remove_with_outputs([r.id for r in records])
            self.panel.log_line(
                "删除记录与产物：%d 条，释放约 %s" % (len(records), human_size(total))
            )
        else:
            return
        self._refresh_history()
        self._refresh_storage()

    def _search_chunks(self, x=None, z=None, dimension=None, *_args) -> None:
        """按坐标搜记录；从导出概览点进来时带上那个坐标。"""

        initial = None if x is None or z is None else (int(x), int(z), dimension or "")
        _ChunkSearchDialog(self.project, self.store, self, initial=initial).exec()

    # ---- 存储与清理 ------------------------------------------------------

    def _retention_sizes(self) -> dict:
        return {
            record.id: record.size_bytes(self.project.path)
            for record in self.store.records
        }

    def _retention_plan(self):
        return retention_plan(
            self.store.records,
            keep=int(self.project.keep_exports or 0),
            max_days=int(self.project.keep_days or 0),
            max_size_mb=int(self.project.keep_size_mb or 0),
            sizes=self._retention_sizes(),
        )

    def _refresh_retention(self) -> None:
        if not policy_active(
            int(self.project.keep_exports or 0),
            int(self.project.keep_days or 0),
            int(self.project.keep_size_mb or 0),
        ):
            self.retention_label.setText(
                i18n.tr("保留策略：不自动清理（只在手动操作时清理）。")
            )
            self.btn_clean_outputs.setToolTip("只保留最近 N 次，其余连产物一起删")
            return
        plan = self._retention_plan()
        if plan.is_empty:
            self.retention_label.setText(
                i18n.tr("保留策略：已生效，当前没有需要清理的导出。")
            )
        else:
            self.retention_label.setText(
                i18n.tr(
                    "保留策略：可清理 %d 次旧导出，约 %s（打开「保留策略」可调整，"
                    "或点「清理旧产物」现在清）"
                )
                % (len(plan.victims), human_size(plan.freed))
            )

    def _edit_retention(self) -> None:
        dialog = _RetentionDialog(self.project, self)
        if dialog.exec() != _RetentionDialog.DialogCode.Accepted:
            return
        for key, value in dialog.values().items():
            setattr(self.project, key, value)
        self.project.save()
        self._refresh_retention()
        plan = self._retention_plan()
        if not plan.is_empty and (
            popup.ask(
                self, "按策略清理", plan.render() + "\n\n现在就清理吗？"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self._apply_retention(plan)

    def _apply_retention(self, plan) -> None:
        removed = self.store.remove_with_outputs(list(plan.victims))
        # 产物没了，贴图库里可能多出没人引用的图——顺手回收，不然越攒越多
        freed_textures = prune(self.project.path, self.store.records)
        self.panel.log_line(
            "按保留策略清理：%d 次导出，约 %s；另回收贴图 %d 张"
            % (removed, human_size(plan.freed), freed_textures[0])
        )
        self._refresh_history()
        self._refresh_storage()

    def _auto_clean_if_needed(self) -> None:
        """打开项目时按策略问一次（`auto_clean` 打开才走这里）。"""
        if not self.project.auto_clean:
            return
        plan = self._retention_plan()
        if plan.is_empty:
            return
        if (
            popup.ask(self, "保留策略", plan.render() + "\n\n现在清理吗？")
            == QMessageBox.StandardButton.Yes
        ):
            self._apply_retention(plan)

    def _open_category(self, key: str) -> None:
        for child in CATEGORY_PATHS.get(key, ()):
            target = self.project.path / child
            if target.exists():
                self._open_path(target)
                return
        popup.info(self, "这一类的目录还没建", "这个类别暂时是空的。")

    def _prune_textures(self) -> None:
        found = orphans(self.project.path, self.store.records)
        if not found:
            popup.info(
                self, "没有可清理的", "贴图库里没有没人引用的贴图。"
            )
            return
        size = sum(item.stat().st_size for item in found if item.is_file())
        if (
            popup.ask(
                self,
                "清理贴图",
                "删掉 %d 张没有任何记录引用的贴图？\n\n将释放约 %s。"
                % (len(found), human_size(size)),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        removed, freed = prune(self.project.path, self.store.records)
        logger().info("清理孤儿贴图：%d 个，释放 %d 字节", removed, freed)
        self.panel.log_line("清理贴图：%d 张，释放 %s" % (removed, human_size(freed)))
        self._refresh_storage()

    def _clean_outputs(self) -> None:
        """按时间保留最近 N 次导出（只删产物目录与记录，不动贴图库与输入副本）。"""
        records = self.store.records
        if not records:
            popup.info(self, "没有产物", "这个项目还没有导出过。")
            return
        keep = self._ask_keep_count()
        if keep is None:
            return
        victims = records[keep:]
        if not victims:
            popup.info(self, "不用清理", "导出的次数还没超过 %d 次。" % keep)
            return
        total = sum(r.size_bytes(self.project.path) for r in victims)
        if (
            popup.ask(
                self,
                "清理旧产物",
                "只保留最近 %d 次导出，删掉更早的 %d 次？\n\n将释放约 %s。\n"
                "贴图库、SNBT 输入副本、存档备份都不会动。"
                % (keep, len(victims), human_size(total)),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.store.remove_with_outputs([r.id for r in victims])
        self.panel.log_line(
            "清理旧产物：%d 次，释放约 %s" % (len(victims), human_size(total))
        )
        self._refresh_history()
        self._refresh_storage()

    def _ask_keep_count(self) -> int | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("清理旧产物")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("保留最近几次导出的产物？"))
        spin = QSpinBox()
        spin.setRange(1, 999)
        spin.setValue(10)
        layout.addWidget(spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return spin.value()

    # ---- 备份与项目配置 --------------------------------------------------

    def _backup_save(self) -> None:
        save_root = self.project.save_root
        if not save_root or not Path(save_root).is_dir():
            popup.warning(
                self,
                "找不到存档",
                "默认存档位置没有设置，或者指向的目录已经不在了。\n\n"
                "在「项目配置」里选一个存在的存档目录。",
            )
            return
        try:
            archive = run_in_background(
                self,
                "备份存档",
                "正在把整个存档打包进项目…\n\n%s\n\n（存档大的话要一会儿）" % save_root,
                lambda: self.project.backup_save(save_root, note=self.project.name),
            )
        except Exception as error:
            logger().exception("备份存档失败：%s", save_root)
            popup.warning(self, "备份失败", str(error))
            return
        self.panel.log_line("存档已备份：%s" % archive)
        self._refresh_all()

    def _manage_backups(self) -> None:
        dialog = _BackupsDialog(self.project, self)
        dialog.exec()
        self._refresh_all()          # 删过备份之后数字要跟着变

    def _export_config(self) -> None:
        suggested = "%s.ltrproject.zip" % (self.project.name or "project")
        chosen, _ = QFileDialog.getSaveFileName(
            self, "导出项目配置", suggested, "项目配置包 (*.zip)"
        )
        if not chosen:
            return
        try:
            archive = self.project.export_config(chosen)
        except Exception as error:
            popup.warning(self, "导出失败", str(error))
            return
        popup.info(
            self,
            "项目配置已导出",
            "已导出：\n%s\n\n里面是 project.json 与封面；素材副本与产物不带"
            "（动辄几百 MB，需要的是配置本身）。" % archive,
        )

    def _import_config_into(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "从配置包导入", "", "项目配置包 (*.zip)"
        )
        if not chosen:
            return
        if (
            popup.ask(
                self,
                "导入配置包",
                "用这个包里的配置覆盖当前项目的名称、描述、封面与素材绑定？\n\n"
                "历史记录与产物不受影响。",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            imported = Project.import_config(chosen, self.project.path)
        except Exception as error:
            popup.warning(self, "导入失败", str(error))
            return
        # 目录以当前项目为准：包里的路径是别的机器上的
        self.project.name = imported.name
        self.project.description = imported.description
        self.project.materials = list(imported.materials)
        self.project.options = dict(imported.options)
        if imported.cover:
            self.project.cover = imported.cover
        self.project.save()
        self._force_recompose = True
        self._refresh_all()
        popup.info(
            self,
            "已导入",
            "配置已导入。素材绑定原样保留了 id，素材库里没有的条目会显示为"
            "「素材库里找不到了」，重新绑定一下即可。",
        )

    def _show_about(self) -> None:
        popup.info(
            self,
            "关于项目模式",
            "项目 = 一个目录 + 一份 project.json。\n\n"
            "· 产物按时间戳新建目录，只往里写，不覆盖旧的\n"
            "· 贴图按内容哈希存进项目的 textures/，多次导出共用同一张\n"
            "· 记录写在 records/，用于查询「哪个区块导过、什么时候」\n\n"
            "素材来自本机游戏与资源包，本工具只读取、不附带、不分发。",
        )

    # ---- 杂项 ------------------------------------------------------------

    def _open_path(self, path: Path) -> None:
        from .export_panel import default_open_directory

        if path.is_dir() and not path.exists():
            popup.info(self, "找不到", "这个路径不存在了：\n%s" % path)
            return
        if not path.exists():
            popup.info(self, "找不到", "这个文件不存在了：\n%s" % path)
            return
        default_open_directory(path if path.is_dir() else path.parent)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)


def _cli_path(config: AppConfig) -> Path:
    if config.library_cli:
        return Path(config.library_cli)
    return paths.reader_executable()


def _relative(path: Path, root: Path) -> str:
    """记录里的路径一律相对项目目录，并且用正斜杠（跨平台、可读）。"""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def _color(text: str):
    return QColor(text)
