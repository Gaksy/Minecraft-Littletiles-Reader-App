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

import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QEventLoop, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ltgen import paths

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
    stamps_for,
)
from ..storage import categories, human_size, percent
from ..texture_library import absorb, orphans, prune
from ..storage import CATEGORY_PATHS
from .chunk_grid import ChunkStateGrid
from .export_dialog import ExportRegionDialog
from .export_panel import ExportPanel
from .storage_bar import Segment, StorageBar, StorageLegend
from .theme import colors_for
from .widgets import ClickableLabel, wrap


class _Worker(QThread):
    """把一件慢活放后台线程跑（组合素材、备份存档、收贴图…）。

    主线程用嵌套事件循环等它——界面照常重绘，进度框一直在动。放主线程的话
    "组合素材"这几秒会整段冻住，看起来像卡死（M1 踩过）。
    """

    finished_with = Signal(object)

    def __init__(self, work, parent=None) -> None:
        super().__init__(parent)
        self._work = work

    def run(self) -> None:
        try:
            self.finished_with.emit(self._work())
        except Exception as error:      # 交给主线程决定怎么说
            self.finished_with.emit(error)


def run_in_background(parent, title: str, text: str, work) -> object:
    """跑 work()，其间显示不确定进度框；返回结果，异常原样抛回调用方。"""
    dialog = QProgressDialog(text, "", 0, 0, parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setCancelButton(None)
    dialog.setMinimumDuration(0)
    dialog.show()

    worker = _Worker(work, parent)
    result: dict = {}
    loop = QEventLoop()

    def finished(payload) -> None:
        result["payload"] = payload
        loop.quit()

    worker.finished_with.connect(finished)
    worker.start()
    loop.exec()
    worker.wait()
    dialog.close()
    payload = result.get("payload")
    if isinstance(payload, Exception):
        raise payload
    return payload


class _BindingPicker(QDialog):
    """从素材库里挑要绑进项目的素材（可多选）。"""

    def __init__(self, sources, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加素材到项目")
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
            item = QListWidgetItem("%s（%s）" % (source.name, source.kind_label))
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

    def chosen_ids(self) -> list[str]:
        return [
            item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()
        ]


class _PasteSnbtDialog(QDialog):
    """粘贴一段 SNBT 文本（框里给个最小示例，省得用户不知道贴什么）。"""

    EXAMPLE = "{name:\"小屋\",tiles:[{pos:[0,0,0],size:[16,16,16],grid:16,color:16711680}]}"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("粘贴 SNBT")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("把结构文本粘进来（游戏里复制或从文件里复制的都行）："))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(self.EXAMPLE)
        self.text.setMinimumSize(560, 300)
        layout.addWidget(self.text)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def snbt(self) -> str:
        return self.text.toPlainText()


class _ChunkQueryDialog(QDialog):
    """查某个范围里每个区块导过没有、什么时候导的。"""

    def __init__(self, project: Project, store: RecordStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("查询区块导出情况")
        self._store = store
        self._project = project

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.world = QLineEdit(project.save_root)
        self.world.setMinimumWidth(420)
        self.world.setPlaceholderText("存档根目录（含 level.dat 的那个文件夹）")
        pick = QPushButton("浏览…")
        pick.clicked.connect(self._pick_world)
        world_row = QHBoxLayout()
        world_row.addWidget(self.world, 1)
        world_row.addWidget(pick)
        world_widget = QWidget()
        world_widget.setLayout(world_row)
        form.addRow("存档", world_widget)

        self.dimension = QComboBox()
        for value in DIMENSIONS:
            self.dimension.addItem(DIMENSION_LABELS[value], value)
        form.addRow("维度", self.dimension)

        self.mode = QComboBox()
        for value in CHUNK_MODES:
            self.mode.addItem(CHUNK_MODE_LABELS[value], value)
        self.mode.setCurrentIndex(CHUNK_MODES.index("center"))
        self.mode.currentIndexChanged.connect(self._sync)
        form.addRow("范围", self.mode)

        self.x, self.z = self._spin(), self._spin()
        self.radius = self._spin(low=0, high=64)
        self.x1, self.z1 = self._spin(), self._spin()
        self.x2, self.z2 = self._spin(), self._spin()
        form.addRow("中心 / 单块 x", self.x)
        form.addRow("中心 / 单块 z", self.z)
        form.addRow("半径 r", self.radius)
        form.addRow("范围起点 x1", self.x1)
        form.addRow("范围起点 z1", self.z1)
        form.addRow("范围终点 x2", self.x2)
        form.addRow("范围终点 z2", self.z2)
        root.addLayout(form)

        query = QPushButton("查询")
        query.clicked.connect(self._query)
        root.addWidget(query, alignment=Qt.AlignmentFlag.AlignRight)

        self.grid = ChunkStateGrid()
        grid_row = QHBoxLayout()
        grid_row.addWidget(self.grid, alignment=Qt.AlignmentFlag.AlignTop)
        self.summary = QLabel()
        wrap(self.summary)
        self.summary.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        grid_row.addWidget(self.summary, 1)
        root.addLayout(grid_row)

        legend = QLabel(
            "灰 = 从未导出　绿 = 已导出且存档未变　黄 = 已导出但之后存档变过"
        )
        legend.setStyleSheet("color:%s;" % colors_for(self.palette()).muted.name())
        root.addWidget(legend)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._sync()
        self.layout().setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

    @staticmethod
    def _spin(low: int = -100000, high: int = 100000) -> QSpinBox:
        box = QSpinBox()
        box.setRange(low, high)
        return box

    def _pick_world(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择存档根目录")
        if chosen:
            self.world.setText(chosen)

    def _sync(self) -> None:
        mode = self.mode.currentData()
        for widget in (self.x, self.z):
            widget.setEnabled(mode in ("single", "center"))
        self.radius.setEnabled(mode == "center")
        for widget in (self.x1, self.z1, self.x2, self.z2):
            widget.setEnabled(mode == "range")

    def _selection(self):
        return expand_chunks(
            self.mode.currentData(),
            x=self.x.value(),
            z=self.z.value(),
            radius=self.radius.value(),
            x1=self.x1.value(),
            z1=self.z1.value(),
            x2=self.x2.value(),
            z2=self.z2.value(),
        )

    def _query(self) -> None:
        world = self.world.text().strip()
        if not world:
            QMessageBox.warning(self, "缺少存档", "请先选择存档根目录。")
            return
        dimension = self.dimension.currentData()
        selection = self._selection()
        cells: dict = {}
        counts = {state: 0 for state in STATE_LABELS}
        for x, z in selection.cells():
            state, record = self._store.chunk_state(world, dimension, x, z)
            counts[state] = counts.get(state, 0) + 1
            detail = ""
            if record is not None:
                detail = "导出于 %s" % record.created_at
                if state != "fresh":
                    detail += "，存档此后已修改"
            cells[(x, z)] = (state, detail)
        self.grid.set_area(
            selection.min_x, selection.min_z, selection.count_x, selection.count_z, cells
        )
        lines = [
            "共 %d 个区块" % selection.total,
            "未导出 %d　已导出 %d　可能已过期 %d"
            % (
                counts.get("missing", 0),
                counts.get("fresh", 0),
                counts.get("stale", 0),
            ),
            "存档：%s" % world,
            "维度：%s" % DIMENSION_LABELS.get(dimension, dimension),
        ]
        for x, z in selection.cells():
            state, detail = cells[(x, z)]
            if state != "missing":
                lines.append("  (%d, %d) %s %s" % (x, z, STATE_LABELS[state], detail))
            if len(lines) > 24:
                lines.append("  …（只列前几块）")
                break
        if self.grid.truncated:
            lines.append("（范围太大，格子只画了左上角一部分）")
        self.summary.setText("\n".join(lines))


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
        self._force_recompose = False

        self.setWindowTitle("项目 · %s" % project.name)
        self.resize(1000, 760)
        self._build_ui()
        self._refresh_all()
        logger().info("打开项目：%s（%s）", project.name, project.path)

    # ---- 界面 ------------------------------------------------------------

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

    def _build_header(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)

        self.cover = ClickableLabel()
        self.cover.setFixedSize(96, 96)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover.setToolTip("点一下换封面")
        self.cover.clicked.connect(self._change_cover)
        row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)

        fields = QVBoxLayout()
        self.name_edit = QLineEdit(self.project.name)
        self.name_edit.setFont(QFont("", 13, QFont.Weight.Bold))
        self.name_edit.setPlaceholderText("项目名")
        self.name_edit.editingFinished.connect(self._save_basic)
        fields.addWidget(self.name_edit)

        self.description_edit = QPlainTextEdit(self.project.description)
        self.description_edit.setPlaceholderText("描述（给未来的自己看：这个项目是干什么的）")
        self.description_edit.setFixedHeight(56)
        # 失焦即存：用事件过滤器而不是给实例赋 focusOutEvent（虚函数派发不稳）
        self.description_edit.installEventFilter(self)
        fields.addWidget(self.description_edit)

        path_row = QHBoxLayout()
        self.directory_label = QLabel()
        wrap(self.directory_label)      # 路径很长，不折行会把整页撑宽
        self.directory_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        open_button = QPushButton("打开目录")
        open_button.clicked.connect(lambda: self._open_path(self.project.path))
        move_button = QPushButton("移动…")
        move_button.clicked.connect(self._move_project)
        path_row.addWidget(self.directory_label, 1)
        path_row.addWidget(open_button)
        path_row.addWidget(move_button)
        fields.addLayout(path_row)
        row.addLayout(fields, 1)

        status_box = QVBoxLayout()
        self.package_status = QLabel()
        wrap(self.package_status)
        status_box.addWidget(self.package_status)
        self.btn_recompose = QPushButton("重新组合素材")
        self.btn_recompose.clicked.connect(lambda: self._compose(force=True, report=True))
        status_box.addWidget(self.btn_recompose)
        status_box.addStretch(1)
        row.addLayout(status_box, 0)
        return box

    def _build_save_box(self) -> QGroupBox:
        box = QGroupBox("存档")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        self.save_edit = QLineEdit(self.project.save_root)
        self.save_edit.setPlaceholderText("本项目默认的存档根目录（含 level.dat 的那个文件夹）")
        self.save_edit.editingFinished.connect(self._save_basic)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._pick_save)
        row.addWidget(QLabel("默认存档"))
        row.addWidget(self.save_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)

        backup_row = QHBoxLayout()
        self.btn_backup = QPushButton("备份存档…")
        self.btn_backup.setToolTip("把整个存档打成一个 zip 存进项目目录（inputs/saves/）")
        self.btn_backup.clicked.connect(self._backup_save)
        self.backup_label = QLabel()
        wrap(self.backup_label)
        self.backup_label.setStyleSheet(
            "color:%s;" % colors_for(self.palette()).muted.name()
        )
        backup_row.addWidget(self.btn_backup)
        backup_row.addWidget(self.backup_label, 1)
        layout.addLayout(backup_row)
        return box

    def _build_material_box(self) -> QGroupBox:
        box = QGroupBox("素材（本项目绑定：材质包 / 模组，越靠下优先级越高）")
        layout = QVBoxLayout(box)

        self.bindings = QListWidget()
        self.bindings.setMinimumHeight(96)
        layout.addWidget(self.bindings)

        row = QHBoxLayout()
        for name, label, slot in (
            ("btn_add_material", "添加…", self._add_materials),
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
        return box

    def _build_history_box(self) -> QGroupBox:
        box = QGroupBox("历史记录")
        layout = QVBoxLayout(box)

        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(
            ["时间", "类型", "名称", "区块", "面数", "大小"]
        )
        self.history.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setMinimumHeight(140)
        self.history.verticalHeader().setVisible(False)
        self.history.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history)

        row = QHBoxLayout()
        for name, label, slot in (
            ("btn_open_output", "打开产物目录", self._open_selected_output),
            ("btn_open_job", "打开 job.json", self._open_selected_job),
            ("btn_query", "查询区块…", self._query_chunks),
            ("btn_forget", "只删记录", self._forget_selected),
            ("btn_delete", "连产物一起删…", self._delete_selected),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            setattr(self, name, button)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
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
        self.btn_prune = QPushButton("清理没被引用的贴图…")
        self.btn_prune.setToolTip(
            "删掉贴图库里没有任何导出记录引用的图（不会删产物与记录）"
        )
        self.btn_prune.clicked.connect(self._prune_textures)
        self.btn_clean_outputs = QPushButton("清理旧产物…")
        self.btn_clean_outputs.clicked.connect(self._clean_outputs)
        row.addWidget(self.btn_prune)
        row.addWidget(self.btn_clean_outputs)
        row.addStretch(1)
        layout.addLayout(row)
        return box

    def storage_legend_hover(self, index: int) -> None:
        """条上悬停 → 图例那一行也淡出/高亮，两边指向同一个类别。"""
        rows = [
            self.storage_legend.itemAt(i).widget()
            for i in range(self.storage_legend.layout().count())
        ]
        for row_index, row in enumerate(rows):
            if row is None:
                continue
            row.setStyleSheet(
                "" if index < 0 or index == row_index
                else "color: palette(mid);"
            )

    def _build_menu(self) -> None:
        bar = self.menuBar()
        project_menu = bar.addMenu("项目(&P)")
        project_menu.addAction("打开项目目录", lambda: self._open_path(self.project.path))
        project_menu.addAction("导出项目配置…", self._export_config)
        project_menu.addAction("从配置包导入到本项目…", self._import_config_into)
        project_menu.addSeparator()
        project_menu.addAction("关闭项目界面", self.close)

        help_menu = bar.addMenu("帮助(&H)")
        help_menu.addAction("关于", self._show_about)

    def _apply_button_style(self) -> None:
        from .main_window import big_button_style

        style = big_button_style(self.palette())
        for button in (self.btn_export_region, self.btn_export_snbt):
            button.setStyleSheet(style)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_button_style()
        super().changeEvent(event)

    def eventFilter(self, source, event) -> bool:  # noqa: N802
        # 描述框失焦就存盘（和名称框的 editingFinished 一个意思）
        if source is self.description_edit and event.type() == QEvent.Type.FocusOut:
            self._save_basic()
        return super().eventFilter(source, event)

    # ---- 刷新 ------------------------------------------------------------

    def _refresh_all(self) -> None:
        self.directory_label.setText("目录：%s" % self.project.path)
        self.directory_label.setStyleSheet(
            "color:%s;" % colors_for(self.palette()).muted.name()
        )
        self._refresh_cover()
        self._refresh_bindings()
        self._refresh_package_status()
        self._refresh_history()
        self._refresh_storage()
        backups = self.project.backups()
        self.backup_label.setText(
            "已备份 %d 次　最近：%s" % (len(backups), backups[0].name)
            if backups
            else "还没有备份过"
        )
        self.btn_backup.setEnabled(bool(self.save_edit.text().strip()))

    def _refresh_cover(self) -> None:
        cover = self.project.cover_png()
        muted = colors_for(self.palette()).muted.name()
        if cover is None:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("封面\n（点击选择）")
            self.cover.setStyleSheet(
                "border:1px dashed %s; color:%s; border-radius:6px;" % (muted, muted)
            )
            return
        pixmap = QPixmap(str(cover)).scaled(
            96, 96, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.cover.setPixmap(pixmap)
        self.cover.setText("")
        self.cover.setStyleSheet("border:1px solid %s; border-radius:6px;" % muted)

    def _refresh_bindings(self) -> None:
        library = Library.load(self.app_dir)
        missing = set(missing_bindings(self.project, library))
        self.bindings.clear()
        for source_id in self.project.materials:
            source = library.by_id(source_id)
            name = source.name if source else source_id
            kind = KIND_LABELS.get(source.kind, source.kind) if source else "缺失"
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
        muted = colors_for(self.palette()).muted.name()
        if not bound.enabled:
            text = "还没有绑定素材：导出会是白模（几何完整，没有贴图）。"
            self.btn_recompose.setEnabled(False)
        elif ready:
            text = "素材包：已就绪（%d 项）" % len(bound.enabled)
            self.btn_recompose.setEnabled(True)
        else:
            text = "素材包：需要重新组合（导出前会自动做一次）"
            self.btn_recompose.setEnabled(True)
        self.package_status.setText(text)
        self.package_status.setStyleSheet("color:%s;" % muted)

    def _refresh_history(self) -> None:
        records = self.store.records
        self.history.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.created_at,
                record.kind_label,
                record.name,
                record.chunk_text(),
                str(record.faces or "—"),
                human_size(record.size_bytes(self.project.path)),
            ]
            for column, text in enumerate(values):
                self.history.setItem(row, column, QTableWidgetItem(text))
            self.history.item(row, 0).setData(Qt.ItemDataRole.UserRole, record.id)
        self.history.resizeColumnsToContents()
        has_rows = bool(records)
        for name in ("btn_open_output", "btn_open_job", "btn_forget", "btn_delete"):
            getattr(self, name).setEnabled(has_rows)
        self.btn_forget.setEnabled(has_rows)
        self.btn_delete.setEnabled(has_rows)

    def _refresh_storage(self) -> None:
        items = categories(self.project.path)
        segments = [
            Segment(category.key, category.label, _color(category.color), category.size)
            for category in items
        ]
        self.storage_bar.set_segments(segments)
        self.storage_legend.set_segments(segments)
        total = sum(category.size for category in items)
        if segments:
            biggest = segments[0]
            self.storage_total.setText(
                "共 %s　最大一类：%s %s（%.1f%%）"
                % (
                    human_size(total),
                    biggest.label,
                    human_size(biggest.size),
                    percent(biggest.size, total),
                )
            )
        else:
            self.storage_total.setText("这个项目还什么都没有。")

    # ---- 基本配置 --------------------------------------------------------

    def _save_basic(self) -> None:
        changed = False
        name = self.name_edit.text().strip()
        if name and name != self.project.name:
            self.project.name = name
            self.setWindowTitle("项目 · %s" % name)
            changed = True
        if self.description_edit.toPlainText() != self.project.description:
            self.project.description = self.description_edit.toPlainText()
            changed = True
        save_root = self.save_edit.text().strip()
        if save_root != self.project.save_root:
            self.project.save_root = save_root
            changed = True
            self.btn_backup.setEnabled(bool(save_root))
        if changed:
            self.project.save()
            self.config.save()

    def _pick_save(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择存档根目录")
        if chosen:
            self.save_edit.setText(chosen)
            self._save_basic()

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
            QMessageBox.question(
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
            QMessageBox.warning(self, "移动失败", str(error))
            return
        self.config.unregister_project(old)
        self.config.register_project(self.project.path)
        self.config.save()
        self.store = RecordStore(self.project.path)
        logger().info("项目已移动：%s → %s", old, self.project.path)
        self._refresh_all()

    # ---- 素材 ------------------------------------------------------------

    def _add_materials(self) -> None:
        library = Library.load(self.app_dir)
        if not library.sources:
            QMessageBox.information(
                self,
                "素材库是空的",
                "先在「素材 → 材质管理…」里导入原版客户端 jar / 资源包 / 模组，"
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
                QMessageBox.warning(self, "绑定失败", str(error))
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
            QMessageBox.question(
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
                QMessageBox.information(self, "没有素材", str(error))
            return None
        except Exception as error:
            logger().exception("组合项目素材失败")
            QMessageBox.warning(self, "组合失败", str(error))
            return None
        self._force_recompose = False
        if report or not package.reused:
            self.panel.log_line("素材包：%s（%s）" % (package.package_dir.name, package.note))
        if package.stale:
            QMessageBox.information(
                self,
                "素材包是旧的",
                "项目里这份素材包是以前组合的，绑定的素材已经不在素材库里了。\n"
                "先用它导出没问题，但要重新组合就得把素材重新导入素材库。",
            )
        self._refresh_package_status()
        self._refresh_storage()
        return package.package_dir

    # ---- 导出 ------------------------------------------------------------

    def _export_region(self) -> None:
        if self.panel.runner.is_running:
            return
        dialog = ExportRegionDialog(
            self.config,
            self,
            initial=self.project.options or self.config.last_export,
            initial_save=self.project.save_root,
        )
        if dialog.exec() != ExportRegionDialog.DialogCode.Accepted:
            return
        save_root = dialog.save_edit.text().strip()
        if not save_root:
            QMessageBox.warning(self, "缺少存档", "请先选择存档根目录。")
            return

        package = self._assets_for_export()
        if package is None:
            return
        self.project.save_root = save_root
        self.save_edit.setText(save_root)
        self.config.remember_save(save_root)

        selection = dialog.selection()
        name = dialog.output_name()
        out_dir = self.project.next_output_dir(name)
        job = dialog.result_job(assets_package=package, output_dir=str(out_dir))
        self.project.options = dict(job.get("options") or {})
        self.project.save()
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
        box = QMessageBox(self)
        box.setWindowTitle("导出 SNBT")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("结构从哪里来？")
        box.setInformativeText(
            "选一个 .txt / .struct 结构文件，或者直接把文本粘进来。"
        )
        from_file = box.addButton("选择文件…", QMessageBox.ButtonRole.AcceptRole)
        from_paste = box.addButton("粘贴文本…", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is from_paste:
            dialog = _PasteSnbtDialog(self)
            if dialog.exec() == _PasteSnbtDialog.DialogCode.Accepted:
                self._run_snbt_paste(dialog.snbt())
            return
        if clicked is not from_file:
            return
        chosen, _ = QFileDialog.getOpenFileName(
            self, "选择 LittleTiles 结构文件", "", "结构文件 (*.txt *.struct);;所有文件 (*)"
        )
        if chosen:
            self._run_snbt(Path(chosen))

    def _run_snbt_paste(self, text: str) -> None:
        if not text.strip():
            return
        target_dir = self.project.path / "inputs" / "snbt"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        target = target_dir / ("%s_paste.txt" % stamp)
        target.write_text(text, encoding="utf-8")
        self.panel.log_line("粘贴的 SNBT 已存为：%s" % target)
        self._run_snbt(target, output_name="paste_%s" % stamp)

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
            answer = QMessageBox.question(
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
            QMessageBox.information(self, "没有 job.json", "这次的记录里没有 job.json。")

    def _forget_selected(self) -> None:
        records = self._selected_records()
        if not records:
            return
        if (
            QMessageBox.question(
                self,
                "只删记录",
                "删掉这 %d 条记录？\n\n产物目录会留下（贴图库里没人引用的图之后可以清理）。"
                % len(records),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.store.remove([r.id for r in records])
        self._refresh_history()
        self._refresh_storage()

    def _delete_selected(self) -> None:
        records = self._selected_records()
        if not records:
            return
        total = sum(r.size_bytes(self.project.path) for r in records)
        if (
            QMessageBox.question(
                self,
                "连产物一起删",
                "删掉这 %d 条记录和它们的产物目录？\n\n将释放约 %s。\n"
                "项目贴图库里被其它记录引用的贴图不会动。"
                % (len(records), human_size(total)),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.store.remove_with_outputs([r.id for r in records])
        self._refresh_history()
        self._refresh_storage()

    def _query_chunks(self) -> None:
        _ChunkQueryDialog(self.project, self.store, self).exec()

    # ---- 存储与清理 ------------------------------------------------------

    def _open_category(self, key: str) -> None:
        for child in CATEGORY_PATHS.get(key, ()):
            target = self.project.path / child
            if target.exists():
                self._open_path(target)
                return
        QMessageBox.information(self, "这一类的目录还没建", "这个类别暂时是空的。")

    def _prune_textures(self) -> None:
        found = orphans(self.project.path, self.store.records)
        if not found:
            QMessageBox.information(
                self, "没有可清理的", "贴图库里没有没人引用的贴图。"
            )
            return
        size = sum(item.stat().st_size for item in found if item.is_file())
        if (
            QMessageBox.question(
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
            QMessageBox.information(self, "没有产物", "这个项目还没有导出过。")
            return
        keep = self._ask_keep_count()
        if keep is None:
            return
        victims = records[keep:]
        if not victims:
            QMessageBox.information(self, "不用清理", "导出的次数还没超过 %d 次。" % keep)
            return
        total = sum(r.size_bytes(self.project.path) for r in victims)
        if (
            QMessageBox.question(
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
        save_root = self.save_edit.text().strip()
        if not save_root or not Path(save_root).is_dir():
            QMessageBox.warning(self, "找不到存档", "请先选一个存在的存档目录。")
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
            QMessageBox.warning(self, "备份失败", str(error))
            return
        self.panel.log_line("存档已备份：%s" % archive)
        self._refresh_all()

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
            QMessageBox.warning(self, "导出失败", str(error))
            return
        QMessageBox.information(
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
            QMessageBox.question(
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
            QMessageBox.warning(self, "导入失败", str(error))
            return
        # 目录以当前项目为准：包里的路径是别的机器上的
        self.project.name = imported.name
        self.project.description = imported.description
        self.project.materials = list(imported.materials)
        self.project.options = dict(imported.options)
        if imported.cover:
            self.project.cover = imported.cover
        self.project.save()
        self.name_edit.setText(self.project.name)
        self.description_edit.setPlainText(self.project.description)
        self._force_recompose = True
        self._refresh_all()
        QMessageBox.information(
            self,
            "已导入",
            "配置已导入。素材绑定原样保留了 id，素材库里没有的条目会显示为"
            "「素材库里找不到了」，重新绑定一下即可。",
        )

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于项目模式",
            "项目 = 一个目录 + 一份 project.json。\n\n"
            "· 产物按时间戳新建目录，只往里写，不覆盖旧的\n"
            "· 贴图按内容哈希存进项目的 textures/，多次导出共用同一张\n"
            "· 记录写在 records/，用于查询「哪个区块导过、什么时候」\n\n"
            "素材来自你自己的游戏与资源包，本工具只读取、不附带也不分发。",
        )

    # ---- 杂项 ------------------------------------------------------------

    def _open_path(self, path: Path) -> None:
        from .export_panel import default_open_directory

        if path.is_dir() and not path.exists():
            QMessageBox.information(self, "找不到", "这个路径不存在了：\n%s" % path)
            return
        if not path.exists():
            QMessageBox.information(self, "找不到", "这个文件不存在了：\n%s" % path)
            return
        default_open_directory(path if path.is_dir() else path.parent)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_basic()
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
