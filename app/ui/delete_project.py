"""删除项目：一个弹窗问清楚"怎么删"，然后照着做。

两种后果差得远，所以必须说清楚：

* **仅从项目列表移除**：只动应用里的登记，磁盘上的目录一个字节都不碰；
* **删除项目目录**：素材副本、贴图库、导出产物、历史记录全没，且**不可恢复**——
  这条选项要额外勾一个确认框才让点「删除」。

入口在**项目界面**（菜单「项目 → 删除项目」），不在启动界面的卡片上：
卡片是"打开项目"的地方，删除是进到项目里才做的事（手滑代价太大）。

双保险：真删目录前必须确认那里有 `project.json`。否则一律拒绝——宁可什么都不做，
也不能把一个手滑选到的普通目录递归删掉。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
)

from ..applog import logger
from ..config import AppConfig
from ..project import Project
from ..storage import dir_size, human_size
from .. import i18n
from . import design
from .widgets import wrap

MODE_FORGET = "forget"
MODE_PURGE = "purge"


class DeleteProjectDialog(QDialog):
    """问"怎么删"：只移除登记，还是连目录一起删。"""

    def __init__(self, directory: str, project: Project | None, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(520)
        self.directory = directory
        self.mode = MODE_FORGET
        path = Path(directory)
        exists = path.is_dir()
        size = dir_size(path) if exists else 0
        name = (project.name if project is not None else "") or path.name or directory
        self.setWindowTitle(i18n.tr("删除项目"))

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_md)

        title = QLabel(i18n.tr("要删除「%s」吗？") % name)
        design.set_role(title, "subtitle")
        layout.addWidget(title)

        where = QLabel(str(path))
        wrap(where)
        design.set_role(where, "dim")
        layout.addWidget(where)

        self.opt_forget = QRadioButton(
            i18n.tr("仅从项目列表移除（磁盘上的目录保留）")
        )
        self.opt_forget.setChecked(True)
        self.opt_purge = QRadioButton(
            i18n.tr("删除项目目录（释放约 %s）") % human_size(size)
            if exists
            else i18n.tr("删除项目目录（这个目录已经不在磁盘上了）")
        )
        self.opt_purge.setEnabled(exists)
        self.opt_forget.toggled.connect(self._sync)
        layout.addWidget(self.opt_forget)
        layout.addWidget(self.opt_purge)

        self.confirm = QCheckBox(
            i18n.tr(
                "我确认永久删除这个目录：素材副本、贴图库、导出产物、历史记录都会一起没有"
            )
        )
        self.confirm.setEnabled(False)
        self.confirm.toggled.connect(self._sync)
        layout.addWidget(self.confirm)

        if not exists:
            hint = QLabel(i18n.tr("目录不在了，只能把这条登记从列表里删掉。"))
            wrap(hint)
            design.set_role(hint, "hint")
            layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.btn_ok.setText(i18n.tr("删除"))
        design.set_variant(self.btn_ok, "danger")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sync()

    def _sync(self) -> None:
        purge = self.opt_purge.isChecked() and self.opt_purge.isEnabled()
        self.confirm.setEnabled(purge)
        if not purge:
            self.confirm.setChecked(False)
        self.btn_ok.setEnabled((not purge) or self.confirm.isChecked())

    def accept(self) -> None:
        self.mode = MODE_PURGE if self.opt_purge.isChecked() else MODE_FORGET
        super().accept()


def delete_project(
    parent,
    directory: str | Path,
    project: Project | None,
    config: AppConfig,
) -> str | None:
    """问一次、删一次。返回 `"forget"` / `"purge"`；取消或拒绝返回 None。

    调用方负责善后（关掉还开着的项目窗口等）。
    """

    target = Path(directory)
    dialog = DeleteProjectDialog(str(target), project, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None

    if dialog.mode == MODE_PURGE:
        if not (target / "project.json").is_file():
            QMessageBox.warning(
                parent,
                i18n.tr("没有删除"),
                i18n.tr(
                    "这个目录里没有 project.json，不像是项目目录，所以没有删除任何东西"
                    "（登记也保留着）：\n%s\n\n"
                    "如果只是不想再看到它，选「仅从项目列表移除」。"
                )
                % target,
            )
            return None
        try:
            shutil.rmtree(target)
        except OSError as error:
            logger().exception("删除项目目录失败：%s", target)
            QMessageBox.warning(parent, i18n.tr("删除失败"), str(error))
            return None
        logger().info("删除项目目录：%s", target)
    else:
        logger().info("从项目列表移除：%s", target)

    config.unregister_project(target)
    config.save()
    return dialog.mode
