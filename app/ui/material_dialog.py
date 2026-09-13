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
    "想要方块带贴图，需要一个「素材包」目录，里面至少要有：\n"
    "  · block_textures.tsv  —— 方块 → 六面贴图 的映射表\n"
    "  · textures/           —— 对应的 PNG\n"
    "  · block_ids.tsv       —— 没有它时普通方块只能导出白模\n"
    "\n"
    "这些东西来自你自己的 Minecraft 1.12.2 客户端，通常在：\n"
    "\n"
    "    <.minecraft>\\versions\\1.12.2\\1.12.2.jar\n"
    "\n"
    "这个 jar 本身就是个压缩包——用 WinRAR / 7-Zip 打开它，里面的\n"
    "assets/minecraft/ 就是 blockstates、models、textures。\n"
    "\n"
    "注意：别去 <.minecraft>\\assets\\ 找。那里只有声音和语言文件；\n"
    "贴图是 1.13 之后才搬到那个目录的，1.12.2 一直放在 jar 里。\n"
    "\n"
    "本工具不附带、也不提供这些素材的下载：贴图是 Mojang 的资源，随游戏分发。\n"
    "不提供素材包也可以导出，那样得到的是没有贴图的白模。"
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
        pick = buttons.addButton("选择素材包…", QDialogButtonBox.ButtonRole.AcceptRole)
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
