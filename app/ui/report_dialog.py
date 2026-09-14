"""反馈问题：写清楚 → 打日志包 → 看一眼将发送什么 → 发送 → 拿数据码。

版面（左表单 / 右预览）与导出对话框同一套：
**左边**写内容（标题、类型、严重程度、描述、联系方式），**右边**是"将发送的内容"
与日志包清单——发送前必须能在同一屏看完，不然"自动附带日志"就成了黑箱。

三条刻意的设计：

1. **发送前能看见全文**：右边预览就是拼好之后的 `description`（含诊断，服务器上限
   2000 字符），下面列出日志包会装哪些文件；
2. **数据码不只显示一次**：落进 `config/reports.json`，按钮可一键复制，凭它能查进度；
3. 失败要说清是哪种（网络不通 / 服务器拒绝 / 内容超长），并把本机留的那份路径给出，
   用户可以直接发邮件。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
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
    LOG_WINDOW_HOURS,
    Report,
    ReportStore,
    attach_log,
    collect_logs_tar,
    diagnostics,
    log_tail,
    recent_logs,
    save_log_copy,
    submit,
    upload_bundle,
)
from . import design
from .widgets import wrap

SEVERITY_LABELS = {"LOW": "轻微", "MEDIUM": "一般", "HIGH": "严重", "CRITICAL": "致命"}
TYPE_LABELS = {"bug": "问题反馈", "suggestion": "建议"}


def human_size(size: int) -> str:
    if size < 1024:
        return "%d B" % size
    if size < 1024 * 1024:
        return "%.1f KB" % (size / 1024)
    return "%.1f MB" % (size / 1024 / 1024)


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
        self.resize(1000, 640)
        self.setMinimumSize(860, 560)
        self.config = config
        self.app_dir = Path(app_dir)
        self.client = client or ApiClient(getattr(config, "server_base", "") or None)
        self._sent: dict = {}
        self._log_path: Path | None = None
        self._bundle = None

        # 诊断只取一次：预览、提交、留档都用同一份，避免"看到的不等于发的"
        self._diagnostics = diagnostics(extra)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            design.METRICS.gap_lg, design.METRICS.gap_lg,
            design.METRICS.gap_lg, design.METRICS.gap_md,
        )
        root.setSpacing(design.METRICS.gap_md)

        head = QLabel(i18n.tr("反馈问题"))
        design.set_role(head, "title")
        root.addWidget(head)

        sub = QLabel(
            i18n.tr("写清问题就好；下面的日志包会帮我们还原现场（发送前你可以先看一眼）。")
        )
        design.set_role(sub, "hint")
        wrap(sub)
        root.addWidget(sub)

        columns = QHBoxLayout()
        columns.setSpacing(design.METRICS.gap_md)
        columns.addWidget(self._build_form(), 1)
        columns.addWidget(self._build_preview(), 1)
        root.addLayout(columns, 1)

        root.addWidget(self._build_actions())
        self.result = QLabel()
        wrap(self.result)
        self.result.setVisible(False)
        root.addWidget(self.result)

        self._refresh_preview()
        i18n.translate(self)

    # ---- 左：表单 ----

    def _build_form(self) -> QWidget:
        card, layout = design.card()
        layout.setSpacing(design.METRICS.gap_sm)

        title = QLabel(i18n.tr("问题"))
        design.set_role(title, "section")
        layout.addWidget(title)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(i18n.tr("一句话说清问题（必填）"))
        layout.addWidget(self.title_edit)

        row = QHBoxLayout()
        row.setSpacing(design.METRICS.gap_sm)
        self.type_box = QComboBox()
        for value in ("bug", "suggestion"):
            self.type_box.addItem(i18n.tr(TYPE_LABELS[value]), value)
        self.severity_box = QComboBox()
        for value in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            self.severity_box.addItem(i18n.tr(SEVERITY_LABELS[value]), value)
        self.severity_box.setCurrentIndex(1)          # MEDIUM
        row.addWidget(self.type_box, 1)
        row.addWidget(self.severity_box, 1)
        layout.addLayout(row)

        # 惯用语言：回复按它给译文（与网站反馈页同一个选项、同一套语义）
        self.locale_box = QComboBox()
        for code, name in i18n.LANGUAGES:
            self.locale_box.addItem(name, code)
        wanted = getattr(self.config, "report_locale", "") or i18n.current()
        index = self.locale_box.findData(wanted)
        if index >= 0:
            self.locale_box.setCurrentIndex(index)
        layout.addWidget(self.locale_box)
        self.locale_hint = QLabel()
        wrap(self.locale_hint)
        design.set_role(self.locale_hint, "hint")
        layout.addWidget(self.locale_hint)
        self.locale_box.currentIndexChanged.connect(self._refresh_locale_hint)
        self._refresh_locale_hint()

        label = QLabel(i18n.tr("详细描述"))
        design.set_role(label, "section")
        layout.addWidget(label)
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText(
            i18n.tr("复现步骤、期望结果、实际结果（越具体越好）")
        )
        layout.addWidget(self.description, 1)

        self.contact_edit = QLineEdit(getattr(config_contact := self.config, "report_contact", "") or "")
        self.contact_edit.setPlaceholderText(i18n.tr("邮箱或其它联系方式（可选）"))
        layout.addWidget(self.contact_edit)

        # ---- 附件 ----
        attach_card, attach_layout = design.card(padding=design.METRICS.gap_sm)
        self.attach = QCheckBox(i18n.tr("把最近 %d 小时的日志打包上传（推荐）") % LOG_WINDOW_HOURS)
        self.attach.setChecked(True)
        attach_layout.addWidget(self.attach)
        self.bundle_hint = QLabel()
        wrap(self.bundle_hint)
        design.set_role(self.bundle_hint, "hint")
        attach_layout.addWidget(self.bundle_hint)
        layout.addWidget(attach_card)

        for widget in (self.title_edit, self.contact_edit):
            widget.textChanged.connect(self._refresh_preview)
        self.description.textChanged.connect(self._refresh_preview)
        self.attach.toggled.connect(self._refresh_preview)
        return card

    # ---- 右：预览 ----

    def _build_preview(self) -> QWidget:
        card, layout = design.card()
        layout.setSpacing(design.METRICS.gap_sm)

        title = QLabel(i18n.tr("将发送的内容"))
        design.set_role(title, "section")
        layout.addWidget(title)

        hint = QLabel(
            i18n.tr("诊断只含版本、系统与库版本；日志已去掉本机用户名与绝对路径。")
        )
        design.set_role(hint, "hint")
        wrap(hint)
        layout.addWidget(hint)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        font = QFont(self.preview.font())
        font.setPixelSize(design.METRICS.font_small)
        self.preview.setFont(font)
        layout.addWidget(self.preview, 1)

        self.counter = QLabel()
        design.set_role(self.counter, "hint")
        wrap(self.counter)
        layout.addWidget(self.counter)

        self.bundle_list = QLabel()
        wrap(self.bundle_list)
        design.set_role(self.bundle_list, "dim")
        layout.addWidget(self.bundle_list)
        return card

    # ---- 底部按钮 ----

    def _build_actions(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(design.METRICS.gap_sm)

        self.btn_send = QPushButton(i18n.tr("发送反馈"))
        design.set_variant(self.btn_send, "secondary")
        self.btn_send.setMinimumHeight(design.METRICS.button_medium_height)
        self.btn_send.clicked.connect(self._send)
        row.addWidget(self.btn_send)

        self.btn_copy = QPushButton(i18n.tr("复制数据码"))
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self._copy_code)
        row.addWidget(self.btn_copy)

        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        return bar

    # ---- 预览 ----

    def _refresh_locale_hint(self) -> None:
        """简体中文不用翻译，直接说清楚；其它语言说明会附中文原文对照。"""

        code = self.locale_box.currentData()
        if code == "zh-Hans":
            self.locale_hint.setText(i18n.tr("回复直接用中文，不需要翻译。"))
        else:
            self.locale_hint.setText(
                i18n.tr("回复会按这个语言给出翻译（AI 翻译），并附中文原文供对照。")
            )

    def _draft(self) -> Report:
        report = Report(
            title=self.title_edit.text().strip(),
            description=self.description.toPlainText().strip(),
            type=self.type_box.currentData(),
            severity=self.severity_box.currentData(),
            contact=self.contact_edit.text().strip(),
            # 惯用语言：默认跟当前界面语言，可在表单里改（与网站反馈页一致）
            locale=self.locale_box.currentData() or i18n.current(),
        )
        if self.attach.isChecked():
            report.diagnostics = self._diagnostics
            report.log_tail = ""
        return report

    def _refresh_preview(self) -> None:
        report = attach_log(self._draft())
        self.preview.setPlainText(report.description)
        used = len(report.description)
        self.counter.setText(
            i18n.tr("服务器上限 %d 字符，当前 %d（超了会被截断）") % (DESC_MAX, used)
        )
        if not self.attach.isChecked():
            self.bundle_hint.setText(i18n.tr("不附带日志：只提交上面的文字与诊断。"))
            self.bundle_list.setText("")
            return
        files = recent_logs(self.app_dir, LOG_WINDOW_HOURS)
        total = sum(item.size for item in files)
        self.bundle_hint.setText(
            i18n.tr("会打包成 tar.gz（脱敏后）：%d 个文件，约 %s")
            % (len(files), human_size(total))
        )
        listed = "\n".join("· %s（%s）" % (item.rel, human_size(item.size)) for item in files[:6])
        if len(files) > 6:
            listed += "\n· …" 
        self.bundle_list.setText(listed)

    # ---- 发送 ----

    def _send(self) -> None:
        report = self._draft()
        if not report.title:
            self._warn(i18n.tr("请先填标题。"))
            return
        self.btn_send.setEnabled(False)
        try:
            result = submit(report, self.client, want_attachment=self.attach.isChecked())
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
                # 提交时的惯用语言与初始状态：后台回复后按它选译文
                "locale": report.locale,
                "status": None,
                "statusName": None,
                "lastCheckedAt": None,
                "seenAt": None,
            }
        )
        self.btn_copy.setEnabled(bool(code))
        lines = [
            i18n.tr("已提交：编号 %s，数据码 %s。") % (bug_no, code),
        ]

        # 第二步：日志包（失败了不影响"反馈已经提交"）
        if self.attach.isChecked():
            lines.append(self._upload_logs(str(result.get("uploadToken", ""))))
        lines.append(i18n.tr("本机留了一份：%s") % self._log_path)
        self.result.setText("\n".join(lines))
        self.result.setVisible(True)
        design.set_role(self.result, "ok")
        if report.contact:
            self.config.report_contact = report.contact
        self.config.report_locale = report.locale      # 下次默认用这次选的

    def _upload_logs(self, token: str) -> str:
        bundle = collect_logs_tar(
            self.app_dir, LOG_WINDOW_HOURS, diagnostics_text=self._diagnostics
        )
        if bundle is None:
            return i18n.tr("没有可打包的日志（这次会话还没写日志文件）。")
        self._bundle = bundle
        if not token:
            return i18n.tr(
                "日志包已生成，但服务器还没开启附件上传；文件在本机：\n%s"
            ) % bundle.path
        try:
            upload_bundle(bundle, token, self.client)
        except ApiError as error:
            return i18n.tr("日志包上传失败（%s）：文件在本机：\n%s") % (error, bundle.path)
        return i18n.tr("日志包已上传：%s（%s，%d 个文件）") % (
            bundle.name, human_size(bundle.size), bundle.files,
        )

    def _warn(self, text: str) -> None:
        self.result.setText(text)
        self.result.setVisible(True)
        design.set_role(self.result, "warn")

    def _failed(self, error: ApiError, report: Report) -> None:
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
        self.result.setVisible(True)
        design.set_role(self.result, "error")

    def _copy_code(self) -> None:
        code = str(self._sent.get("dataCode", ""))
        if code:
            QGuiApplication.clipboard().setText(code)
            self.result.setText(i18n.tr("数据码已复制：%s（查询进度用它）") % code)
            design.set_role(self.result, "ok")
