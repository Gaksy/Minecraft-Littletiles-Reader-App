"""启动界面的项目列表：卡片（封面 · 名称 · 描述）+ 新建 / 添加 / 重定位。

项目目录是用户自己挑的，所以列表来自**登记表**（应用配置里），不是扫目录树；
卡片内容以项目里的 `project.json` 为准（项目可能被搬到别的地方）。

三种卡片：

* 正常：点一下进项目
* 项目不可用（`project.json` 读不到，多半是目录被搬走/删了）：给「重新定位」与
  「从列表移除」——**不自动删登记**，用户的东西不该被程序悄悄丢掉
* 素材绑定失效由项目界面提示，这里不掺和
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..applog import logger
from ..config import AppConfig
from ..project import Project
from .theme import colors_for
from .widgets import wrap

COVER_SIZE = 72
CARD_MIN_WIDTH = 250
COLUMNS = 3


class ProjectCard(QWidget):
    """一张项目卡片。"""

    opened = Signal(str)        # 项目目录
    relocate = Signal(str)      # 要重新定位的项目目录（原来是哪个）
    removed = Signal(str)       # 从列表移除登记

    def __init__(
        self, directory: str, project: Project | None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.directory = directory
        self.project = project
        self._hover = False
        self.setMinimumWidth(CARD_MIN_WIDTH)
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
        text.addStretch(1)
        top.addLayout(text, 1)
        layout.addLayout(top)

        self.actions = QHBoxLayout()
        self.btn_relocate = QPushButton("重新定位…")
        self.btn_relocate.clicked.connect(lambda: self.relocate.emit(self.directory))
        self.btn_forget = QPushButton("从列表移除")
        self.btn_forget.clicked.connect(lambda: self.removed.emit(self.directory))
        self.actions.addWidget(self.btn_relocate)
        self.actions.addWidget(self.btn_forget)
        self.actions.addStretch(1)
        layout.addLayout(self.actions)

        muted = colors_for(self.palette()).muted.name()
        self.description.setStyleSheet("color:%s;" % muted)
        self.path_label.setStyleSheet("color:%s; font-size:11px;" % muted)

    def _refresh(self) -> None:
        muted = colors_for(self.palette()).muted.name()
        if self.project is None:
            self.name.setText("项目不可用")
            self.description.setText("读不到 project.json——目录可能被搬走或删掉了。")
            self.path_label.setText(self.directory)
            self.cover.setText("?")
            self.cover.setStyleSheet(
                "border:1px dashed %s; color:%s; border-radius:6px;" % (muted, muted)
            )
            self.btn_relocate.setVisible(True)
            self.btn_forget.setVisible(True)
            return

        self.name.setText(self.project.name or "未命名项目")
        self.description.setText(self.project.description or "（没有描述）")
        self.path_label.setText(self.project.directory)
        cover = self.project.cover_png()
        if cover is None:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("无封面")
            self.cover.setStyleSheet(
                "border:1px dashed %s; color:%s; border-radius:6px;" % (muted, muted)
            )
        else:
            pixmap = QPixmap(str(cover)).scaled(
                COVER_SIZE, COVER_SIZE,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cover.setPixmap(pixmap)
            self.cover.setText("")
            self.cover.setStyleSheet("border:1px solid %s; border-radius:6px;" % muted)
        self.btn_relocate.setVisible(False)
        self.btn_forget.setVisible(False)
        self._paint_border()

    def _paint_border(self) -> None:
        colors = colors_for(self.palette())
        border = colors.accent_strong if self._hover else colors.border
        self.setStyleSheet(
            "ProjectCard { border:1px solid %s; border-radius:8px; background:%s; }"
            % (border.name(), colors.surface.name())
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
        wrap(self.count_label)
        header.addWidget(self.count_label)
        header.addStretch(1)
        self.btn_new = QPushButton("新建项目…")
        self.btn_new.clicked.connect(self._new_project)
        self.btn_add = QPushButton("添加已有项目…")
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

        muted = colors_for(self.palette()).muted.name()
        self.count_label.setStyleSheet("color:%s;" % muted)

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
            card.removed.connect(self._forget)
            self.cards.addWidget(card, index // COLUMNS, index % COLUMNS)

        if not entries:
            hint = QLabel("还没有项目。新建一个，或把已有的项目目录添加进来。")
            wrap(hint)
            hint.setStyleSheet(
                "color:%s;" % colors_for(self.palette()).muted.name()
            )
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

    def _forget(self, directory: str) -> None:
        if (
            QMessageBox.question(
                self,
                "从列表移除",
                "把「%s」从项目列表里移除？\n\n只是不再登记，磁盘上的目录不动。"
                % directory,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.config.unregister_project(directory)
        self.config.save()
        self.refresh()
