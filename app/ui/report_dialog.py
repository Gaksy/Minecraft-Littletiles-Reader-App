"""反馈问题：写清楚 + 看到将要发送什么 + 发送 + 记住数据码。

三个刻意的设计：

1. **发送前能看见全文**（预览框里就是拼好之后的 description）——诊断与日志会
   一起发出去，用户有权在按下发送前看到它，也顺着这条提示看清"哪些信息没被收集"；
2. **数据码不只显示一次**：落进 `config/reports.json`，对话框里也能一键复制，
   凭它能查进度（服务器公开接口）；
3. 发送失败要**说清是哪种失败**（网络不通 / 服务器拒绝 / 内容超长），
   并把本机留的那份日志路径给出来——用户可以直接发邮件。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, i18n
from ..api import ApiClient, ApiError
from ..report import (
    DESC_MAX,
    QUERY_PATH,
    Report,
    ReportStore,
    build_payload,
    diagnostics,
    log_tail,
    redact,
    save_log_copy,
    submit,
)
from . import design
from .widgets import wrap

SEVERITY_LABELS = {
    "LOW": "轻微",
    "MEDIUM": "一般",
    "HIGH": "严重",
    "CRITICAL": "致命",
}
TYPE_LABELS = {"bug": "问题反馈", "suggestion": "建议"}


class ReportDialog(QDialog):
    """写反馈、看预览、发送、拿数据码。"""

    def __init__(
        self,
        config,
        app_dir: Path | str,
        parent: QWidget | None = None,
        *,
        client: ApiClient | None = None,
        extra: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("反馈问题"))
        self.setMinimumWidth(680)
        self.config = config
        self.app_dir = Path(app_dir)
        self.client = client or ApiClient(getattr(config, "server_base", "") or None)
        self._sent: dict = {}
        self._log_path: Path | None = None

        # 诊断与日志只在这里取一次：预览、提交、留档都用同一份，避免"看到的不等于发的"
        self._diagnostics = diagnostics(extra)
        self._log_tail = log_tail()

        layout = QVBoxLayout(self)
        layout.setSpacing(design.METRICS.gap_sm)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(i18n.tr("一句话说清问题（必填）"))
        form.addRow(i18n.tr("标题"), self.title_edit)

        kinds = QHBoxLayout()
        self.type_box = QComboBox()
        for value in ("bug", "suggestion"):
            self.type_box.addItem(i18n.tr(TYPE_LABELS[value]), value)
        self.severity_box = QComboBox()
        for value in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            self.severity_box.addItem(i18n.tr(SEVERITY_LABELS[value]), value)
        self.severity_box.setCurrentIndex(1)          # MEDIUM
        kinds.addWidget(self.type_box)
        kinds.addWidget(QLabel(i18n.tr("严重程度")))
        kinds.addWidget(self.severity_box)
        kinds.addStretch(1)
        holder = QWidget()
        holder.setLayout(kinds)
        form.addRow(i18n.tr("类型"), holder)

        self.contact_edit = QLineEdit(getattr(config, "report_contact", "") or "")
        self.contact_edit.setPlaceholderText(i18n.tr("邮箱或其它联系方式（可选）"))
        form.addRow(i18n.tr("联系方式"), self.contact_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel(i18n.tr("详细描述")))
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText(
            i18n.tr("复现步骤、期望结果、实际结果（越具体越好）")
        )
        self.description.setFixedHeight(120)
        layout.addWidget(self.description)

        self.attach = QCheckBox(i18n.tr("附带诊断信息与日志尾部（推荐）"))
        self.attach.setChecked(True)
        self.attach.setToolTip(
            i18n.tr("只包含版本、系统、日志尾部；已去掉本机用户名与绝对路径")
        )
        layout.addWidget(self.attach)

        layout.addWidget(QLabel(i18n.tr("将发送的内容（可以先看一眼）")))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(150)
        layout.addWidget(self.preview)

        self.counter = QLabel()
        design.set_role(self.counter, "hint")
        wrap(self.counter)
        layout.addWidget(self.counter)

        row = QHBoxLayout()
        self.btn_send = QPushButton(i18n.tr("发送反馈"))
        design.set_variant(self.btn_send, "secondary")
        self.btn_send.clicked.connect(self._send)
        row.addWidget(self.btn_send)
        self.btn_copy = QPushButton(i18n.tr("复制数据码"))
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self._copy_code)
        row.addWidget(self.btn_copy)
        row.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)

        self.result = QLabel()
        wrap(self.result)
        layout.addWidget(self.result)

        for widget in (self.title_edit, self.contact_edit):
            widget.textChanged.connect(self._refresh_preview)
        self.description.textChanged.connect(self._refresh_preview)
        self.attach.toggled.connect(self._refresh_preview)
        self.type_box.currentIndexChanged.connect(self._refresh_preview)
        self.severity_box.currentIndexChanged.connect(self._refresh_preview)

        self._refresh_preview()
        i18n.translate(self)

    # ---- 预览 ----

    def _draft(self) -> Report:
        report = Report(
            title=self.title_edit.text().strip(),
            description=self.description.toPlainText().strip(),
            type=self.type_box.currentData(),
            severity=self.severity_box.currentData(),
            contact=self.contact_edit.text().strip(),
        )
        if self.attach.isChecked():
            report.diagnostics = self._diagnostics
            report.log_tail = self._log_tail
        else:
            report.diagnostics = ""
            report.log_tail = ""
        return report

    def _refresh_preview(self) -> None:
        from ..report import attach_log

        report = attach_log(self._draft())
        self.preview.setPlainText(report.description)
        used = len(report.description)
        self.counter.setText(
            i18n.tr("服务器上限 %d 字符，当前 %d（超了会被截断）") % (DESC_MAX, used)
        )

    # ---- 发送 ----

    def _send(self) -> None:
        report = self._draft()
        if not report.title:
            self.result.setText(i18n.tr("请先填标题。"))
            design.set_role(self.result, "warn")
            return
        self.btn_send.setEnabled(False)
        try:
            result = submit(report, self.client)
        except ApiError as error:
            self._failed(error, report)
            return
        finally:
            self.btn_send.setEnabled(True)

        self._sent = result
        bug_no = str(result.get("bugNo", ""))
        code = str(result.get("dataCode", ""))
        self._log_path = save_log_copy(report, self.app_dir, bug_no)
        store = ReportStore.load(self.app_dir)
        store.add(
            {
                "bugNo": bug_no,
                "dataCode": code,
                "title": report.title,
                "type": report.type,
                "severity": report.severity,
                "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "logCopy": str(self._log_path),
            }
        )
        self.btn_copy.setEnabled(bool(code))
        self.result.setText(
            i18n.tr(
                "已提交：编号 %s，数据码 %s。\n凭数据码可以查进度；本机也留了一份：\n%s"
            )
            % (bug_no, code, self._log_path)
        )
        design.set_role(self.result, "ok")
        if report.contact:
            self.config.report_contact = report.contact

    def _failed(self, error: ApiError, report: Report) -> None:
        """失败要说清是哪种：网络不通 / 服务器拒绝 / 内容问题。"""

        kind = {
            "network": i18n.tr("网络不通"),
            "server": i18n.tr("服务器拒绝了这次提交"),
            "bad_response": i18n.tr("服务器返回的内容看不懂"),
            "client": i18n.tr("内容有问题"),
        }.get(error.kind, error.kind)
        path = save_log_copy(report, self.app_dir, "未提交")
        self.result.setText(
            i18n.tr("%s：%s\n\n内容已留在本机，可以直接发邮件：\n%s")
            % (kind, error, path)
        )
        design.set_role(self.result, "error")

    def _copy_code(self) -> None:
        code = str(self._sent.get("dataCode", ""))
        if code:
            QGuiApplication.clipboard().setText(code)
            self.result.setText(
                i18n.tr("数据码已复制：%s（查询进度用它）") % code
            )
