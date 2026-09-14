"""界面多语言：源语言是简体中文，其它语言查表替换。

**为什么拿中文原文当键**：界面代码本来就是中文写死的。要给每句话编一个 id
（`export.dialog.title` 这种）然后到处改调用点，收益是"改文案不用改代码"，
代价是漏一个就显示成 id；用原文当键则漏翻的地方自动退回中文——看得懂、能用。

两层覆盖：

* `tr(text)`：手工包在代码里，管**动态**文案（带 %s / %d 的模板）；
* `translate(widget)`：建完界面后扫一遍控件树，管**静态**文案（按钮、标签、
  菜单项、分组标题、占位文字、tooltip）。扫不到、认不出的原样留着，所以
  路径、文件名、状态文字不会被误翻。

改语言要重建界面：Qt 控件里的文案是死值，切完写入配置、重启后生效
（比逐个回填更不容易漏，也不会出现"一半新语言一半旧语言"的界面）。
"""

from __future__ import annotations

import importlib
from typing import Iterable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QWidget,
)

#: (代码, 自称)。代码用 BCP 47：zh-Hans / zh-Hant / en / ja / ko / de / fr
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("zh-Hans", "简体中文"),
    ("zh-Hant", "繁體中文"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("de", "Deutsch"),
    ("fr", "Français"),
)

SOURCE = "zh-Hans"
_current = SOURCE
_tables: dict[str, dict[str, str]] = {}


def codes() -> list[str]:
    return [code for code, _ in LANGUAGES]


def display_name(code: str) -> str:
    for item, name in LANGUAGES:
        if item == code:
            return name
    return SOURCE


def current() -> str:
    return _current


def system_language() -> str:
    """按系统地区猜一个：认得出来就用，认不出用简体中文。"""

    try:
        from PySide6.QtCore import QLocale

        name = QLocale.system().name()          # 例如 "zh_CN" / "en_US" / "ja_JP"
    except Exception:                           # 还没建 QApplication 之类
        name = ""
    code = (name or "").replace("-", "_")
    if code.startswith("zh"):
        return "zh-Hant" if code.lower() in ("zh_tw", "zh_hk", "zh_mo") else "zh-Hans"
    for candidate in codes():
        if code.startswith(candidate):
            return candidate
    return SOURCE


def set_language(code: str) -> str:
    """切换当前语言（未知代码退回简体中文）。"""

    global _current
    _current = code if code in codes() else SOURCE
    _load(_current)
    return _current


def table() -> dict[str, str]:
    _load(_current)
    return _tables[_current]


def tr(text: str) -> str:
    """翻译一句话（没翻到就原样返回）。"""

    if _current == SOURCE or not text:
        return text
    return table().get(text, text)


def tr_all(texts: Iterable[str]) -> list[str]:
    return [tr(text) for text in texts]


def translate(widget: QWidget | None) -> None:
    """扫一遍控件树，把认得的静态文案换成当前语言。

    认不出的（路径、数字、状态行）原样留着——这也是"漏翻不炸"的原因。
    """

    if widget is None or _current == SOURCE:
        return
    for child in [widget, *widget.findChildren(QWidget)]:
        # 注意顺序：QGroupBox 没有 text()（它是 title()），先判它再判 QLabel
        if isinstance(child, QGroupBox):
            if child.title():
                child.setTitle(tr(child.title()))
        elif isinstance(child, QLabel):
            if child.text():
                child.setText(tr(child.text()))
        elif isinstance(child, QAbstractButton):
            if child.text():
                child.setText(tr(child.text()))
        elif isinstance(child, QLineEdit):
            if child.placeholderText():
                child.setPlaceholderText(tr(child.placeholderText()))
        elif isinstance(child, QPlainTextEdit):
            if child.placeholderText():
                child.setPlaceholderText(tr(child.placeholderText()))
        elif isinstance(child, QComboBox):
            for index in range(child.count()):
                child.setItemText(index, tr(child.itemText(index)))
        elif isinstance(child, QTableWidget):
            # 表头文字是模型里的 item，不是控件，得单独翻
            for column in range(child.columnCount()):
                item = child.horizontalHeaderItem(column)
                if item is not None and item.text():
                    item.setText(tr(item.text()))
        if child.toolTip():
            child.setToolTip(tr(child.toolTip()))
    # 菜单项不是控件（是 QAction），得单独走一遍
    for action in widget.findChildren(QAction):
        if action.text():
            action.setText(tr(action.text()))


def _load(code: str) -> None:
    if code in _tables:
        return
    if code == SOURCE:
        _tables[code] = {}
        return
    module_name = "app.i18n_data.%s" % code.replace("-", "_").lower()
    try:
        module = importlib.import_module(module_name)
        _tables[code] = dict(getattr(module, "STRINGS", {}))
    except Exception:          # 数据文件缺失/写坏了也不该让应用起不来
        _tables[code] = {}
