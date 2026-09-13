"""导出存档：选存档 → 选区块 → 选项。

区块选择的三种模式用 `docs/chunk-selection-modes.svg` 那张示意图说明
（**只是示例图，不是让用户在图上点选**——范围由输入框决定）。

不适用的输入框**置灰而不是隐藏**：隐藏会让那一行留个空洞，列也就对不齐；
置灰则所有行始终在位，位置固定。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtSvgWidgets import QSvgWidget
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
from .theme import colors_for

# 仓库根/docs/chunk-selection-modes.svg（app/ui/ → app/ → 仓库根）
MODES_SVG = Path(__file__).resolve().parents[2] / "docs" / "chunk-selection-modes.svg"


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
        root = QVBoxLayout(self)

        # 存档根目录（含 level.dat，不是 region 目录）
        save_row = QHBoxLayout()
        self.save_edit = QLineEdit(
            self._config.recent_saves[0] if self._config.recent_saves else ""
        )
        self.save_edit.setPlaceholderText("存档根目录（含 level.dat 的那个文件夹）")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._pick_save)
        save_row.addWidget(QLabel("存档"))
        save_row.addWidget(self.save_edit, 1)
        save_row.addWidget(browse)
        root.addLayout(save_row)
        self.save_edit.textChanged.connect(self._sync)

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
        left_layout.addStretch(1)
        body.addWidget(left)

        # 右：示意图（静态） + 本次范围摘要
        right_layout = QVBoxLayout()
        if MODES_SVG.is_file():
            self.illustration = QSvgWidget(str(MODES_SVG))
            # 原图 1240×576，按这个比例给个能看清文字的大小
            self.illustration.setFixedSize(660, 307)
        else:
            self.illustration = QLabel("（找不到示意图：%s）" % MODES_SVG)
        right_layout.addWidget(self.illustration)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(
            "color:%s;" % colors_for(self.palette()).muted.name()
        )
        right_layout.addWidget(self.summary)
        right_layout.addStretch(1)
        body.addLayout(right_layout, 1)

        self.plain_blocks = QCheckBox("同时导出普通方块")
        self.plain_blocks.setChecked(bool(self._initial.get("plain_blocks", True)))
        self.cull = QCheckBox("剔除被相邻方块挡住的面")
        self.cull.setChecked(bool(self._initial.get("cull_hidden_faces", True)))
        self.center = QCheckBox("把模型中心移到原点")
        self.center.setChecked(bool(self._initial.get("center", True)))
        self.normalize = QCheckBox("再把最长边缩放到 1 个单位（会改变真实尺寸）")
        self.normalize.setChecked(bool(self._initial.get("normalize_scale", False)))
        for box in (self.plain_blocks, self.cull, self.center, self.normalize):
            root.addWidget(box)

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

    # ---- 交互 ------------------------------------------------------------

    def _pick_save(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择存档根目录")
        if chosen:
            self.save_edit.setText(chosen)

    def _sync(self) -> None:
        mode = self.mode.currentData()
        # 置灰而不是隐藏：行不消失，列才对得齐（隐藏会留一个空洞）
        for widget in (self.x, self.z):
            widget.setEnabled(mode in ("single", "center"))
        self.radius.setEnabled(mode == "center")
        for widget in (self.x1, self.z1, self.x2, self.z2):
            widget.setEnabled(mode == "range")

        selection = self.selection()
        self.summary.setText(
            "本次：共 %d 个区块　x %d … %d　z %d … %d\n"
            "（右图只说明三种模式的取法，范围以上面的输入为准）"
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
