"""导出存档：选存档 → 选区块 → 选项。

版面：**左边一列输入（区块参数 + 选项），右边一张区块概览图**，把宽度用起来
（以前是上下堆叠，图表挤在左下角一小块）。

概览图默认"以有导出数据的区块为中心，向外各 5 格"——打开就能看到"哪些块导过、
这次要导的框在哪儿"，而不是只有一个孤零零的坐标。图**只用来查看**：范围仍旧由
输入框决定（图上点选会让人以为"点了就等于选了范围"）。图上悬停看坐标与状态，
点一格在旁边看详情；范围大于视口时可以按住拖动平移，像看地图那样。

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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
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
from ..records import STATE_LABELS
from .chunk_grid import ChunkMapView

# 概览图：格子小一点（22px 一屏能放很多），单边最多 96 格（再多就该靠滚动看了）
GRID_CELL = 18
GRID_MAX = 96
OVERVIEW_RADIUS = 5        # 以"有数据的区块"为中心向外拓展几格


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
        exported_provider: Callable[[str, str], list] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出存档模型")
        self._config = config
        self._initial = dict(initial or {})
        # 项目模式要把"这个项目默认的存档"填进去，而不是全局最近用过的那个
        self._initial_save = initial_save
        # 项目模式会把"这些区块导过没有"的数据源传进来（§6 的概览图）：
        #   一次问一批格子（每格一回就是上百次文件系统查询，卡在打开对话框上）
        self._state_provider = state_provider
        # 概览图的中心来自"这个存档里已经导过哪些区块"，由项目界面提供
        self._exported_provider = exported_provider
        self._grid_key: tuple | None = None
        self._grid_scope: tuple | None = None
        self._cell_info: dict = {}
        self._build_ui()
        self._reset_detail()
        self.hover_label.setText("把鼠标停在格子上看这一块的坐标与状态。")
        if self._state_provider is None:
            self.grid_legend.setText(
                "黄框 = 本次范围（快速导出没有导出记录，不显示“导过没有”）"
            )
        self._sync()
        # 左列输入 + 右列概览图并排，宽度给足（概览图要能横向铺开）
        self.resize(1080, 700)
        self.setMinimumWidth(900)
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
        save_row.addWidget(QLabel("存档"))
        save_row.addWidget(self.save_edit, 1)
        save_row.addWidget(browse)
        root.addLayout(save_row)
        self.save_edit.textChanged.connect(self._sync)

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
            self.dimension.addItem(DIMENSION_LABELS[value], value)
        self.dimension.currentIndexChanged.connect(self._sync)
        form.addRow("维度", self.dimension)

        self.mode = QComboBox()
        for value in CHUNK_MODES:
            self.mode.addItem(CHUNK_MODE_LABELS[value], value)
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

        # 左列：区块参数 + 导出选项（都是"输入"）
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(design.METRICS.gap_md)
        left_layout.addLayout(form)

        options_label = QLabel("选项")
        design.set_role(options_label, "hint")
        left_layout.addWidget(options_label)

        self.plain_blocks = QCheckBox("同时导出普通方块")
        self.plain_blocks.setChecked(bool(self._initial.get("plain_blocks", True)))
        self.cull = QCheckBox("剔除被相邻方块挡住的面")
        self.cull.setChecked(bool(self._initial.get("cull_hidden_faces", True)))
        self.center = QCheckBox("把模型中心移到原点")
        self.center.setChecked(bool(self._initial.get("center", True)))
        self.normalize = QCheckBox("再把最长边缩放到 1 个单位（会改变真实尺寸）")
        self.normalize.setChecked(bool(self._initial.get("normalize_scale", False)))
        for box in (self.plain_blocks, self.cull, self.center, self.normalize):
            left_layout.addWidget(box)

        self.help_button = QPushButton("区块选择说明")
        self.help_button.clicked.connect(self._show_help)
        left_layout.addWidget(self.help_button)
        left_layout.addStretch(1)
        body.addWidget(left, 0)

        # 右列：概览图 + 悬停信息 + 点击详情 + 本次摘要
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(design.METRICS.gap_sm)

        head = QHBoxLayout()
        self.grid_size_label = QLabel()
        design.set_role(self.grid_size_label, "subtitle")
        head.addWidget(self.grid_size_label)
        self.grid_legend = QLabel(
            "灰 = 从未导出　绿 = 已导出且存档未变　黄 = 已导出但之后存档变过　"
            "黄框 = 本次范围"
        )
        design.set_role(self.grid_legend, "hint")
        head.addWidget(self.grid_legend, 1)
        right_layout.addLayout(head)

        map_row = QHBoxLayout()
        map_row.setSpacing(design.METRICS.gap_sm)
        self.state_map = ChunkMapView(cell=GRID_CELL, max_cells=GRID_MAX)
        self.state_map.hovered.connect(self._on_grid_hover)
        self.state_map.clicked.connect(self._on_grid_clicked)
        map_row.addWidget(self.state_map, 1)

        # 点一格 → 详情出现在图的旁边（用卡片装：纯 QLabel 不会自己画底与描边）
        detail_card, detail_layout = design.card(padding=design.METRICS.gap_sm)
        detail_card.setFixedWidth(240)
        self.detail = QLabel()
        # 卡片宽度是固定的，所以这里不用 wrap()（那套 Ignored 策略是为了"随可用宽度
        # 折行"，在这个定宽卡片里会让高度算错，正文被截掉几行）
        self.detail.setWordWrap(True)
        self.detail.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred
        )
        self.detail.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.detail)
        detail_layout.addStretch(1)
        map_row.addWidget(detail_card, 0)
        right_layout.addLayout(map_row, 1)

        self.hover_label = QLabel()
        wrap(self.hover_label)
        design.set_role(self.hover_label, "hint")
        right_layout.addWidget(self.hover_label)

        self.summary = QLabel()
        wrap(self.summary)
        design.set_role(self.summary, "hint")
        right_layout.addWidget(self.summary)
        body.addWidget(right, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

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
            "本次：共 %d 个区块　x %d … %d　z %d … %d（%d × %d）"
            % (
                selection.total,
                selection.min_x,
                selection.min_x + selection.count_x - 1,
                selection.min_z,
                selection.min_z + selection.count_z - 1,
                selection.count_x,
                selection.count_z,
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
            text = "！%s" % result.message
            if result.hint:
                text += "　%s" % result.hint
            role = "warn"
        self.save_status.setText(text)
        design.set_role(self.save_status, role)

    def _update_state_grid(self, selection) -> None:
        """把概览画出来：以"有数据的区块"为中心向外 5 格，并标出本次范围。

        数据源没给（快速导出）就只画本次范围那一块，并说明原因——
        图仍旧在，只是没有"导过没有"这一层信息。

        只在存档 / 维度 / 本次范围真的变了时才重算：一次要问上百格，
        每敲一个数字都重算是浪费（更别说文件系统查询不便宜）。
        """

        world = self.save_edit.text().strip()
        dimension = self.dimension.currentData()
        key = (
            world,
            dimension,
            selection.min_x,
            selection.min_z,
            selection.count_x,
            selection.count_z,
        )
        if key == self._grid_key:
            return
        self._grid_key = key
        if self._grid_scope != (world, dimension):
            # 换了存档/维度，之前点开的那条详情就不作数了
            self._grid_scope = (world, dimension)
            self._reset_detail()

        box = self._overview_box(world, dimension, selection)
        min_x, min_z, count_x, count_z = box
        cells: dict = {}
        self._cell_info = {}
        if self._state_provider is not None and world and Path(world).is_dir():
            wanted = [
                (min_x + column, min_z + row)
                for row in range(count_z)
                for column in range(count_x)
            ]
            found = self._state_provider(world, dimension, wanted)
            cells = dict(found)
            self._cell_info = dict(found)
        self.state_map.set_area(
            min_x,
            min_z,
            count_x,
            count_z,
            cells,
            selection=(
                selection.min_x,
                selection.min_z,
                selection.count_x,
                selection.count_z,
            ),
        )
        drawn = (self.state_map.grid.count_x, self.state_map.grid.count_z)
        note = ""
        if drawn != (count_x, count_z):
            note = "（范围太大，图上只画了中间 %d × %d，其余靠拖动查看）" % drawn
        self.grid_size_label.setText("区块概览：%d × %d%s" % (count_x, count_z, note))
        # 让"本次范围"落在眼前：图比视口大时滚到它的中心
        self.state_map.center_on_chunk(
            selection.min_x + (selection.count_x - 1) // 2,
            selection.min_z + (selection.count_z - 1) // 2,
        )

    def _overview_box(self, world: str, dimension: str, selection):
        """概览范围：数据的外接框各向外 5 格，并并上本次范围。

        没有数据（或快速导出没有索引）时就用本次范围的中心向外 5 格——
        至少让人看到"周围一圈是什么样"。
        """

        radius = OVERVIEW_RADIUS
        lo_x, hi_x = selection.min_x, selection.min_x + selection.count_x - 1
        lo_z, hi_z = selection.min_z, selection.min_z + selection.count_z - 1
        data: list = []
        if self._exported_provider is not None and world:
            try:
                data = list(self._exported_provider(world, dimension))
            except Exception:       # 索引读不出来不该让对话框打不开
                data = []
        if data:
            data_x = [int(x) for x, _ in data]
            data_z = [int(z) for _, z in data]
            lo_x = min(lo_x, min(data_x) - radius)
            hi_x = max(hi_x, max(data_x) + radius)
            lo_z = min(lo_z, min(data_z) - radius)
            hi_z = max(hi_z, max(data_z) + radius)
        else:
            center_x = (lo_x + hi_x) // 2
            center_z = (lo_z + hi_z) // 2
            lo_x, hi_x = min(lo_x, center_x - radius), max(hi_x, center_x + radius)
            lo_z, hi_z = min(lo_z, center_z - radius), max(hi_z, center_z + radius)
        return lo_x, lo_z, hi_x - lo_x + 1, hi_z - lo_z + 1

    # ---- 悬停与点击 ------------------------------------------------------

    def _on_grid_hover(self, x: int, z: int, text: str) -> None:
        if x < 0:
            self.hover_label.setText("")
            return
        self.hover_label.setText("区块 (%d, %d)：%s" % (x, z, text.split("：", 1)[-1]))

    def _on_grid_clicked(self, x: int, z: int) -> None:
        """点一格 → 详情显示在图的旁边（没点之前给一句用法说明）。"""

        if x < 0:
            return
        state, detail = self._cell_info.get((x, z), ("missing", ""))
        lines = [
            "区块 (%d, %d)" % (x, z),
            "状态：%s" % STATE_LABELS.get(state, state),
        ]
        if detail:
            lines.append(detail)
        lines.append("区域文件：r.%d.%d.mca" % (x >> 5, z >> 5))
        if state == "missing":
            lines.append("这一块还没有导出过。")
        self.detail.setText("\n".join(lines))

    def _reset_detail(self) -> None:
        self.detail.setText("在左边的概览图上点一个区块，这里显示它的详情。")

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
