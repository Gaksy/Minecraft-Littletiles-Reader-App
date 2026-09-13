"""主题管理器：一处设置，全局生效。

`install()` 在启动时调用一次，之后任何地方都用 `theme()` 取当前主题的语义色。
切换主题（浅色/深色）时重新套 QSS、同步 Qt 调色板，并发 `changed` 信号——
自绘控件（区块格子、容量条等）连这个信号重绘即可。

主题名与网站一致：`"dark"`（默认）与 `"light"`。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ...applog import logger
from .fonts import font_families, load_fonts
from .qss import stylesheet_for
from .tokens import METRICS, Theme, theme_by_name


class ThemeManager(QObject):
    """持有当前主题，负责把它应用到整个 QApplication。"""

    changed = Signal()

    def __init__(self, app: QApplication | None = None, theme_name: str = "dark") -> None:
        super().__init__()
        self._app = app or QApplication.instance()
        self._theme = theme_by_name(theme_name)

    # ---- 查询 ----

    @property
    def theme(self) -> Theme:
        return self._theme

    @property
    def name(self) -> str:
        return self._theme.name

    @property
    def is_dark(self) -> bool:
        return self._theme.is_dark

    # ---- 切换 ----

    def apply(self, theme_name: str | None = None) -> Theme:
        """套用主题（不传名字就重套当前主题，用于字体加载完后刷新）。"""

        if theme_name:
            self._theme = theme_by_name(theme_name)
        if self._app is None:
            logger().warning("没有 QApplication，主题只记录不生效")
            return self._theme

        self._apply_font()
        self._apply_palette()
        self._app.setStyleSheet(stylesheet_for(self._theme.name))
        self._repaint_all()
        self.changed.emit()
        return self._theme

    def set_theme(self, theme_name: str) -> Theme:
        return self.apply(theme_name)

    def toggle(self) -> Theme:
        return self.apply("light" if self._theme.is_dark else "dark")

    # ---- 内部 ----

    def _apply_font(self) -> None:
        """像素字体 + 12px。字体缺了就退回系统栈，界面依旧可用。"""

        load_fonts()
        font = QFont()
        font.setFamilies(list(font_families()))
        font.setPixelSize(METRICS.font_body)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, METRICS.letter_spacing)
        self._app.setFont(font)

    def _apply_palette(self) -> None:
        """同步 Qt 调色板：让没用 QSS 覆盖到的地方（原生弹窗、tooltip 等）也同色。

        同时也让 `app.ui.theme.colors_for()` 这类自绘代码拿到正确的一组色。
        """

        t = self._theme
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(t.page))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(t.text_1))
        palette.setColor(QPalette.ColorRole.Base, QColor(t.sidebar))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(t.surface_2))
        palette.setColor(QPalette.ColorRole.Text, QColor(t.text_1))
        palette.setColor(QPalette.ColorRole.Button, QColor(t.surface_2))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(t.text_1))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(t.on_accent))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.sidebar))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(t.text_1))
        palette.setColor(QPalette.ColorRole.Mid, QColor(t.border))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_4))
        self._app.setPalette(palette)

    def _repaint_all(self) -> None:
        """让已经开着的窗口立刻换色。

        说明：QSS 只对"样式表里选中的控件"重新生效，自绘控件（区块格子、
        容量条、项目卡片）与带动态属性的控件不一定自动刷新，这里统一重绘一次；
        顺带把带 `role` / `variant` / `chip` 属性的控件重新 polish，
        避免切换主题后属性值还在、样式却是旧的。
        """

        if self._app is None:
            return
        for widget in self._app.allWidgets():
            for prop in ("role", "variant", "chip", "card", "size"):
                if widget.property(prop) is not None:
                    style = widget.style()
                    style.unpolish(widget)
                    style.polish(widget)
                    break
            widget.update()


_manager: ThemeManager | None = None


def install(app: QApplication | None = None, theme_name: str = "dark") -> ThemeManager:
    """创建并应用全局主题管理器（重复调用只更新主题）。"""

    global _manager
    if _manager is None:
        _manager = ThemeManager(app, theme_name)
    _manager.apply(theme_name)
    return _manager


def manager() -> ThemeManager:
    """取全局管理器；还没 install 过就先装上（默认深色），保证不会拿到 None。"""

    global _manager
    if _manager is None:
        _manager = ThemeManager(QApplication.instance(), "dark")
        _manager.apply()
    return _manager


def theme() -> Theme:
    """当前主题的语义色（界面代码最常用的入口）。"""

    return manager().theme


def set_theme(theme_name: str) -> Theme:
    """切换主题（并立即生效）。"""

    return manager().set_theme(theme_name)


def toggle_theme() -> Theme:
    """深色 ↔ 浅色。"""

    return manager().toggle()


def is_dark_theme() -> bool:
    """当前是不是深色主题。"""

    return manager().is_dark


def reset() -> None:
    """清掉全局管理器（测试用）。"""

    global _manager
    _manager = None
