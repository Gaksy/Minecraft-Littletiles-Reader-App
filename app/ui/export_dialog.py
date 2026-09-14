"""导出存档：选存档 → 选区块 → 选项。

区块选择的三种模式由「区块选择说明」那张现画的示意图解释
（**只是示例图，不是让用户在图上点选**——范围由输入框决定）。

对话框里右下角那张小网格画的是"这次要导的范围里，哪些块导过没有"（三态配色）；
整个项目"导过哪些区块"的概览在项目界面上（`project_window._build_overview_box`）。

不适用的输入框**置灰而不是隐藏**：隐藏会让那一行留个空洞，列也就对不齐；
置灰则所有行始终在位，位置固定。
"""

from __future__ import annotations

from typing import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from .. import i18n
from ..job import (
    CHUNK_MODE_LABELS,
    CHUNK_MODES,
    DIMENSION_LABELS,
    DIMENSIONS,
    build_region_job,
    chunks_field,
    default_options,
    expand_chunks,
)
from ..savefolder import inspect as inspect_save
from .illustration_dialog import IllustrationDialog
from . import design
from .widgets import wrap
from .chunk_grid import NO_CELL, ChunkStateGrid

# 这个对话框里只放得下一小块，格子画小一点、单边最多 16 格
GRID_CELL = 12
GRID_MAX = 16


class ExportRegionDialog(QDialog):
    """返回一个可直接写盘的 job（`result_job()`）。

    `initial` 是上次用过的选项（来自配置），让复选框记住上次的选择——
    默认值只应该在**第一次**出现。
    """

    def __init__(
        self,
        config: AppConfig,
        parent: QWidget | None = None,
        initial: dict | None = None,
        show_help_on_open: bool = False,
        initial_save: str = "",
        state_provider: Callable[[str, str, list], dict] | None = None,
        save_locked: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出存档模型")
        self._config = config
        self._initial = dict(initial or {})
        # 项目模式要把"这个项目默认的存档"填进去，而不是全局最近用过的那个
        self._initial_save = initial_save
        # 项目模式会把"这个区块导过没有"的数据源传进来（§6 的预览网格）
        self._state_provider = state_provider
        # 项目模式：存档位置由项目配置决定，这里只显示、不让改（改的地方在「项目配置」）
        self._save_locked = save_locked
        self._grid_key: tuple | None = None
        self._build_ui()
        self._sync()
        # 像素字体比系统字体宽，列太窄会把右侧摘要截断；给一个下限宽度，
        # 两列（左：区块参数 / 右：状态图 + 选项）才都放得下。
        self.setMinimumWidth(820)
        # 固定大小：所有行始终在位（不适用的只是置灰），内容高度是确定的，
        # 没理由让用户拖出一个空一半的窗口。
        self.layout().setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        if show_help_on_open:
            self._show_help()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """对话框出现时淡入一次。"""

        super().showEvent(event)
        if not getattr(self, "_faded_in", False):
            self._faded_in = True
            design.motion.fade_in(self)

    # ---- 界面 ------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # 存档根目录（含 level.dat，不是 region 目录）
        save_row = QHBoxLayout()
        self.save_edit = QLineEdit(self._initial_save or self._default_save())
        self.save_edit.setPlaceholderText("存档根目录（含 level.dat 的那个文件夹）")
        browse = QPushButton("选择文件夹")
        browse.clicked.connect(self._pick_save)
        self.save_browse = browse
        save_row.addWidget(QLabel("存档"))
        save_row.addWidget(self.save_edit, 1)
        save_row.addWidget(browse)
        root.addLayout(save_row)
        self.save_edit.textChanged.connect(self._sync)
        if self._save_locked:
            # 项目模式：路径来自项目配置，要改去项目界面上的「项目配置」
            self.save_edit.setEnabled(False)
            browse.setVisible(False)
            locked = QLabel("存档位置来自项目配置，要改请用项目界面上的「项目配置」。")
            wrap(locked)
            design.set_role(locked, "hint")
            root.addWidget(locked)

        # 选完路径当场说清楚对不对：选错目录的表现是"导出 0 个区块"，
        # 只看结果很难反推是自己选错了一层
        self.save_status = QLabel()
        wrap(self.save_status)
        root.addWidget(self.save_status)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        # 左：输入。所有行始终存在，只按模式置灰。
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.dimension = QComboBox()
        for value in DIMENSIONS:
            self.dimension.addItem(i18n.tr(DIMENSION_LABELS[value]), value)
        self.dimension.currentIndexChanged.connect(self._sync)
        form.addRow("维度", self.dimension)

        self.mode = QComboBox()
        for value in CHUNK_MODES:
            self.mode.addItem(i18n.tr(CHUNK_MODE_LABELS[value]), value)
        self.mode.setCurrentIndex(CHUNK_MODES.index("center"))
        self.mode.currentIndexChanged.connect(self._sync)
        form.addRow("区块选择", self.mode)

        # 三种模式各自的输入，每行一个字段、标签右对齐，所以列是齐的
        self.x = self._spin()
        self.z = self._spin()
        self.radius = self._spin(low=0, high=64)
        self.x1, self.z1 = self._spin(), self._spin()
        self.x2, self.z2 = self._spin(), self._spin()
        # 数字框也要接上：不然改了坐标，"本次：共 N 个区块"和预览网格还是旧值
        for widget in (self.x, self.z, self.radius, self.x1, self.z1, self.x2, self.z2):
            widget.valueChanged.connect(self._sync)
        form.addRow("中心 / 单块 x", self.x)
        form.addRow("中心 / 单块 z", self.z)
        form.addRow("半径 r", self.radius)
        form.addRow("范围起点 x1", self.x1)
        form.addRow("范围起点 z1", self.z1)
        form.addRow("范围终点 x2", self.x2)
        form.addRow("范围终点 z2", self.z2)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(form)
        # 项目模式下：这里画出"这几块导过没有"（灰/绿/黄），配一行图例
        self.state_grid = ChunkStateGrid(cell=GRID_CELL, max_cells=GRID_MAX)
        self.grid_legend = QLabel(
            "灰 = 从未导出　绿 = 已导出且存档未变　黄 = 已导出但之后存档变过"
        )
        design.set_role(self.grid_legend, "hint")
        if self._state_provider is None:
            self.grid_legend.setText("（项目模式下这里会显示每个区块导出过没有）")
            self.state_grid.setVisible(False)
        left_layout.addSpacing(8)
        left_layout.addWidget(self.state_grid)
        left_layout.addWidget(self.grid_legend)
        left_layout.addStretch(1)
        body.addWidget(left)

        # 右：示意图（静态） + 本次范围摘要
        right_layout = QVBoxLayout()
        self.help_button = QPushButton("区块选择说明")
        self.help_button.clicked.connect(self._show_help)
        right_layout.addWidget(self.help_button)

        self.summary = QLabel()
        wrap(self.summary)
        design.set_role(self.summary, "hint")
        # 摘要一行就是"共 N 个区块 x a…b z c…d"，窄了会被截断成半句
        self.summary.setMinimumWidth(360)
        right_layout.addWidget(self.summary)

        # 选项放在右列：说明图搬去独立窗口之后，这里原本空着一大块。
        options_label = QLabel("选项")
        design.set_role(options_label, "hint")
        right_layout.addSpacing(8)
        right_layout.addWidget(options_label)

        self.plain_blocks = QCheckBox("同时导出普通方块")
        self.plain_blocks.setChecked(bool(self._initial.get("plain_blocks", True)))
        self.cull = QCheckBox("剔除被相邻方块挡住的面")
        self.cull.setChecked(bool(self._initial.get("cull_hidden_faces", True)))
        self.center = QCheckBox("把模型中心移到原点")
        self.center.setChecked(bool(self._initial.get("center", True)))
        self.normalize = QCheckBox("再把最长边缩放到 1 个单位（会改变真实尺寸）")
        self.normalize.setChecked(bool(self._initial.get("normalize_scale", False)))
        for box in (self.plain_blocks, self.cull, self.center, self.normalize):
            right_layout.addWidget(box)

        right_layout.addStretch(1)
        body.addLayout(right_layout, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        i18n.translate(self)

    @staticmethod
    def _spin(low: int = -100000, high: int = 100000) -> QSpinBox:
        box = QSpinBox()
        box.setRange(low, high)
        return box

    def _default_save(self) -> str:
        return self._config.recent_saves[0] if self._config.recent_saves else ""

    # ---- 交互 ------------------------------------------------------------

    def _pick_save(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择存档根目录")
        if chosen:
            self.save_edit.setText(chosen)

    def _show_help(self) -> None:
        """三种选择模式的示意图：按需打开，不常驻。"""
        IllustrationDialog(self).exec()

    def _sync(self) -> None:
        mode = self.mode.currentData()
        # 置灰而不是隐藏：行不消失，列才对得齐（隐藏会留一个空洞）
        for widget in (self.x, self.z):
            widget.setEnabled(mode in ("single", "center"))
        self.radius.setEnabled(mode == "center")
        for widget in (self.x1, self.z1, self.x2, self.z2):
            widget.setEnabled(mode == "range")

        self._sync_save_status()
        selection = self.selection()
        self.summary.setText(
            i18n.tr(
                "本次：共 %d 个区块　x %d … %d　z %d … %d\n"
                "（右图只说明三种模式的取法，范围以上面的输入为准）"
            )
            % (
                selection.total,
                selection.min_x,
                selection.min_x + selection.count_x - 1,
                selection.min_z,
                selection.min_z + selection.count_z - 1,
            )
        )
        self._update_state_grid(selection)

    def _sync_save_status(self) -> None:
        """存档目录选对没有——选错一层是最常见、也最难自查的错误。"""
        result = inspect_save(self.save_edit.text(), self.dimension.currentData())
        if result.ok:
            text = "✓ %s" % result.message
            role = "ok"
        else:
            text = i18n.tr("！") + result.message
            if result.hint:
                text += "　%s" % result.hint
            role = "warn"
        self.save_status.setText(text)
        design.set_role(self.save_status, role)

    def _update_state_grid(self, selection) -> None:
        """把"导过没有"画出来。数据源没给就什么都不做。

        只在范围/存档/维度真的变了时才重算：这块每次改动都会跑一遍文件系统查询，
        范围一大就不便宜（大范围只画左上角那一块，见 ChunkStateGrid 的上限）。
        """
        if self._state_provider is None:
            return
        key = (
            self.save_edit.text().strip(),
            self.dimension.currentData(),
            selection.min_x,
            selection.min_z,
            selection.count_x,
            selection.count_z,
        )
        if key == self._grid_key:
            return
        self._grid_key = key
        world = key[0]
        rows = min(selection.count_z, GRID_MAX)
        columns = min(selection.count_x, GRID_MAX)
        cells: dict = {}
        if world and Path(world).is_dir():
            # 一次问一批：一格格问要走上百次"读记录 + 比 .mca"，打开对话框会卡一下
            wanted = [
                (selection.min_x + column, selection.min_z + row)
                for row in range(rows)
                for column in range(columns)
            ]
            cells = dict(self._state_provider(world, key[1], wanted))
        self.state_grid.set_area(
            selection.min_x, selection.min_z, selection.count_x, selection.count_z,
            cells,
        )
        self.state_grid.setVisible(True)

    # ---- 结果 ------------------------------------------------------------

    def selection(self):
        mode = self.mode.currentData()
        return expand_chunks(
            mode,
            x=self.x.value(),
            z=self.z.value(),
            radius=self.radius.value(),
            x1=self.x1.value(),
            z1=self.z1.value(),
            x2=self.x2.value(),
            z2=self.z2.value(),
        )

    def output_name(self) -> str:
        selection = self.selection()
        if selection.total == 1:
            return "c%d_%d" % (selection.min_x, selection.min_z)
        return "c%d_%d_r%d" % (
            selection.min_x,
            selection.min_z,
            max(selection.count_x, selection.count_z) // 2,
        )

    def result_job(self, *, assets_package: str, output_dir: str) -> dict:
        """拼成 job。输出目录由调用方补上（M1 用应用默认目录，M2 换成项目目录）。"""
        mode = self.mode.currentData()
        chunks = chunks_field(
            mode,
            x=self.x.value(),
            z=self.z.value(),
            radius=self.radius.value(),
            x1=self.x1.value(),
            z1=self.z1.value(),
            x2=self.x2.value(),
            z2=self.z2.value(),
        )
        return build_region_job(
            world_root=self.save_edit.text().strip(),
            dimension=self.dimension.currentData(),
            chunks=chunks,
            assets_package=assets_package,
            output_dir=output_dir,
            output_name=self.output_name(),
            options=default_options(
                plain_blocks=self.plain_blocks.isChecked(),
                cull_hidden_faces=self.cull.isChecked(),
                center=self.center.isChecked(),
                normalize_scale=self.normalize.isChecked(),
            ),
        )
