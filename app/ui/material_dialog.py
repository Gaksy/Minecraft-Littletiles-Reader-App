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

from .theme import colors_for

HELP_TEXT = (
    "直接选一个 zip / rar / jar 文件即可，应用会自己认：\n"
    "\n"
    "  · Minecraft 1.12.2 客户端 jar —— 直接生成素材包（推荐，一步到位）\n"
    "  · 资源包 / 模组 —— 目前还不能单独用（见下）\n"
    "\n"
    "客户端 jar 在你自己的游戏目录里，通常在：\n"
    "\n"
    "    <.minecraft>\\versions\\1.12.2\\1.12.2.jar\n"
    "\n"
    "它本身就是个压缩包，里面 assets/minecraft/ 装着 blockstates、models、\n"
    "textures——应用会解压、整理成素材包，只用你自己的游戏文件。\n"
    "\n"
    "注意：别去 <.minecraft>\\assets\\ 找。那里只有声音和语言文件；\n"
    "贴图是 1.13 之后才搬到那个目录的，1.12.2 一直放在 jar 里。\n"
    "\n"
    "资源包（换皮 zip）和模组 jar 需要先有原版底子才能合并，属于后续步骤。\n"
    "\n"
    "本工具不附带、也不提供这些素材的下载：贴图是 Mojang 的资源，随游戏分发。\n"
    "不选素材也可以导出，那样得到的是没有贴图的白模。"
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
        colors = colors_for(self.palette())

        if configured:
            label = QLabel("已配置的素材包：\n%s" % configured)
            label.setWordWrap(True)
            label.setStyleSheet("color:%s;" % colors.muted.name())
            layout.addWidget(label)

        hint = QLabel(HELP_TEXT)
        hint.setWordWrap(True)
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(hint, 1)

        buttons = QDialogButtonBox()
        if configured:
            use_saved = buttons.addButton(
                "用已配置的素材包", QDialogButtonBox.ButtonRole.AcceptRole
            )
            use_saved.clicked.connect(lambda: self._pick("configured"))
        pick = buttons.addButton(
            "选择素材文件…", QDialogButtonBox.ButtonRole.AcceptRole
        )
        pick.clicked.connect(lambda: self._pick("pick"))
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
