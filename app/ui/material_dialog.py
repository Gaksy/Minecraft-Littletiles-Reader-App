"""导出前问一句：本次用什么材质。

三种选择：用已配置的素材包 / 现挑一个目录 / 不用材质（白模）。
用户第一次用这个工具时通常手上什么都没有，所以"不用材质"必须是**一等选项**，
并且要当场说清楚怎样才算是配好了素材。

**这里不提供、也不链接任何素材下载。** 方块贴图是 Mojang 的资源，随游戏分发；
本工具只做"读取用户自己那份游戏里提取出来的素材"，不承担分发，也不引导去下载。
所以说明里只讲"需要什么、从哪来的原理"，并把来源指向用户自己的游戏安装。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from . import design
from .widgets import wrap

HELP_TEXT = (
    "<b>原版材质</b><br>"
    "由于 Minecraft 贴图资源的版权原因，本工具不提供这些素材。<br>"
    "您可以在个人游戏客户端的版本文件夹中选择 jar 文件，例如：<br>"
    "<span style='font-family:Consolas,monospace'>"
    "&nbsp;&nbsp;.minecraft\\versions\\1.12.2\\1.12.2.jar</span>"
    "<br><br>"
    "<b>其它材质或模组方块</b><br>"
    "需要您自行选择导入 zip / rar / 模组 jar，由本工具提取其中的贴图。"
)


class MaterialChoiceDialog(QDialog):
    """返回值：'configured' / 'pick' / 'none' / 取消时为空字符串。"""

    def __init__(
        self,
        configured: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("本次导出用什么材质？")
        self._choice = ""
        self.resize(560, 360)

        layout = QVBoxLayout(self)

        if configured:
            label = QLabel("上次使用：\n%s" % configured)
            wrap(label)
            design.set_role(label, "hint")
            layout.addWidget(label)

        hint = QLabel(HELP_TEXT)
        # 上面的文案带了 <b>/<br>，显式声明富文本，别指望自动识别
        hint.setTextFormat(Qt.TextFormat.RichText)
        wrap(hint)
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(hint, 1)

        buttons = QDialogButtonBox()
        if configured:
            use_last = buttons.addButton(
                "继续使用上次", QDialogButtonBox.ButtonRole.AcceptRole
            )
            use_last.clicked.connect(lambda: self._pick("last"))
        pick = buttons.addButton(
            "打开材质管理", QDialogButtonBox.ButtonRole.AcceptRole
        )
        # 这个框只在"库里一个素材都没有"时出现；导入、启用、排序都在材质管理里做，
        # 不要在这里另开一条"选某个文件"的路——那是我做管理界面之前的旧流程。
        pick.clicked.connect(lambda: self._pick("manage"))
        none = buttons.addButton(
            "不用材质（白模）", QDialogButtonBox.ButtonRole.AcceptRole
        )
        none.clicked.connect(lambda: self._pick("none"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 固定大小：内容就这么点，不要留一片空白也不要能拖大
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

    def _pick(self, choice: str) -> None:
        self._choice = choice
        self.accept()

    @property
    def choice(self) -> str:
        return self._choice
