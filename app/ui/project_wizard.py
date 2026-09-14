"""新建项目的配置向导：项目名 → 简介 → 存档目录 → 封面。

两页，按"先起名、再指位置"的顺序来：

1. **项目名（必填）** 与简介；
2. **存档目录（必填，要真的存在）** 与封面（可选）。

为什么存档目录必填：项目模式的导出全靠它（默认存档位置就是从这里来的），
建完再让它空着，第一次导出的体验就是"点了导出再被问要存档"。所以这里一次问清，
并且当场用 `savefolder.inspect` 判断"这个目录像不像存档根目录"，把结果写在下面——
选错一层（选进 `region/` 或选到 `saves/`）是这类工具最常见、也最难自查的错误。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from .. import i18n
from ..config import AppConfig
from ..savefolder import inspect as inspect_save
from . import design
from . import popup
from .widgets import wrap

COVER_PREVIEW = 96


class NewProjectWizard(QWizard):
    """收集"建一个项目"需要的四样东西。"""

    def __init__(self, config: AppConfig, directory: Path, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.directory = Path(directory)
        self.setWindowTitle(i18n.tr("新建项目"))
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setMinimumWidth(560)
        # Qt 自带的按钮文案随发行版而变，直接写死（i18n 里各语言一份）
        for button, key in (
            (QWizard.WizardButton.BackButton, "上一步"),
            (QWizard.WizardButton.NextButton, "下一步"),
            (QWizard.WizardButton.FinishButton, "完成"),
            (QWizard.WizardButton.CancelButton, "取消"),
        ):
            self.setButtonText(button, i18n.tr(key))

        self.name_page = _NamePage(self.directory.name, self)
        self.source_page = _SourcePage(self, self)
        self.addPage(self.name_page)
        self.addPage(self.source_page)

    def values(self) -> dict:
        return {
            "name": self.name_page.name_edit.text().strip() or self.directory.name,
            "description": self.name_page.description_edit.toPlainText(),
            "save_root": self.source_page.save_edit.text().strip(),
            "cover": self.source_page.cover_path,
        }


class _NamePage(QWizardPage):
    """第一页：项目名（必填）与简介。"""

    def __init__(self, default_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setTitle(i18n.tr("这个项目叫什么？"))
        self.setSubTitle(i18n.tr("名称与简介只影响界面显示，随时可以在「项目配置」里改。"))

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_md)
        layout.addWidget(QLabel(i18n.tr("项目名（必填）")))
        self.name_edit = QLineEdit(default_name)
        self.name_edit.setPlaceholderText(i18n.tr("例如：地铁站 · 站台吊顶"))
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel(i18n.tr("简介")))
        self.description_edit = QPlainTextEdit()
        self.description_edit.setFixedHeight(96)
        self.description_edit.setPlaceholderText(
            i18n.tr("这个项目是做什么的（可以留空）")
        )
        layout.addWidget(self.description_edit)
        layout.addStretch(1)

    def validatePage(self) -> bool:  # noqa: N802 (Qt 命名)
        if not self.name_edit.text().strip():
            popup.warning(
                self, i18n.tr("还差一步"), i18n.tr("请先填项目名。")
            )
            return False
        return True


class _SourcePage(QWizardPage):
    """第二页：存档目录（必填）与封面（可选）。"""

    def __init__(self, wizard: NewProjectWizard, parent=None) -> None:
        super().__init__(parent)
        self.wizard = wizard
        self.cover_path = ""
        self.setTitle(i18n.tr("存档在哪？"))
        self.setSubTitle(
            i18n.tr("存档目录是必须的：项目模式的导出默认就从这里取区块。")
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_sm)

        layout.addWidget(QLabel(i18n.tr("存档目录（必填）")))
        pick_row = QHBoxLayout()
        self.save_edit = QLineEdit()
        self.save_edit.setPlaceholderText(
            i18n.tr("存档根目录（含 level.dat 的那个文件夹）")
        )
        self.save_edit.textChanged.connect(self._refresh_status)
        pick = QPushButton(i18n.tr("选择文件夹"))
        pick.clicked.connect(self._pick_save)
        pick_row.addWidget(self.save_edit, 1)
        pick_row.addWidget(pick)
        layout.addLayout(pick_row)

        self.save_status = QLabel()
        wrap(self.save_status)
        layout.addWidget(self.save_status)

        layout.addWidget(QLabel(i18n.tr("封面（可选）")))
        cover_row = QHBoxLayout()
        self.cover_preview = QLabel()
        self.cover_preview.setFixedSize(COVER_PREVIEW, COVER_PREVIEW)
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setText(i18n.tr("无封面"))
        cover_row.addWidget(self.cover_preview)
        self.btn_cover = QPushButton(i18n.tr("选择封面图片"))
        self.btn_cover.clicked.connect(self._pick_cover)
        self.btn_cover_clear = QPushButton(i18n.tr("清除封面"))
        self.btn_cover_clear.clicked.connect(self._clear_cover)
        buttons = QVBoxLayout()
        buttons.addWidget(self.btn_cover)
        buttons.addWidget(self.btn_cover_clear)
        cover_row.addLayout(buttons)
        cover_row.addStretch(1)
        layout.addLayout(cover_row)
        layout.addStretch(1)
        self._refresh_cover()
        self._refresh_status()

    # ---- 交互 ----

    def _pick_save(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, i18n.tr("选择存档根目录"))
        if chosen:
            self.save_edit.setText(chosen)

    def _refresh_status(self) -> None:
        text = self.save_edit.text().strip()
        if not text:
            self.save_status.setText(i18n.tr("存档目录是必填项。"))
            design.set_role(self.save_status, "warn")
            return
        result = inspect_save(text)
        prefix = "✓ " if result.ok else i18n.tr("！")
        message = result.message + (("　%s" % result.hint) if result.hint else "")
        self.save_status.setText(prefix + message)
        design.set_role(self.save_status, "ok" if result.ok else "warn")

    def _pick_cover(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("选择封面图片"), "",
            i18n.tr("图片 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)"),
        )
        if not chosen:
            return
        self.cover_path = chosen
        self._refresh_cover()

    def _clear_cover(self) -> None:
        self.cover_path = ""
        self._refresh_cover()

    def _refresh_cover(self) -> None:
        theme = design.theme()
        if self.cover_path:
            self.cover_preview.setPixmap(
                QPixmap(self.cover_path).scaled(
                    COVER_PREVIEW, COVER_PREVIEW,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.cover_preview.setText("")
            self.cover_preview.setStyleSheet(
                "border:%dpx solid %s;" % (design.METRICS.border_width, theme.border)
            )
            self.btn_cover_clear.setEnabled(True)
            return
        self.cover_preview.setPixmap(QPixmap())
        self.cover_preview.setText(i18n.tr("无封面"))
        self.cover_preview.setStyleSheet(
            "border:%dpx dashed %s; color:%s;"
            % (design.METRICS.border_width, theme.border, theme.text_3)
        )
        self.btn_cover_clear.setEnabled(False)

    # ---- 校验 ----

    def validatePage(self) -> bool:  # noqa: N802 (Qt 命名)
        text = self.save_edit.text().strip()
        if not text:
            popup.warning(
                self, i18n.tr("还差一步"), i18n.tr("存档目录是必须的，请先选一个。")
            )
            return False
        if not Path(text).is_dir():
            popup.warning(
                self,
                i18n.tr("还差一步"),
                i18n.tr("这个路径不存在，或者不是目录：\n%s") % text,
            )
            return False
        if not inspect_save(text).ok and (
            popup.ask(
                self,
                i18n.tr("确认存档目录"),
                i18n.tr(
                    "这个目录看起来不像是存档根目录（没有 level.dat 或 region/）。\n\n"
                    "仍然用它作为本项目的默认存档位置吗？"
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return False
        return True
