"""导出存档：选存档 → 选区块 → 选项。对应设计文档 §6 的三种选择模式。"""

from __future__ import annotations

from pathlib import Path

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
from .chunk_grid import ChunkGrid


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
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出存档模型")
        self._config = config
        self._initial = dict(initial or {})
        self._build_ui()
        self._sync()

    # ---- 界面 ------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 存档根目录（含 level.dat，不是 region 目录）
        save_row = QHBoxLayout()
        self.save_edit = QLineEdit(self._config.recent_saves[0] if self._config.recent_saves else "")
        self.save_edit.setPlaceholderText("存档根目录（含 level.dat 的那个文件夹）")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._pick_save)
        save_row.addWidget(self.save_edit, 1)
        save_row.addWidget(browse)
        layout.addLayout(save_row)
        self.save_edit.textChanged.connect(self._sync)

        form = QFormLayout()
        self.dimension = QComboBox()
        for value in DIMENSIONS:
            self.dimension.addItem(DIMENSION_LABELS[value], value)
        form.addRow("维度", self.dimension)

        self.mode = QComboBox()
        for value in CHUNK_MODES:
            self.mode.addItem(CHUNK_MODE_LABELS[value], value)
        self.mode.setCurrentIndex(CHUNK_MODES.index("center"))
        self.mode.currentIndexChanged.connect(self._sync)
        form.addRow("区块选择", self.mode)

        self.x = self._spin(-100000, 100000)
        self.z = self._spin(-100000, 100000)
        self.radius = self._spin(0, 64)
        self.x1, self.z1 = self._spin(-100000, 100000), self._spin(-100000, 100000)
        self.x2, self.z2 = self._spin(-100000, 100000), self._spin(-100000, 100000)
        form.addRow("中心 / 单块 x", self.x)
        form.addRow("中心 / 单块 z", self.z)
        form.addRow("半径 r", self.radius)
        form.addRow("起点 (x1, z1)", self._pair(self.x1, self.z1))
        form.addRow("终点 (x2, z2)", self._pair(self.x2, self.z2))
        layout.addLayout(form)

        grid_row = QHBoxLayout()
        self.grid = ChunkGrid()
        grid_row.addWidget(self.grid)
        side = QVBoxLayout()
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        side.addWidget(self.summary)
        side.addStretch(1)
        grid_row.addLayout(side, 1)
        layout.addLayout(grid_row)

        self.plain_blocks = QCheckBox("同时导出普通方块")
        self.plain_blocks.setChecked(bool(self._initial.get("plain_blocks", True)))
        self.cull = QCheckBox("剔除被相邻方块挡住的面")
        self.cull.setChecked(bool(self._initial.get("cull_hidden_faces", True)))
        self.center = QCheckBox("把模型中心移到原点")
        self.center.setChecked(bool(self._initial.get("center", True)))
        self.normalize = QCheckBox("再把最长边缩放到 1 个单位（会改变真实尺寸）")
        self.normalize.setChecked(bool(self._initial.get("normalize_scale", False)))
        layout.addWidget(self.plain_blocks)
        layout.addWidget(self.cull)
        layout.addWidget(self.center)
        layout.addWidget(self.normalize)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _spin(low: int, high: int) -> QSpinBox:
        box = QSpinBox()
        box.setRange(low, high)
        return box

    @staticmethod
    def _pair(left: QSpinBox, right: QSpinBox) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(left)
        row.addWidget(right)
        return holder

    # ---- 交互 ------------------------------------------------------------

    def _pick_save(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择存档根目录")
        if chosen:
            self.save_edit.setText(chosen)

    def _mode_visibility(self, mode: str) -> None:
        """按模式只留下相关的输入框，避免用户对着无关项发愣。"""
        for widget in (self.x, self.z):
            widget.setVisible(mode in ("single", "center"))
        self.radius.setVisible(mode == "center")
        for widget in (self.x1, self.z1, self.x2, self.z2):
            widget.setVisible(mode == "range")

    def _sync(self) -> None:
        mode = self.mode.currentData()
        self._mode_visibility(mode)
        selection = self.selection()
        center = (self.x.value(), self.z.value())
        self.grid.set_selection(center, selection)
        self.summary.setText(
            "共 %d 个区块\nx: %d … %d\nz: %d … %d\n\n"
            "左图只是示意：每个小格 = 1 个区块，粗框 = 本次导出的范围；\n"
            "范围由左侧输入框决定。"
            % (
                selection.total,
                selection.min_x,
                selection.min_x + selection.count_x - 1,
                selection.min_z,
                selection.min_z + selection.count_z - 1,
            )
        )

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
