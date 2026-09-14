"""首次启动的许可协议同意框：看清单 → 看全文 → 勾选 → 同意才能继续。

设计上刻意"不好跳过"：

* 清单常驻左边，组件与许可一眼看全；
* 全文在右边可滚动（默认展开自己那份 MIT，可切换第三方文本）；
* 「同意并继续」在勾选之前是灰的；关掉窗口或点「不同意」= 拒绝；
* 同意结果写进配置（带版本号），协议集合变了会重新问（`app/licenses.py`）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import i18n, licenses
from . import design
from .widgets import wrap


class LicenseDialog(QDialog):
    """返回 `Accepted` = 同意；其它（拒绝 / 关闭）= 不同意。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("许可协议"))
        self.resize(980, 640)
        self.setMinimumSize(820, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            design.METRICS.gap_lg, design.METRICS.gap_lg,
            design.METRICS.gap_lg, design.METRICS.gap_lg,
        )
        layout.setSpacing(design.METRICS.gap_sm)

        head = QLabel(i18n.tr("首次使用前，请阅读并同意以下许可协议"))
        design.set_role(head, "title")
        layout.addWidget(head)

        hint = QLabel(
            i18n.tr(
                "本应用自身以 MIT 发布；分发包里还包含第三方组件（含 GPL / LGPL / "
                "OFL 等），它们的许可同样适用于对应部分。"
            )
        )
        design.set_role(hint, "hint")
        wrap(hint)
        layout.addWidget(hint)

        columns = QHBoxLayout()
        columns.setSpacing(design.METRICS.gap_md)
        columns.addWidget(self._build_list(), 1)
        columns.addWidget(self._build_text(), 2)
        layout.addLayout(columns, 1)

        self.agree = QCheckBox(
            i18n.tr("我已阅读并同意上述许可条款（MIT 及第三方组件各自的许可）")
        )
        self.agree.toggled.connect(self._sync)
        layout.addWidget(self.agree)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        self.btn_accept = QPushButton(i18n.tr("同意并继续"))
        design.set_variant(self.btn_accept, "secondary")
        self.btn_accept.setMinimumHeight(design.METRICS.button_medium_height)
        self.btn_accept.setEnabled(False)
        self.btn_accept.clicked.connect(self.accept)
        row.addWidget(self.btn_accept)

        self.btn_decline = QPushButton(i18n.tr("不同意并退出"))
        design.set_variant(self.btn_decline, "danger")
        self.btn_decline.clicked.connect(self.reject)
        row.addWidget(self.btn_decline)
        row.addStretch(1)
        layout.addLayout(row)
        i18n.translate(self)

    # ---- 左：组件清单 ----

    def _build_list(self) -> QWidget:
        card, layout = design.card()
        title = QLabel(i18n.tr("组件与许可"))
        design.set_role(title, "section")
        layout.addWidget(title)

        lines = []
        for item in licenses.COMPONENTS:
            scope = (
                i18n.tr("应用本体")
                if item.scope == "app"
                else i18n.tr("含库完整包")
            )
            # 组件名与说明来自 app/licenses.py（数据层），这里过一遍词表：
            # 控件扫不到组合出来的富文本，所以显式翻。
            lines.append("<b>%s</b><br>%s　·　%s<br><span>%s</span>" % (
                i18n.tr(item.name), item.license_name, scope, i18n.tr(item.notice),
            ))
        body = QLabel("<br><br>".join(lines))
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(body, 1)
        return card

    # ---- 右：许可全文 ----

    def _build_text(self) -> QWidget:
        card, layout = design.card()
        self.all_texts = licenses.texts()
        picker_row = QHBoxLayout()
        picker_row.setSpacing(design.METRICS.gap_sm)
        label = QLabel(i18n.tr("许可全文"))
        design.set_role(label, "section")
        picker_row.addWidget(label)
        self.picker = QComboBox()
        for title, _ in self.all_texts:
            self.picker.addItem(title)
        self.picker.currentIndexChanged.connect(self._show_text)
        picker_row.addWidget(self.picker, 1)
        layout.addLayout(picker_row)

        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        layout.addWidget(self.viewer, 1)
        self._show_text()
        return card

    def _show_text(self) -> None:
        index = max(0, self.picker.currentIndex())
        if not self.all_texts:
            self.viewer.setPlainText(
                i18n.tr("（包里没有找到许可文本，请检查安装是否完整）")
            )
            return
        self.viewer.setPlainText(self.all_texts[index][1])

    # ---- 交互 ----

    def _sync(self) -> None:
        self.btn_accept.setEnabled(self.agree.isChecked())

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """直接关窗口 = 不同意（别让"点叉"被当成同意）。"""

        if self.result() != QDialog.DialogCode.Accepted:
            self.reject()
        super().closeEvent(event)
