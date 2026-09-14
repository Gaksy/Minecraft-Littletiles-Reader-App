"""「视图 → 语言」菜单：主界面与项目界面共用同一份。

之前只有主界面有语言菜单，项目窗口里翻不到——两处各写一份又容易走样，
所以抽到这里：**任何人调用都拿到同样的七个语言 + 跟随系统**。

语言切换要重启才生效：Qt 控件里的文案是死值，整窗重建比逐个回填更稳（见 docs/design.md §5.2）。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMessageBox

from .. import i18n
from . import popup


def build_language_menu(window, config, save_config: Callable[[str], None], label: str | None = None):
    """给窗口的菜单栏造一个「语言」子菜单（返回该 QMenu，调用方自己 addMenu）。

    `save_config` 用来落盘（各窗口手里的 config 保存方式略有不同），
    `label` 可覆盖菜单标题（默认取 i18n 的"语言"）。
    """

    language = window.menuBar().addMenu(label or i18n.tr("语言")) if False else None
    # 由调用方决定挂到哪个父菜单下，这里只负责"填内容"
    from PySide6.QtWidgets import QMenu

    menu = QMenu(label or i18n.tr("语言"), window)
    group = QActionGroup(window)
    group.setExclusive(True)

    def choose(code: str) -> None:
        chosen = code or i18n.system_language()
        config.language = code
        save_config("语言")
        popup.info(
            window,
            i18n.tr("语言"),
            i18n.tr("界面语言已切换为 %s，重启应用后生效。") % i18n.display_name(chosen),
        )

    for code, name in i18n.LANGUAGES:
        action = menu.addAction(name)
        action.setCheckable(True)
        action.setChecked(code == i18n.current())
        action.triggered.connect(lambda _checked=False, chosen=code: choose(chosen))
        group.addAction(action)

    menu.addSeparator()
    follow = menu.addAction(i18n.tr("跟随系统"))
    follow.setCheckable(True)
    follow.setChecked(not config.language)
    follow.triggered.connect(lambda _checked=False: choose(""))
    menu.language_group = group          # 留个引用，别被 GC 掉
    return menu
