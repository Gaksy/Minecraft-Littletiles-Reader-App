"""两个对话框的离屏自检：反馈表单（含预览与结果）与检查更新结果页。

网络一律走替身：`ReportDialog` / `UpdateDialog` 都接受注入的客户端。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from app.api import ApiClient  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.report import ReportStore  # noqa: E402
from app.ui import design  # noqa: E402
from app.ui.report_dialog import ReportDialog  # noqa: E402
from app.ui.update_dialog import UpdateDialog  # noqa: E402
from app.update import UpdateInfo  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def client_returning(result: dict) -> ApiClient:
    def opener(_request):
        return json.dumps({"success": True, "payload": result},
                          ensure_ascii=False).encode("utf-8")

    return ApiClient(opener=opener)


class _TwoStep:
    """两段式替身：/feedback/submit 发凭证，/feedback/attach 收附件。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.payload: dict = {}
        self.file_bytes = 0

    def __call__(self, request):
        url = request.full_url
        self.calls.append(url)
        if url.endswith("/feedback/attach"):
            self.file_bytes = len(request.data or b"")
            return json.dumps({"success": True, "payload": {
                "name": "logs.tar.gz", "size": self.file_bytes, "sha256": "b" * 64}
            }).encode("utf-8")
        self.payload = json.loads((request.data or b"{}").decode("utf-8"))
        return json.dumps({"success": True, "payload": {
            "bugId": 9, "bugNo": "20260914-009", "dataCode": "WXYZ2345",
            "uploadToken": "9f3c" * 8,
        }}).encode("utf-8")


def main() -> int:
    print("== 反馈与更新对话框 ==")
    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")

    with tempfile.TemporaryDirectory(prefix="lt-report-ui-") as tmp:
        root = Path(tmp)
        config = AppConfig()
        config.save = lambda path=None: root / "app.json"
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "logs" / "2026-09-14_180000.log").write_text(
            "app=0.1.0\n正在导出\n" * 30, encoding="utf-8")

        # ---- 反馈表单 ----
        client = _TwoStep()
        dialog = ReportDialog(
            config, root, None, client=ApiClient(opener=client),
            extra={"library": "0.2.0-beta"},
        )
        dialog.show()
        application.processEvents()
        check("预览里已经有诊断（默认勾选附带）",
              "app=" in dialog.preview.toPlainText()
              and "0.2.0-beta" in dialog.preview.toPlainText(),
              dialog.preview.toPlainText()[:80])
        check("列出了要打包的日志",
              "2026-09-14_180000.log" in dialog.bundle_list.text(),
              dialog.bundle_list.text()[:60])
        check("附件说明写了体积", "KB" in dialog.bundle_hint.text() or "B" in dialog.bundle_hint.text(),
              dialog.bundle_hint.text())
        check("字符计数在提示上限",
              "2000" in dialog.counter.text(), dialog.counter.text())

        dialog.attach.setChecked(False)
        application.processEvents()
        check("不勾选就没有诊断与日志",
              "app=" not in dialog.preview.toPlainText(),
              dialog.preview.toPlainText()[:80])
        dialog.attach.setChecked(True)

        dialog.title_edit.setText("导出到一半卡住")
        dialog.description.setPlainText("点导出后进度条停在 100%，日志见下。")
        application.processEvents()

        dialog._send()
        application.processEvents()
        text = dialog.result.text()
        check("提交时带上了 wantAttachment 标记",
              client.payload.get("wantAttachment") is True, str(client.payload.get("wantAttachment")))
        check("发送成功后显示编号与数据码",
              "20260914-009" in text and "WXYZ2345" in text, text.replace("\n", " | "))
        check("接着把日志包传上去了",
              any(url.endswith("/feedback/attach") for url in client.calls)
              and client.file_bytes > 0,
              "%s / %d 字节" % (client.calls, client.file_bytes))
        check("结果里说了日志包已上传", "日志包已上传" in text, text.replace("\n", " | "))
        check("复制按钮可用了", dialog.btn_copy.isEnabled())
        store = ReportStore.load(root)
        check("编号与数据码也落盘了",
              store.latest() is not None and store.latest()["bugNo"] == "20260914-009",
              str(store.items))
        check("本机留了一份完整内容",
              dialog._log_path is not None and dialog._log_path.is_file(),
              str(dialog._log_path))

        # 没填标题就不发
        blank = ReportDialog(config, root, None, client=client_returning({}))
        blank.show()
        application.processEvents()
        blank._send()
        check("没填标题会被拦住", "标题" in blank.result.text(), blank.result.text())
        blank.close()
        dialog.close()

        # ---- 检查更新 ----
        newer = UpdateDialog(UpdateInfo(current="0.1.0", latest="v0.9.0",
                                        has_update=True, platform="macos-arm",
                                        url="https://example.invalid/a.zip",
                                        note="12 MB"))
        newer.show()
        application.processEvents()
        joined = " ".join(label.text() for label in newer.findChildren(QLabel))
        check("有新版时写清版本对比",
              "0.1.0" in joined and "v0.9.0" in joined, joined[:80])
        buttons = [b.text() for b in newer.findChildren(QPushButton)]
        check("给了下载入口", any("下载" in text for text in buttons), str(buttons))
        newer.close()

        plain = UpdateDialog(UpdateInfo(current="0.1.0", latest="", has_update=False,
                                        platform="windows"))
        plain.show()
        application.processEvents()
        joined = " ".join(label.text() for label in plain.findChildren(QLabel))
        check("服务器没发布时说明清楚", "windows" in joined, joined[:80])
        plain.close()

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
