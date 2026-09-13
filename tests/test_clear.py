"""清空重来：删素材、删缓存、重置索引，但保留用户的原始压缩包。

补这条是因为它曾经崩过——`_clear_everything` 用了模块级没导入的 `shutil`，
一按就 NameError。调用一次就能测出来的东西，不该漏。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.library import Library, import_source  # noqa: E402
from app.ui import material_manager as mm  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name, "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 清空重来 ==")
    QApplication([])
    jar = os.environ.get("LTR_VANILLA_JAR", "")
    if not jar or not Path(jar).is_file():
        print("  [跳过] 未设置 LTR_VANILLA_JAR")
        return 0

    with tempfile.TemporaryDirectory(prefix="lt-clear-") as tmp:
        app_dir = Path(tmp)
        work = app_dir / "cache" / "sources"
        library = Library()
        library.add(import_source(Path(jar), app_dir, work))
        library.enable(library.sources[0].id)
        library.save(app_dir)
        (app_dir / "cache" / "packages" / "abc").mkdir(parents=True, exist_ok=True)
        (app_dir / "cache" / "icons").mkdir(parents=True, exist_ok=True)

        dialog = mm.MaterialManagerDialog(app_dir)
        check("清空前有素材", len(dialog.library.sources) == 1)
        check("清空前有解压出来的素材", (app_dir / "resources" / "sources").is_dir())

        # 替身：确认框直接答"是"，不然会等人点
        mm.QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes
        )
        dialog._clear_everything()

        check("素材清零", dialog.library.sources == [])
        check("启用列表清零", dialog.library.enabled == [])
        check("解压目录已删", not (app_dir / "resources" / "sources").exists())
        check("组合缓存已删", not (app_dir / "cache" / "packages").exists())
        check("图标缓存已删", not (app_dir / "cache" / "icons").exists())
        check("存盘的索引也重置了", Library.load(app_dir).sources == [])
        check("原始 jar 没被动", Path(jar).is_file())

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
