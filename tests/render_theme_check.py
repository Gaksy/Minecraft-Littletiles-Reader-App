"""把界面在浅色与深色调色板下各渲染一张 PNG，人工核对配色。

离屏运行，不需要显示器：
    python tests/render_theme_check.py [输出目录]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.ui.export_dialog import ExportRegionDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def dark_palette() -> QPalette:
    """手工造一份深色调色板——不依赖系统是否真的处于深色模式。"""
    palette = QPalette()
    window = QColor("#1e1e1e")
    base = QColor("#252526")
    text = QColor("#e6e6e6")
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, base)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Mid, QColor("#3c3c3c"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#094771"))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    return palette


def render(palette: QPalette, path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    application.setPalette(palette)
    window = MainWindow(AppConfig())
    window.resize(880, 620)
    window.show()
    application.processEvents()
    window.grab().save(str(path))
    window.close()


def render_dialog(palette: QPalette, path: Path) -> None:
    """导出对话框里画得最多（自绘网格），单独出一张。"""
    application = QApplication.instance() or QApplication([])
    application.setPalette(palette)
    dialog = ExportRegionDialog(AppConfig())
    dialog.resize(760, 620)
    dialog.show()
    application.processEvents()
    dialog.grab().save(str(path))
    dialog.close()


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp" / "theme"
    out_dir.mkdir(parents=True, exist_ok=True)
    light = out_dir / "light.png"
    dark = out_dir / "dark.png"
    render(QApplication([]).style().standardPalette(), light)
    render(dark_palette(), dark)
    print("浅色: %s" % light)
    print("深色: %s" % dark)
    application = QApplication.instance() or QApplication([])
    render_dialog(application.style().standardPalette(), out_dir / "dialog_light.png")
    render_dialog(dark_palette(), out_dir / "dialog_dark.png")
    print("对话框: %s / %s" % (out_dir / "dialog_light.png", out_dir / "dialog_dark.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
