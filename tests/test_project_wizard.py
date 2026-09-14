"""新建项目向导：项目名 / 简介 / 存档目录（必填）/ 封面。

要验的是那条硬约束：**存档目录不填就走不下去**——项目模式的导出全靠它，
建完再空着，第一次导出就会被反问一次。
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.project import Project  # noqa: E402
from app.ui import design  # noqa: E402
from app.ui.project_wizard import NewProjectWizard  # noqa: E402

#: 一张真的 1×1 PNG（假的会让 Qt 报 libpng 错，日志里全是噪音）
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 新建项目向导 ==")
    QApplication.instance() or QApplication([])
    design.install(QApplication.instance(), "dark")
    warnings: list[str] = []
    QMessageBox.warning = staticmethod(
        lambda _parent, _title, text="", *a, **k: warnings.append(str(text))
        or QMessageBox.StandardButton.Ok
    )
    QMessageBox.question = staticmethod(
        lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    with tempfile.TemporaryDirectory(prefix="lt-wizard-") as tmp:
        root = Path(tmp)
        world = root / "世界"
        (world / "region").mkdir(parents=True)
        (world / "region" / "r.0.0.mca").write_bytes(b"x" * 100)
        (world / "level.dat").write_bytes(b"level")
        cover = root / "封面.png"
        cover.write_bytes(PNG_1PX)

        wizard = NewProjectWizard(AppConfig(), root / "城东地铁站")
        wizard.show()
        QApplication.instance().processEvents()

        check("第一页问项目名", "项目名" in wizard.name_page.name_edit.placeholderText()
              or wizard.name_page.name_edit.text() == "城东地铁站",
              wizard.name_page.name_edit.text())

        # 名字空着过不去
        wizard.name_page.name_edit.setText("   ")
        check("名字空着拦下来", not wizard.name_page.validatePage())
        check("给了提示", any("项目名" in text for text in warnings), str(warnings[-1:]))

        wizard.name_page.name_edit.setText("城东地铁站")
        wizard.name_page.description_edit.setPlainText("扶梯与站台")
        check("名字填好就能过", wizard.name_page.validatePage())

        # 存档目录不填过不去
        check("存档目录空着拦下来", not wizard.source_page.validatePage())
        check("说了必须填", any("存档" in text for text in warnings), str(warnings[-1:]))

        wizard.source_page.save_edit.setText(str(root / "没有这个"))
        check("目录不存在也拦下来", not wizard.source_page.validatePage())

        wizard.source_page.save_edit.setText(str(world))
        check("存档目录合法就放行", wizard.source_page.validatePage())
        check("当场说清认出了什么", wizard.source_page.save_status.text().startswith("✓"),
              wizard.source_page.save_status.text())

        wizard.source_page.cover_path = str(cover)
        wizard.source_page._refresh_cover()
        values = wizard.values()
        check("向导把四样东西都带出来",
              values["name"] == "城东地铁站"
              and values["description"] == "扶梯与站台"
              and values["save_root"] == str(world)
              and values["cover"] == str(cover),
              str(values))

        # 真按向导的值建一次项目
        project = Project.create(root / "城东地铁站", values["name"])
        project.description = values["description"]
        project.save_root = values["save_root"]
        project.save()
        project.set_cover(values["cover"])
        loaded = Project.load(project.path)
        check("建出来的项目名字/简介/存档都在",
              loaded is not None and loaded.name == "城东地铁站"
              and loaded.description == "扶梯与站台"
              and loaded.save_root == str(world),
              "%s / %s" % (loaded.name, loaded.save_root))
        check("封面也存进项目了",
              loaded.cover_png() is not None and loaded.cover_png().is_file())
        check("向导不用点导出就能建项目", (project.path / "project.json").is_file())
        wizard.close()

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
