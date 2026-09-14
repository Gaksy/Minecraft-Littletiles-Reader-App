"""启动界面的项目列表：一行一个项目（封面 · 名称 · 描述 · 目录）+ 新建 / 添加。

项目目录是用户自己挑的，所以列表来自**登记表**（应用配置里），不是扫目录树；
卡片内容以项目里的 `project.json` 为准（项目可能被搬到别的地方）。

三种卡片：

* 正常：点一下进项目
* 项目不可用（`project.json` 读不到，多半是目录被搬走/删了）：给「重新定位」——
  **不自动删登记**，用户的东西不该被程序悄悄丢掉
* 素材绑定失效由项目界面提示，这里不掺和

**删除不在这一页**：卡片是"打开项目"的地方，删除要进到项目里（菜单「项目 → 删除项目」），
按错了代价太大，不该在启动页一眼就能点到。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..applog import logger
from ..config import AppConfig
from ..project import Project
from . import design
from .widgets import wrap

COVER_SIZE = 72
CARD_MIN_WIDTH = 250
COLUMNS = 1                 # 一行一个项目：名字和目录都看得全，不用横向找


class ProjectCard(QWidget):
    """一张项目卡片。"""

    opened = Signal(str)        # 项目目录
    relocate = Signal(str)      # 要重新定位的项目目录（原来是哪个）

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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(design.METRICS.gap_md)

        self.cover = QLabel()
        self.cover.setFixedSize(COVER_SIZE, COVER_SIZE)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(design.METRICS.gap_xs)
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
        layout.addLayout(text, 1)

        # 卡片上只留"打不开时"才用得上的动作；删除在项目界面里
        self.actions = QVBoxLayout()
        self.actions.addStretch(1)
        self.btn_relocate = QPushButton("重新定位")
        self.btn_relocate.clicked.connect(lambda: self.relocate.emit(self.directory))
        self.actions.addWidget(self.btn_relocate)
        self.actions.addStretch(1)
        layout.addLayout(self.actions)

        design.set_role(self.description, "hint")
        design.set_role(self.path_label, "dim")
        i18n.translate(self)

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
            self._paint_border()
            i18n.translate(self)
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
        self._paint_border()
        i18n.translate(self)

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


class ProjectListWidget(QWidget):
    """项目卡片区 + 新建 / 添加 / 刷新。"""

    opened = Signal(str)

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
        i18n.translate(self)

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

        # 配置向导：项目名 → 简介 → 存档目录（必填）→ 封面
        from .project_wizard import NewProjectWizard

        wizard = NewProjectWizard(self.config, directory, self)
        if wizard.exec() != NewProjectWizard.DialogCode.Accepted:
            return
        values = wizard.values()
        try:
            project = Project.create(directory, values["name"])
        except OSError as error:
            QMessageBox.warning(self, "建不了项目", str(error))
            return
        project.description = values["description"]
        project.save_root = values["save_root"]
        project.save()
        if values["cover"]:
            project.set_cover(values["cover"])
        self.config.register_project(project.path)
        self.config.remember_save(values["save_root"])
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
