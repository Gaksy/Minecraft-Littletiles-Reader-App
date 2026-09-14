"""检查更新的结果：一句话 + 版本对比 + 下载入口。

不在这里下载安装包：发布形态还没定（M5 打包分发），客户端现在只负责
"告诉你有没有新版、去哪儿拿"。服务器上 `ready=false`（还没配好地址）时
明确写"还没发布"，不要给一个点不动的按钮。
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..update import UpdateInfo
from . import design
from .widgets import wrap


class UpdateDialog(QDialog):
    """把一次检查结果摆出来。"""

    def __init__(self, info: UpdateInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("检查更新"))
        self.setMinimumWidth(460)
        self.info = info

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_md)

        if info.has_update:
            head = i18n.tr("有新版本：%s → %s") % (info.current, info.latest)
            role = "ok"
        elif info.latest:
            head = i18n.tr("已是最新版本（%s）") % info.current
            role = "ok"
        else:
            head = i18n.tr("服务器上还没有当前平台（%s）的发布记录") % info.platform
            role = "warn"

        title = QLabel(head)
        design.set_role(title, "subtitle")
        wrap(title)
        layout.addWidget(title)

        if info.latest:
            detail = i18n.tr("当前版本：%s\n服务器版本：%s") % (info.current, info.latest)
            if info.note:
                detail += "\n" + info.note
            label = QLabel(detail)
            wrap(label)
            layout.addWidget(label)

        plan = i18n.tr(
            "更新日志与最低支持版本还没在服务器上；现在只提示版本号与下载地址。"
        )
        hint = QLabel(plan)
        design.set_role(hint, "hint")
        wrap(hint)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        if info.url:
            open_page = QPushButton(i18n.tr("打开下载页"))
            open_page.clicked.connect(self._open)
            buttons.addButton(open_page, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)
        i18n.translate(self)

    def _open(self) -> None:
        if self.info.url:
            QDesktopServices.openUrl(QUrl(self.info.url))
