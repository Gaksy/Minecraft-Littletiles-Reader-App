"""库版本：启动时就问，不用先导出一次。

以前版本号只能从导出的 `start` 事件里拿到，没导出过就一直写"（本次还没导出过）"。
现在启动时跑一次 `LittleTilesReader --version`（几十毫秒），顺手还验证了
"这个 CLI 真的跑得起来"；问不到也不该让界面起不来。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.library_probe import parse_version, probe  # noqa: E402
from app.ui import design, main_window  # noqa: E402
from ltgen import paths  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    print("== 库版本探测 ==")
    check("取最后一行（纯版本号）",
          parse_version("LittleTiles Reader 0.2.0-beta (test build)\n0.2.0-beta\n")
          == "0.2.0-beta",
          parse_version("LittleTiles Reader 0.2.0-beta (test build)\n0.2.0-beta\n"))
    check("空输出给空串", parse_version("") == "" and parse_version("\n\n") == "")
    check("只有一行也能取", parse_version("1.2.3\n") == "1.2.3")
    check("文件不在时安静返回空串", probe("/没有/这个/可执行文件") == "")

    executable = paths.reader_executable()
    if executable.is_file():
        version = probe(executable)
        check("真 CLI 问得到版本号", bool(version) and version[0].isdigit(), version)
    else:
        print("  [跳过] 没找到库 CLI（%s）" % executable)

    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")
    with tempfile.TemporaryDirectory(prefix="lt-probe-") as tmp:
        config = AppConfig()
        config.save = lambda path=None: Path(tmp) / "app.json"
        if executable.is_file():
            config.library_cli = str(executable)
        window = main_window.MainWindow(config)
        check("主界面一建好就有库版本（没导出过）",
              bool(window._library_version) if executable.is_file()
              else window._library_version == "",
              window._library_version)
        shown: dict = {}
        main_window.QMessageBox.information = staticmethod(
            lambda _parent, _title, text="", *a, **k: shown.update(text=text)
        )
        window._show_about()
        check("关于里有库版本", "库版本" in shown.get("text", ""), shown.get("text", "")[:80])
        check("关于里不再写「本次还没导出过」",
              "本次还没导出过" not in shown.get("text", ""))
        window.close()

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
