"""首次启动的许可协议：必须看得到、必须勾了才能同意、不同意就退出、版本变要重问。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from app import licenses  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.ui import design  # noqa: E402
from app.ui.license_dialog import LicenseDialog  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 许可协议 ==")
    QApplication.instance() or QApplication([])
    design.install(QApplication.instance(), "dark")

    with tempfile.TemporaryDirectory(prefix="lt-license-") as tmp:
        config = AppConfig()
        config.save = lambda path=None: Path(tmp) / "app.json"

        check("全新配置需要同意", not licenses.accepted(config))
        licenses.accept(config)
        check("同意后记下版本与时间",
              licenses.accepted(config) and bool(config.licenses_accepted_at),
              "%s / %s" % (config.licenses_version, config.licenses_accepted_at))
        check("同意一次就不会每次启动都问", licenses.accepted(config))

        # 协议集合变了（版本 +1）→ 必须重新问
        config.licenses_version = licenses.LICENSE_SET_VERSION - 1
        check("协议集合更新后要重新同意", not licenses.accepted(config))
        config.licenses_version = licenses.LICENSE_SET_VERSION

        # 清单必须覆盖所有第三方（用户要"同意 MIT 以及 GPL/Boost 等"）
        names = " ".join(item.name for item in licenses.COMPONENTS)
        for keyword in ("MIT", "LGPL", "GPL", "BSL", "zlib", "OFL"):
            check("清单里有 %s" % keyword,
                  keyword in " ".join(item.license_name for item in licenses.COMPONENTS),
                  str([i.license_name for i in licenses.COMPONENTS]))
        summary = licenses.summary()
        check("摘要里逐条列了组件", all(item.name in summary for item in licenses.COMPONENTS))

        # 全文：至少要有 MIT、GPL、LGPL、BSL、zlib、OFL 六份
        texts = licenses.texts()
        titles = " ".join(title for title, _ in texts)
        check("能读到六份许可全文", len(texts) >= 6, str(list(titles.split(" · "))))
        for keyword in ("MIT", "GPL", "LGPL", "Boost", "zlib", "Font"):
            check("全文里有 %s" % keyword, keyword in titles, titles)
        check("MIT 正文是标准文本",
              "Permission is hereby granted" in dict(texts)["LittleTiles Reader · MIT"])

        # 对话框：不勾不给过；关窗口 = 不同意
        dialog = LicenseDialog()
        dialog.show()
        QApplication.instance().processEvents()
        check("默认不能点同意", not dialog.btn_accept.isEnabled())
        dialog.agree.setChecked(True)
        check("勾选后才能点同意", dialog.btn_accept.isEnabled())
        dialog.reject()
        check("拒绝时不是 Accepted", dialog.result() != QDialog.DialogCode.Accepted,
              str(dialog.result()))
        dialog.accept()
        check("同意时是 Accepted", dialog.result() == QDialog.DialogCode.Accepted)
        dialog.close()

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
