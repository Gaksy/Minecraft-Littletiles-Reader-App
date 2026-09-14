"""启动界面的项目列表：卡片（封面 · 名称 · 描述）+ 新建 / 添加 / 重定位 / 删除。

项目目录是用户自己挑的，所以列表来自**登记表**（应用配置里），不是扫目录树；
卡片内容以项目里的 `project.json` 为准（项目可能被搬到别的地方）。

三种卡片：

* 正常：点一下进项目
* 项目不可用（`project.json` 读不到，多半是目录被搬走/删了）：给「重新定位」与
  「删除项目」——**不自动删登记**，用户的东西不该被程序悄悄丢掉
* 素材绑定失效由项目界面提示，这里不掺和
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..applog import logger
from ..config import AppConfig
from ..project import Project
from ..storage import dir_size, human_size
from . import design
from .widgets import wrap

COVER_SIZE = 72
CARD_MIN_WIDTH = 250
COLUMNS = 3


class ProjectCard(QWidget):
    """一张项目卡片。"""

    opened = Signal(str)        # 项目目录
    relocate = Signal(str)      # 要重新定位的项目目录（原来是哪个）
    delete_requested = Signal(str)      # 删除项目（怎么删由对话框问）

    def __init__(
        self, directory: str, project: Project | None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.directory = directory
        self.project = project
        self._hover = False
        self.setMinimumWidth(CARD_MIN_WIDTH)
        self.setMinimumHeight(120)      # 同一行的卡片高度一致，看着才整齐
        # 用 objectName 选样式：按"类名"选（ProjectCard {...}）在 PySide 子类上
        # 不一定匹配得到，那样边框和底色会静悄悄地不生效
        self.setObjectName("ProjectCard")
        # 纯 QWidget 不画样式表里的背景/边框，除非显式打开这个属性
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if project is not None
            else Qt.CursorShape.ArrowCursor
        )
        self._build_ui()
        self._refresh()

    # ---- 界面 ------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        top = QHBoxLayout()
        self.cover = QLabel()
        self.cover.setFixedSize(COVER_SIZE, COVER_SIZE)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        self.name = QLabel()
        self.name.setFont(QFont("", 11, QFont.Weight.Bold))
        wrap(self.name)
        text.addWidget(self.name)
        self.description = QLabel()
        wrap(self.description)
        self.description.setMinimumHeight(34)
        text.addWidget(self.description)
        self.path_label = QLabel()
        wrap(self.path_label)
        text.addWidget(self.path_label)
        # 不在卡片里留弹性空间：卡片必须贴着内容长，不然被拉高之后
        # 名称在上、按钮在下，中间空一大片
        top.addLayout(text, 1)
        layout.addLayout(top)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(design.METRICS.gap_sm)
        self.btn_relocate = QPushButton("重新定位")
        self.btn_relocate.clicked.connect(lambda: self.relocate.emit(self.directory))
        self.btn_delete = QPushButton("删除项目")
        design.set_variant(self.btn_delete, "danger")
        self.btn_delete.setToolTip("从列表移除，或者连同项目目录一起删除")
        self.btn_delete.clicked.connect(
            lambda: self.delete_requested.emit(self.directory)
        )
        self.actions.addWidget(self.btn_relocate)
        self.actions.addWidget(self.btn_delete)
        self.actions.addStretch(1)
        layout.addLayout(self.actions)

        design.set_role(self.description, "hint")
        design.set_role(self.path_label, "dim")

    def _refresh(self) -> None:
        theme = design.theme()
        if self.project is None:
            self.name.setText("项目不可用")
            self.description.setText("读不到 project.json——目录可能被搬走或删掉了。")
            self.path_label.setText(self.directory)
            self.cover.setText("?")
            self.cover.setStyleSheet(
                "border:%dpx dashed %s; color:%s;"
                % (design.METRICS.border_width, theme.border, theme.text_3)
            )
            self.btn_relocate.setVisible(True)
            self.btn_delete.setVisible(True)
            self._paint_border()
            return

        self.name.setText(self.project.name or "未命名项目")
        self.description.setText(self.project.description or "（没有描述）")
        self.path_label.setText(self.project.directory)
        cover = self.project.cover_png()
        if cover is None:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("无封面")
            self.cover.setStyleSheet(
                "border:%dpx dashed %s; color:%s;"
                % (design.METRICS.border_width, theme.border, theme.text_3)
            )
        else:
            pixmap = QPixmap(str(cover)).scaled(
                COVER_SIZE, COVER_SIZE,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cover.setPixmap(pixmap)
            self.cover.setText("")
            self.cover.setStyleSheet(
                "border:%dpx solid %s;" % (design.METRICS.border_width, theme.border)
            )
        self.btn_relocate.setVisible(False)
        self.btn_delete.setVisible(True)
        self._paint_border()

    def _paint_border(self) -> None:
        """卡片描边：悬停时用强调绿，平时用普通描边（直角 + 2px，与网站一致）。"""

        theme = design.theme()
        border = theme.accent if self._hover else theme.border
        self.setStyleSheet(
            "#ProjectCard { border:%dpx solid %s; background:%s; }"
            % (design.METRICS.border_width, border, theme.sidebar)
        )

    # ---- 交互 ------------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._paint_border()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._paint_border()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.project is not None:
            self.opened.emit(self.project.directory)
        super().mouseReleaseEvent(event)


class _DeleteProjectDialog(QDialog):
    """删除项目：从列表移除，或者连同项目目录一起删。

    两种后果差别很大，所以放在一个对话框里讲清楚：
    * 从列表移除：只动应用里的登记，磁盘上的目录一个字节都不碰；
    * 删除目录：素材副本、贴图库、导出产物、历史记录全没，且**不可恢复**——
      所以那条选项要额外勾一个确认框才让点「删除」。
    """

    def __init__(self, directory: str, project: Project | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("删除项目")
        self.setMinimumWidth(520)
        self.directory = directory
        self.mode = "forget"
        path = Path(directory)
        exists = path.is_dir()
        size = dir_size(path) if exists else 0
        name = (project.name if project is not None else "") or path.name or directory

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_md)

        title = QLabel("要删除「%s」吗？" % name)
        design.set_role(title, "subtitle")
        layout.addWidget(title)

        where = QLabel(str(path))
        wrap(where)
        design.set_role(where, "dim")
        layout.addWidget(where)

        self.opt_forget = QRadioButton("仅从项目列表移除（磁盘上的目录保留）")
        self.opt_forget.setChecked(True)
        self.opt_purge = QRadioButton(
            "删除项目目录（释放约 %s）" % human_size(size)
            if exists
            else "删除项目目录（这个目录已经不在磁盘上了）"
        )
        self.opt_purge.setEnabled(exists)
        self.opt_forget.toggled.connect(self._sync)
        layout.addWidget(self.opt_forget)
        layout.addWidget(self.opt_purge)

        self.confirm = QCheckBox(
            "我确认永久删除这个目录：素材副本、贴图库、导出产物、历史记录都会一起没有"
        )
        self.confirm.setEnabled(False)
        self.confirm.toggled.connect(self._sync)
        layout.addWidget(self.confirm)

        if not exists:
            hint = QLabel("目录不在了，只能把这条登记从列表里删掉。")
            wrap(hint)
            design.set_role(hint, "hint")
            layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.btn_ok.setText("删除")
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
        self.mode = "purge" if self.opt_purge.isChecked() else "forget"
        super().accept()


class ProjectListWidget(QWidget):
    """项目卡片区 + 新建 / 添加 / 刷新。"""

    opened = Signal(str)
    deleted = Signal(str)       # 项目目录被删掉了（主界面据此关掉开着的窗口）

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        title = QLabel("项目")
        title.setFont(QFont("", 11, QFont.Weight.Bold))
        header.addWidget(title)
        self.count_label = QLabel()
        header.addWidget(self.count_label)
        header.addStretch(1)
        self.btn_new = QPushButton("新建项目")
        self.btn_new.clicked.connect(self._new_project)
        self.btn_add = QPushButton("添加已有项目")
        self.btn_add.clicked.connect(self._add_existing)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        for button in (self.btn_new, self.btn_add, self.btn_refresh):
            header.addWidget(button)
        root.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(150)
        self.cards_host = QWidget()
        self.cards = QGridLayout(self.cards_host)
        self.cards.setContentsMargins(2, 2, 2, 2)
        self.scroll.setWidget(self.cards_host)
        root.addWidget(self.scroll, 1)

        design.set_role(self.count_label, "hint")

    # ---- 刷新 ------------------------------------------------------------

    def refresh(self) -> None:
        while self.cards.count():
            item = self.cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        entries = self.config.project_paths()
        available = 0
        for index, directory in enumerate(entries):
            project = Project.load(directory)
            if project is not None:
                available += 1
                # 项目被搬过地方：以项目内为准，顺手更新登记表
                if str(project.path) != directory:
                    self.config.unregister_project(directory)
                    self.config.register_project(project.path)
                    self.config.save()
            card = ProjectCard(directory, project, self.cards_host)
            card.opened.connect(self.opened.emit)
            card.relocate.connect(self._relocate)
            card.delete_requested.connect(self._delete_project)
            self.cards.addWidget(card, index // COLUMNS, index % COLUMNS)
            # 依次淡入：列表刷新时看得出"这些卡片是刚排好的"
            design.motion.fade_in(card, delay=min(index, 8) * 40)

        # 列等宽、最后一行贴顶：不然卡片会被 GridLayout 拉满整块可用高度
        for column in range(COLUMNS):
            self.cards.setColumnStretch(column, 1)
        rows = (len(entries) + COLUMNS - 1) // COLUMNS
        for row in range(max(rows, 1)):
            self.cards.setRowStretch(row, 0)
        self.cards.setRowStretch(max(rows, 1), 1)

        if not entries:
            hint = QLabel("还没有项目。新建一个，或把已有的项目目录添加进来。")
            wrap(hint)
            design.set_role(hint, "hint")
            self.cards.addWidget(hint, 0, 0, 1, COLUMNS)
            self.count_label.setText("")
        else:
            self.count_label.setText(
                "共 %d 个%s"
                % (
                    len(entries),
                    "" if available == len(entries) else "（%d 个不可用）" % (len(entries) - available),
                )
            )

    # ---- 新建 / 添加 / 重定位 --------------------------------------------

    def _new_project(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "选择项目目录（可以在对话框里新建一个文件夹）"
        )
        if not chosen:
            return
        directory = Path(chosen)
        if (directory / "project.json").is_file():
            self.config.register_project(directory)
            self.config.save()
            self.refresh()
            return
        default_name = directory.name or "我的项目"
        name, ok = QInputDialog.getText(self, "新建项目", "项目名：", text=default_name)
        if not ok:
            return
        try:
            project = Project.create(directory, name.strip() or default_name)
        except OSError as error:
            QMessageBox.warning(self, "建不了项目", str(error))
            return
        self.config.register_project(project.path)
        self.config.save()
        logger().info("新建项目：%s（%s）", project.name, project.path)
        self.refresh()

    def _add_existing(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择已有的项目目录")
        if not chosen:
            return
        directory = Path(chosen)
        if Project.load(directory) is None:
            QMessageBox.warning(
                self,
                "这个目录不是项目",
                "里面没有 %s。\n\n如果项目在别的位置，请选到项目目录本身；"
                "如果是刚拿到的项目，先把它解压出来。" % "project.json",
            )
            return
        self.config.register_project(directory)
        self.config.save()
        logger().info("添加已有项目：%s", directory)
        self.refresh()

    def _relocate(self, old_directory: str) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "这个项目现在在哪个目录？"
        )
        if not chosen:
            return
        directory = Path(chosen)
        project = Project.load(directory)
        if project is None:
            QMessageBox.warning(self, "还是找不到", "这个目录里也没有 project.json。")
            return
        self.config.unregister_project(old_directory)
        self.config.register_project(project.path)
        self.config.save()
        logger().info("项目重新定位：%s → %s", old_directory, project.path)
        self.refresh()

    def _delete_project(self, directory: str) -> None:
        """删除项目：只删登记，或者连目录一起删（对话框里选）。"""

        project = Project.load(directory)
        dialog = _DeleteProjectDialog(directory, project, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if dialog.mode == "purge":
            target = Path(directory)
            # 双保险：只删"确实是一个项目目录"的目录（里面有 project.json），
            # 免得一个手滑把别的目录递归删了。
            if not (target / "project.json").is_file():
                QMessageBox.warning(
                    self,
                    "没有删除",
                    "这个目录里没有 project.json，不像是项目目录，所以没有删除任何东西"
                    "（登记也保留着）：\n%s\n\n"
                    "如果只是不想再看到它，选「仅从项目列表移除」。" % target,
                )
                return
            try:
                shutil.rmtree(target)
            except OSError as error:
                logger().exception("删除项目目录失败：%s", target)
                QMessageBox.warning(self, "删除失败", str(error))
                return
            logger().info("删除项目目录：%s", target)
            self.deleted.emit(str(target))
        else:
            logger().info("从项目列表移除：%s", directory)

        self.config.unregister_project(directory)
        self.config.save()
        self.refresh()
