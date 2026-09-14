"""我的反馈：本机提交过的反馈列表 + 状态 + 查看回复。

设计要点（与 `docs/feedback-v2.md` §5 对应）：

* 列表里显示**未读点**：`seenAt` 为空说明这条还没被看过；
* 「查看详情」永远是**主动查询**（真发请求），拿回来的是最新状态与回复；
* 回复**译文优先**，下面可展开「中文原文（对照）」；没有译文就显示中文并注明；
* 详情看过之后写 `seenAt` → 以后启动不再自动查这条。
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..api import ApiClient, ApiError
from ..report import ReportStore, query, refresh, reply_for
from . import design
from .widgets import wrap


class MyFeedbackDialog(QDialog):
    """我提交过的反馈：看状态、看回复、复制数据码。"""

    def __init__(
        self,
        app_dir: Path | str,
        parent: QWidget | None = None,
        *,
        client: ApiClient | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("我的反馈"))
        self.resize(900, 560)
        self.app_dir = Path(app_dir)
        self.client = client or ApiClient()
        self.store = ReportStore.load(self.app_dir)

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_sm)

        head = QLabel(i18n.tr("这里列出本机提交过的反馈；「查看详情」会去服务器查最新状态与回复。"))
        design.set_role(head, "hint")
        wrap(head)
        layout.addWidget(head)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            i18n.tr_all(["未读", "编号", "标题", "状态", "惯用语言", "提交时间"])
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._sync)
        layout.addWidget(self.table, 1)

        detail_label = QLabel(i18n.tr("回复"))
        design.set_role(detail_label, "section")
        layout.addWidget(detail_label)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(160)
        layout.addWidget(self.detail, 1)

        self.origin_toggle = QPushButton(i18n.tr("查看中文原文（对照）"))
        self.origin_toggle.setCheckable(True)
        self.origin_toggle.setVisible(False)
        self.origin_toggle.toggled.connect(self._render_detail)
        layout.addWidget(self.origin_toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        self.btn_view = QPushButton(i18n.tr("查看详情"))
        design.set_variant(self.btn_view, "secondary")
        self.btn_view.clicked.connect(self._view)
        row.addWidget(self.btn_view)
        self.btn_copy = QPushButton(i18n.tr("复制数据码"))
        self.btn_copy.clicked.connect(self._copy_code)
        row.addWidget(self.btn_copy)
        self.btn_log = QPushButton(i18n.tr("打开本机日志"))
        self.btn_log.clicked.connect(self._open_log)
        row.addWidget(self.btn_log)
        self.btn_delete = QPushButton(i18n.tr("删除记录"))
        design.set_variant(self.btn_delete, "danger")
        self.btn_delete.clicked.connect(self._delete)
        row.addWidget(self.btn_delete)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        layout.addLayout(row)

        self._refresh()
        i18n.translate(self)

    # ---- 列表 ----

    def _refresh(self) -> None:
        items = self.store.items
        self.table.setRowCount(len(items))
        for row, entry in enumerate(items):
            values = [
                "●" if not entry.get("seenAt") else "",
                str(entry.get("bugNo") or ""),
                str(entry.get("title") or ""),
                str(entry.get("statusName") or i18n.tr("未查询")),
                str(entry.get("localeName") or "—"),
                str(entry.get("createdAt") or ""),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        if items:
            self.table.selectRow(0)
        self._sync()

    def _selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        if 0 <= index < len(self.store.items):
            return self.store.items[index]
        return None

    def _sync(self) -> None:
        entry = self._selected()
        has = entry is not None
        for button in (self.btn_view, self.btn_copy, self.btn_delete):
            button.setEnabled(has)
        self.btn_log.setEnabled(bool(has and entry.get("logCopy")))
        self._render_detail()

    # ---- 详情渲染 ----

    def _render_detail(self) -> None:
        entry = self._selected()
        if entry is None:
            self.detail.setPlainText("")
            self.origin_toggle.setVisible(False)
            return
        lines = [
            "%s：%s" % (i18n.tr("状态"), entry.get("statusName") or i18n.tr("未查询")),
            "%s：%s" % (i18n.tr("编号"), entry.get("bugNo") or "—"),
            "%s：%s" % (i18n.tr("数据码"), entry.get("dataCode") or "—"),
        ]
        if entry.get("lastCheckedAt"):
            lines.append("%s：%s" % (i18n.tr("上次查询"), entry["lastCheckedAt"]))
        lines.append("")

        show_origin = self.origin_toggle.isChecked()
        has_origin = False
        for field_name, title in (("resolution", "处理方案"), ("opinion", "处理意见")):
            text, origin = reply_for(entry, field_name)
            if not text and not origin:
                continue
            lines.append("—— %s ——" % i18n.tr(title))
            if origin and show_origin:
                lines.append(origin)
            else:
                lines.append(text)
                if origin:
                    has_origin = True
                elif entry.get(field_name):
                    lines.append(i18n.tr("（本条回复只有中文）"))
            lines.append("")
        self.detail.setPlainText("\n".join(lines).strip())

        # 有中文原文才显示那个折叠按钮
        has_translation = any(
            reply_for(entry, field)[1] for field in ("resolution", "opinion")
        )
        self.origin_toggle.setVisible(bool(has_translation))
        if not has_translation and self.origin_toggle.isChecked():
            self.origin_toggle.setChecked(False)

    # ---- 操作 ----

    def _view(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        code = entry.get("dataCode")
        if not code:
            return
        try:
            payload = query(code, self.client)
        except ApiError as error:
            QMessageBox.warning(
                self,
                i18n.tr("查询失败"),
                i18n.tr("没能从服务器拿到这条反馈的状态：%s") % error,
            )
            return
        self.store.mark_checked(entry, payload)
        # 看过详情就算已读：以后不再自动查这条
        self.store.mark_seen(entry)
        self._refresh()

    def _copy_code(self) -> None:
        entry = self._selected()
        if entry and entry.get("dataCode"):
            QGuiApplication.clipboard().setText(str(entry["dataCode"]))
            QMessageBox.information(
                self,
                i18n.tr("已复制"),
                i18n.tr("数据码已复制：%s（到网站 /feedback 也能查）") % entry["dataCode"],
            )

    def _open_log(self) -> None:
        entry = self._selected()
        if not entry or not entry.get("logCopy"):
            return
        from .export_panel import default_open_directory

        path = Path(str(entry["logCopy"]))
        if path.is_file():
            default_open_directory(path.parent)
        else:
            QMessageBox.information(
                self, i18n.tr("找不到"), i18n.tr("本机那份记录不在了：\n%s") % path
            )

    def _delete(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        if (
            QMessageBox.question(
                self,
                i18n.tr("删除记录"),
                i18n.tr(
                    "只删本机这条记录？\n\n服务器上的反馈不会删，但数据码会丢，之后查不了进度。"
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.store.remove(str(entry.get("dataCode") or ""))
        self._refresh()


def check_on_start(
    app_dir: Path | str, client: ApiClient | None = None
) -> list[dict]:
    """启动时查一遍没看过的反馈，返回**新变成有结论**的那些（调用方据此弹提示）。"""

    store = ReportStore.load(app_dir)
    if not store.unresolved():
        return []
    solved = refresh(store, client)
    if solved:
        logger_line = ", ".join(str(entry.get("bugNo")) for entry in solved)
        from ..applog import logger

        logger().info("反馈有新结论：%s", logger_line)
    return solved
