"""默认输出目录管理（P0 需求）：菜单里能改、能恢复、状态栏跟着变。

    python tests/test_output_dir.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 数据目录指到临时目录：自检绝不能碰用户真实的 config/ 与 logs/
# （`data_dir()` 每次调用重新解析 LTR_HOME，所以在这里设就够了）
_LTR_HOME = tempfile.mkdtemp(prefix="lt-home-")
os.environ["LTR_HOME"] = _LTR_HOME

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.ui import design, main_window  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print("  %s %s%s" % ("[OK]" if condition else "[FAIL]", name,
                         "  " + detail if detail else ""))
    if not condition:
        FAILURES.append(name)


def main() -> int:
    application = QApplication.instance() or QApplication([])
    design.install(application, "dark")

    with tempfile.TemporaryDirectory(prefix="lt-outdir-") as tmp:
        root = Path(tmp)
        config = AppConfig()
        saved: dict = {}
        config.save = lambda path=None: saved.update(path=str(root / "app.json"))
        window = main_window.MainWindow(config)

        default_dir = config.resolved_output_dir()
        check("默认落在应用目录下的 outputs",
              default_dir.name == "outputs", str(default_dir))
        check("状态栏里有输出目录", "模型输出目录" in window.status.currentMessage())

        chosen = root / "导出到这儿"
        chosen.mkdir()
        main_window.QFileDialog.getExistingDirectory = staticmethod(
            lambda *a, **k: str(chosen)
        )
        window._choose_output_dir()
        check("选择后写进配置", config.output_dir == str(chosen), config.output_dir)
        check("选择后落盘", "path" in saved)
        check("状态栏跟着变",
              str(chosen) in window.status.currentMessage(),
              window.status.currentMessage())

        # 取消（返回空串）不改动已有设置
        main_window.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
        window._choose_output_dir()
        check("取消不改设置", config.output_dir == str(chosen), config.output_dir)

        window._reset_output_dir()
        check("恢复默认后字段清空", config.output_dir == "")
        check("恢复默认后回到 outputs",
              config.resolved_output_dir().name == "outputs")
        window.close()

    print()
    if FAILURES:
        print("失败 %d 项: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
